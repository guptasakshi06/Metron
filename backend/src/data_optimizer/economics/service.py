"""Reconcile Decimal line items without converting missing evidence into zero."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from data_optimizer.economics.models import (
    MIGRATION,
    RECURRING,
    Breakdown,
    Charge,
    Component,
    ConfigurationCost,
    CostReport,
    CostRequest,
    Footprint,
    LineItem,
    MetricRange,
    Scenario,
    ScenarioResult,
    SpaceChange,
)
from data_optimizer.pricing.models import Rate, Source, Unit
from data_optimizer.profiling.models import fingerprint

ZERO = Decimal(0)
MONEY_QUANTUM = Decimal("0.000001")
RATIO_QUANTUM = Decimal("0.000000000001")
BYTE_UNITS = {"GB_month": Decimal(10**9), "GiB_month": Decimal(2**30)}
UNITS: dict[str, set[Unit]] = {
    "storage": {"GB_month", "GiB_month"},
    "backups": {"GB_month", "GiB_month"},
    "replicas": {"GB_month", "GiB_month"},
    "query_compute": {"compute_hour"},
    "transform_compute": {"compute_hour"},
    "read_requests": {"request"},
    "write_requests": {"request"},
    "retrieval": {"GB", "GiB"},
    "network": {"GB", "GiB"},
    "maintenance": {"hour", "month"},
    "service": {"month"},
    "conversion": {"compute_hour"},
    "temporary_storage": {"GB_month", "GiB_month"},
    "transfer": {"GB", "GiB"},
    "labor": {"hour"},
    "rollback": {"hour"},
}


def rounded(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def ratio(value: Decimal, denominator: Decimal) -> Decimal:
    return (value / denominator).quantize(RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)


def object_sizes(footprint: Footprint) -> tuple[int, ...] | None:
    if footprint.data_file_bytes is None or footprint.metadata_file_bytes is None:
        return None
    return footprint.data_file_bytes + footprint.metadata_file_bytes


def physical_bytes(footprint: Footprint) -> int | None:
    sizes = object_sizes(footprint)
    if sizes is None:
        return None
    copies = footprint.primary_copies + footprint.backup_copies + footprint.replica_copies
    return sum(sizes) * copies


def storage_quantity(footprint: Footprint, component: str, rate: Rate) -> Decimal | None:
    copies = {
        "storage": footprint.primary_copies,
        "backups": footprint.backup_copies,
        "replicas": footprint.replica_copies,
    }[component]
    if copies == 0:
        return ZERO
    sizes = object_sizes(footprint)
    if sizes is None:
        return None
    billable = sum(max(size, rate.minimum_object_bytes) for size in sizes) * copies
    # Steady replacement of retained objects, amortized to one month's operating charge.
    duration = Decimal(max(footprint.retention_days, rate.minimum_duration_days))
    return Decimal(billable) / BYTE_UNITS[rate.unit] * duration / footprint.retention_days


def same_commitment(a: Charge, b: Charge) -> bool:
    def signature(c: Charge) -> tuple[object, ...]:
        return (
            c.component,
            c.basis,
            c.shared_key,
            c.rate_id,
            c.quantity.value if c.quantity else None,
            c.quantity.unit if c.quantity else None,
        )

    return signature(a) == signature(b)


def validate_commitments(scenario: Scenario) -> None:
    b = {c.component: c for c in scenario.baseline.recurring}
    c = {c.component: c for c in scenario.candidate.recurring}
    for component in set(b) | set(c):
        before, after = b.get(component), c.get(component)
        if any(item and item.basis != "usage" for item in (before, after)):
            if before is None or after is None or before.basis != after.basis:
                raise ValueError("fixed_or_provisioned_commitment_cannot_disappear_or_change_basis")
            if before.basis == "shared_fixed" and not same_commitment(before, after):
                raise ValueError("shared_fixed_commitment_must_be_identical")
            if not same_commitment(before, after) and scenario.achievable_capacity_change is None:
                raise ValueError("provisioned_change_requires_achievable_capacity_evidence")


def line_item(
    component: Component,
    charge: Charge | None,
    scenario: Scenario,
    footprint: Footprint | None,
) -> LineItem:
    rates = {rate.id: rate for rate in scenario.prices.rates}
    rate = rates.get(charge.rate_id) if charge and charge.rate_id else None
    missing: list[str] = []
    sources: list[Source] = []
    value: Decimal | None = None
    unit: Unit | None = rate.unit if rate else None
    formula = "quantity / per_quantity * rate_amount * (1 - discount_fraction)"
    if charge is None:
        missing.append("charge_not_supplied")
    if rate is None:
        missing.append("price_rate")
    else:
        sources.append(rate.source)
        if rate.unit not in UNITS[component]:
            raise ValueError(f"unsupported_billing_unit_for_{component}")
    if (
        charge
        and footprint
        and component in {"storage", "backups", "replicas"}
        and charge.basis == "usage"
    ):
        sources.extend((footprint.data_source, footprint.metadata_source))
        if rate:
            value = storage_quantity(footprint, component, rate)
        if value is None:
            missing.append("object_sizes_including_metadata")
        formula = (
            "sum(max(object_bytes, minimum_object_bytes)) * copies / bytes_per_unit "
            "* max(retention_days, minimum_duration_days) / retention_days "
            "/ per_quantity * rate_amount * (1 - discount_fraction)"
        )
    elif charge and charge.quantity:
        sources.append(charge.quantity.source)
        value, unit = charge.quantity.value, charge.quantity.unit
        if rate and rate.unit != unit:
            raise ValueError(f"quantity_price_unit_mismatch_for_{component}")
        if rate and (rate.minimum_duration_days or rate.minimum_object_bytes):
            raise ValueError("manual_storage_quantity_with_minimum_tariff_unsupported")
        if value is None:
            missing.append("quantity")
    else:
        missing.append("quantity")
    amount = None
    if rate and value is not None:
        amount = rounded(value / rate.per_quantity * rate.amount * (1 - rate.discount_fraction))
    return LineItem(
        component=component,
        basis=charge.basis if charge else "unknown",
        formula=formula,
        quantity=value,
        unit=unit,
        rate_id=charge.rate_id if charge else None,
        price_snapshot_id=scenario.prices.snapshot_id,
        rate_amount=rate.amount if rate else None,
        per_quantity=rate.per_quantity if rate else None,
        discount_fraction=rate.discount_fraction if rate else None,
        amount=amount,
        currency=scenario.prices.currency,
        sources=tuple(sources),
        missing_inputs=tuple(f"{component}.{m}" for m in missing),
    )


def breakdown(items: tuple[LineItem, ...]) -> Breakdown:
    known = sum((item.amount for item in items if item.amount is not None), ZERO)
    missing = tuple(m for item in items for m in item.missing_inputs)
    return Breakdown(
        items=items,
        known_subtotal=known,
        total=known if not missing else None,
        missing_inputs=missing,
    )


def operating(config: ConfigurationCost, scenario: Scenario) -> Breakdown:
    charges = {c.component: c for c in config.recurring}
    return breakdown(
        tuple(line_item(c, charges.get(c), scenario, config.footprint) for c in RECURRING)
    )


def calculate_scenario(scenario: Scenario, horizon: int) -> ScenarioResult:
    validate_commitments(scenario)
    baseline, candidate = (
        operating(scenario.baseline, scenario),
        operating(scenario.candidate, scenario),
    )
    charges = {c.component: c for c in scenario.migration.forecast}
    migration = breakdown(tuple(line_item(c, charges.get(c), scenario, None) for c in MIGRATION))
    before, after = (
        physical_bytes(config.footprint) for config in (scenario.baseline, scenario.candidate)
    )
    missing_space = tuple(
        name
        for name, value in (
            ("baseline_object_sizes_including_metadata", before),
            ("candidate_object_sizes_including_metadata", after),
            ("extra_migration_peak_bytes", scenario.migration.extra_peak_bytes),
        )
        if value is None
    )
    space_saved = before - after if before is not None and after is not None else None
    peak = None
    if before is not None and after is not None and scenario.migration.extra_peak_bytes is not None:
        peak = before + after + scenario.migration.extra_peak_bytes
    savings = None
    if baseline.total is not None and candidate.total is not None:
        savings = baseline.total - candidate.total
    recurring = savings * horizon if savings is not None else None
    net = (
        recurring - migration.total
        if recurring is not None and migration.total is not None
        else None
    )
    payback = None
    if savings is None or migration.total is None:
        reason = "missing_cost_inputs"
    elif savings <= 0:
        reason = "nonpositive_monthly_savings"
    elif not scenario.steady_monthly_usage:
        reason = "steady_monthly_usage_not_established"
    else:
        payback, reason = ratio(migration.total, savings), "steady_forecast_only"
    missing = tuple(
        f"{prefix}.{m}"
        for prefix, value in (
            ("baseline", baseline),
            ("candidate", candidate),
            ("migration", migration),
        )
        for m in value.missing_inputs
    ) + tuple(f"space.{m}" for m in missing_space)
    return ScenarioResult(
        name=scenario.name,
        currency=scenario.prices.currency,
        price_snapshot_id=scenario.prices.snapshot_id,
        baseline=baseline,
        candidate=candidate,
        migration_forecast=migration,
        migration_actual_incurred=scenario.migration.actual_incurred,
        space=SpaceChange(
            baseline_physical_bytes=before,
            candidate_physical_bytes=after,
            physical_bytes_saved=space_saved,
            percent_saved=ratio(Decimal(space_saved) * 100, Decimal(before))
            if space_saved is not None and before
            else None,
            migration_peak_bytes=peak,
            missing_inputs=missing_space,
        ),
        monthly_savings=savings,
        monthly_savings_percent=ratio(savings * 100, baseline.total)
        if savings is not None and baseline.total
        else None,
        horizon_recurring_savings=recurring,
        horizon_net_savings=net,
        payback_months=payback,
        payback_reason=reason,
        missing_inputs=missing,
    )


def calculate(request: CostRequest) -> CostReport:
    # Revalidate even callers using Pydantic's unchecked model_copy/update interface.
    request = CostRequest.model_validate(request.model_dump())
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        results = tuple(
            calculate_scenario(scenario, request.horizon_months) for scenario in request.scenarios
        )
        ranges = []
        for metric in ("monthly_savings", "horizon_net_savings", "payback_months"):
            values = [value for result in results if (value := getattr(result, metric)) is not None]
            ranges.append(
                MetricRange(
                    metric=metric,
                    minimum=min(values) if values else None,
                    maximum=max(values) if values else None,
                    known_scenarios=len(values),
                    total_scenarios=len(results),
                )
            )
        report = CostReport(
            report_fingerprint="0" * 64,
            request_fingerprint=fingerprint(request.model_dump(mode="json")),
            request=request,
            results=results,
            ranges=tuple(ranges),
            limitations=(
                "Modeled forecasts, not verified provider bills or realized savings.",
                "Synthetic snapshots are invented offline rates, never live provider quotes.",
                "Monthly inputs represent constant horizon averages; "
                "scenario ranges are not confidence intervals.",
                "Physical space includes declared metadata and retained copies; "
                "peak assumes coexistence of all copies.",
                "No automatic sample scaling, production throughput or cloud latency inference.",
                "Flat linear tariffs only; no tiers, taxes, commitments allocation, "
                "free tiers or currency conversion.",
                "Missing rates or quantities leave totals null; "
                "known subtotals exclude missing charges.",
                "Money rounds per line to six decimal places, half even; "
                "percentages/payback to twelve.",
            ),
        )
        return report.model_copy(
            update={
                "report_fingerprint": fingerprint(
                    report.model_dump(mode="json", exclude={"report_fingerprint"})
                )
            }
        )
