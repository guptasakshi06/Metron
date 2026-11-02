"""Comparable usage counterfactuals, never verified optimization savings."""

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Any

from data_optimizer.economics.models import RECURRING, Scenario
from data_optimizer.economics.service import operating, rounded
from data_optimizer.observations.models import ObservationInput, PlanInput
from data_optimizer.optimization.assessment import AssessmentReport
from data_optimizer.pricing.models import Source

ZERO = Decimal(0)


def original_scenario(report: AssessmentReport) -> Scenario:
    selected = report.decision.selected_candidate_id
    cost = report.costs.get(selected or "")
    if report.decision.outcome != "change" or cost is None:
        raise ValueError("adoption_requires_tested_change_with_cost_evidence")
    return next(s for s in cost.request.scenarios if s.name == report.request.policy.scenario)


def evaluate(report: AssessmentReport, plan: PlanInput, obs: ObservationInput) -> dict[str, Any]:
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        return _evaluate(report, plan, obs)


def _evaluate(report: AssessmentReport, plan: PlanInput, obs: ObservationInput) -> dict[str, Any]:
    scenario = original_scenario(report)
    delta = obs.period_end - obs.period_start
    seconds = Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000
    fraction = seconds / 2592000
    issues = []
    drift = []
    if report.profile:
        if obs.schema_fingerprint and obs.schema_fingerprint != report.profile.schema_fingerprint:
            drift.append("schema_changed_reassess")
        if obs.input_fingerprint and obs.input_fingerprint != report.profile.input_fingerprint:
            drift.append("input_changed_reassess")
    source = Source(
        kind="assumption",
        reference="s13.linear_usage_v1",
        note=(
            "Original prices, retention, copies and representation; linear logical-volume scaling. "
            "30-day modeled month; observed period quantities. Not a verified counterfactual bill."
        ),
    )
    volume = (
        Decimal(obs.logical_volume_bytes) / plan.reference_logical_bytes
        if obs.logical_volume_bytes is not None
        else None
    )
    if volume is None:
        issues.append("logical_volume_missing")
    elif abs(volume - 1) >= Decimal("0.2"):
        drift.append("logical_volume_changed_at_least_20_percent")
    conversion = report.request.conversion
    queries = conversion.workload.queries if conversion else ()
    expected_mix = {q.id: Decimal(1) / len(queries) for q in queries}
    # Replays execute each query once; compare fractions without repeating decimal thirds.
    mix_matches = (
        bool(queries)
        and set(obs.query_mix) == set(expected_mix)
        and all(
            abs(obs.query_mix[k] - v) <= Decimal("0.000000000001") for k, v in expected_mix.items()
        )
    )
    if not mix_matches:
        issues.append("query_mix_missing_or_changed")
        drift.append("workload_mix_unvalidated_reassess")
    reference_replays = report.request.replays_per_month
    replay_ratio = (
        obs.workload_replays / fraction / reference_replays
        if obs.workload_replays is not None and reference_replays
        else None
    )
    if replay_ratio is not None and abs(replay_ratio - 1) >= Decimal("0.2"):
        drift.append("access_rate_changed_at_least_20_percent")
    data = scenario.baseline.model_dump(mode="json")
    footprint = data["footprint"]
    # Scale physical objects, preserving topology. Minimum-size tariffs invalidate this model.
    minima = any(r.minimum_object_bytes or r.minimum_duration_days for r in scenario.prices.rates)
    if minima:
        issues.append("minimum_billing_topology_unsupported")
    for key in ("data_file_bytes", "metadata_file_bytes"):
        sizes = footprint[key]
        footprint[key] = (
            [int((Decimal(n) * volume).to_integral_value(rounding=ROUND_HALF_EVEN)) for n in sizes]
            if volume is not None and sizes is not None
            else None
        )
    for key in ("data_file_bytes", "metadata_file_bytes"):
        if footprint[key] and any(n > 2**63 - 1 for n in footprint[key]):
            footprint[key] = None
            issues.append("logical_volume_model_range_exceeded")
    footprint["data_source"] = footprint["metadata_source"] = source.model_dump(mode="json")
    for charge in data["recurring"]:
        component = charge["component"]
        quantity = charge["quantity"]
        if quantity is None:
            continue
        original = Decimal(quantity["value"]) if quantity["value"] is not None else None
        if charge["basis"] != "usage":
            value = original  # Unchanged provisioned/shared capacity does not scale with usage.
        elif component == "query_compute":
            value = (
                original * replay_ratio * volume
                if original is not None
                and replay_ratio is not None
                and volume is not None
                and mix_matches
                else None
            )
        else:
            observed = obs.access_quantities.get(component)
            value = observed / fraction if observed is not None else None
        if value is not None and value >= Decimal("1e18"):
            issues.append("quantity_model_range_exceeded")
            value = None
        quantity["value"] = (
            str(value.quantize(Decimal("0.000000000001"))) if value is not None else None
        )
        quantity["source"] = source.model_dump(mode="json")
    baseline_config = type(scenario.baseline).model_validate(data)
    baseline = operating(baseline_config, scenario)
    items = [
        {
            "component": item.component,
            "amount": str(rounded(item.amount * fraction)) if item.amount is not None else None,
            "unit": item.unit,
            "monthly_quantity": str(item.quantity) if item.quantity is not None else None,
        }
        for item in baseline.items
    ]
    if baseline.missing_inputs:
        issues.extend(baseline.missing_inputs)
    modeled = (
        sum((Decimal(i["amount"]) for i in items if i["amount"] is not None), ZERO)
        if baseline.total is not None
        and not minima
        and mix_matches
        and "schema_changed_reassess" not in drift
        else None
    )
    missing_bills = [c for c in RECURRING if obs.itemized_costs.get(c) is None]
    actual = (
        sum((obs.itemized_costs[c] or ZERO for c in RECURRING), ZERO) if not missing_bills else None
    )
    if missing_bills:
        issues.append("incomplete_itemized_bill")
    currency_matches = obs.currency == scenario.prices.currency
    if not currency_matches:
        issues.append("currency_mismatch_no_fx_conversion")
    deployed = (
        plan.deployed_at is not None
        and obs.period_start >= plan.deployed_at
        and (plan.reverted_at is None or obs.period_end <= plan.reverted_at)
    )
    if not deployed:
        issues.append("period_outside_deployment")
    savings = (
        rounded(modeled - actual)
        if modeled is not None
        and actual is not None
        and currency_matches
        and deployed
        and "schema_changed_reassess" not in drift
        and not obs.excluded
        else None
    )
    forecast = operating(scenario.candidate, scenario)
    projected = rounded(forecast.total * fraction) if forecast.total is not None else None
    if obs.retained_bytes is None:
        drift.append("retained_bytes_missing")
    if volume is not None and obs.retained_bytes is not None:
        fp = scenario.candidate.footprint
        sizes = (fp.data_file_bytes or ()) + (fp.metadata_file_bytes or ())
        expected = Decimal(sum(sizes) * (fp.primary_copies + fp.backup_copies + fp.replica_copies))
        expected *= volume
        if expected and abs(Decimal(obs.retained_bytes) / expected - 1) >= Decimal("0.2"):
            drift.append("retained_bytes_diverged_at_least_20_percent")
    if (obs.period_end - scenario.prices.effective_at).days >= 90:
        drift.append("original_price_snapshot_at_least_90_days_old")
    return {
        "calculation_version": "s13.linear_usage_v1",
        "evidence": "user_supplied_not_provider_verified",
        "attribution": "modeled_comparable_usage_not_verified_optimization_savings",
        "actual_currency": obs.currency,
        "model_currency": scenario.prices.currency,
        "period_months_30_days": str(fraction),
        "actual_cost": str(actual) if actual is not None else None,
        "actual_known_subtotal": str(
            sum((v for v in obs.itemized_costs.values() if v is not None), ZERO)
        ),
        "original_projected_cost": str(projected) if projected is not None else None,
        "modeled_adjusted_baseline": str(modeled) if modeled is not None else None,
        "modeled_savings": str(savings) if savings is not None else None,
        "baseline_items": items,
        "missing_inputs": issues,
        "drift_signals": drift,
        "price_snapshot_id": scenario.prices.snapshot_id,
        "assumptions": [
            source.note,
            "Same logical content, retention, required copies, region and "
            "availability boundary must be confirmed against the bill.",
            "Query CPU scales linearly with volume/replays only for unchanged mix; "
            "this is an unvalidated model. Non-storage usage requires explicit quantities.",
            "Projection uses original usage; adjusted baseline uses observed usage. "
            "Lower usage alone is not attributed to optimization.",
        ],
    }
