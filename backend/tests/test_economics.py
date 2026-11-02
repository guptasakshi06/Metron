"""Independent arithmetic examples, billing boundaries and missing-evidence behavior."""

from __future__ import annotations

import copy
import json
from decimal import Decimal, Inexact, localcontext
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from data_optimizer.economics.models import CostRequest
from data_optimizer.economics.service import calculate
from data_optimizer.pricing.models import PriceSnapshot
from data_optimizer.profiling.models import fingerprint

REPO = Path(__file__).resolve().parents[2]
D = Decimal


@pytest.fixture
def payload() -> dict[str, Any]:
    return json.loads((REPO / "examples/s07-cost-request.json").read_bytes())


def result(payload: dict[str, Any]) -> Any:
    return calculate(CostRequest.model_validate(payload)).results[0]


def find(items: list[dict[str, Any]], component: str) -> dict[str, Any]:
    return next(item for item in items if item.get("component", item.get("id")) == component)


def test_documented_example_reconciles_every_total(payload: dict[str, Any]) -> None:
    request = CostRequest.model_validate(payload)
    report = calculate(request)
    r = report.results[0]
    assert r.baseline.total == 300
    assert r.candidate.total == 180
    assert r.migration_forecast.total == 300
    assert r.monthly_savings == 120
    assert r.monthly_savings_percent == 40
    assert r.payback_months == D("2.5")
    assert r.horizon_net_savings == 1140
    assert r.space.physical_bytes_saved == 650_000_000_000
    assert r.space.percent_saved == 65
    assert r.space.migration_peak_bytes == 1_350_000_000_000
    for costs in (r.baseline, r.candidate, r.migration_forecast):
        assert costs.total == sum(line.amount for line in costs.items)
        assert all(line.unit and line.sources and line.price_snapshot_id for line in costs.items)
        assert not costs.missing_inputs
    assert report.report_fingerprint == fingerprint(
        report.model_dump(mode="json", exclude={"report_fingerprint"})
    )
    assert report == calculate(request)
    assert report == type(report).model_validate_json(report.model_dump_json())


def test_price_fixture_matches_embedded_snapshot_and_is_immutable(payload: dict[str, Any]) -> None:
    prices = PriceSnapshot.model_validate_json(
        (REPO / "examples/s07-synthetic-prices.json").read_bytes()
    )
    assert prices == CostRequest.model_validate(payload).scenarios[0].prices
    with pytest.raises(ValidationError):
        prices.rates[0].amount = D(999)
    assert isinstance(prices.rates, tuple)
    updated = prices.model_copy(update={"region": "different"})
    assert prices.snapshot_id != updated.snapshot_id


@pytest.mark.parametrize(
    "change",
    [
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"amount": "-1"},
        {"discount_fraction": "1.001"},
        {"discount_fraction": "-0.1"},
        {"per_quantity": "0"},
        {"unit": "GB_per_second"},
        {"amount": "0.0000000000001"},
    ],
)
def test_invalid_price_rejected(payload: dict[str, Any], change: dict[str, Any]) -> None:
    payload["scenarios"][0]["prices"]["rates"][0].update(change)
    with pytest.raises(ValidationError):
        CostRequest.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("effective_at", "2026-11-02T00:00:00"),
        ("retrieved_at", "2026-11-02T00:00:00+05:30"),
        ("currency", "usd"),
        ("source", "live_provider"),
    ],
)
def test_price_metadata_rejected(
    payload: dict[str, Any],
    field: str,
    value: str,
) -> None:
    payload["scenarios"][0]["prices"][field] = value
    with pytest.raises(ValidationError):
        CostRequest.model_validate(payload)


def test_synthetic_rates_cannot_be_relabelled(payload: dict[str, Any]) -> None:
    payload["scenarios"][0]["prices"]["source"] = "user_supplied"
    with pytest.raises(ValidationError, match="relabelled"):
        CostRequest.model_validate(payload)


@pytest.mark.parametrize("discount,expected", [("0", "100"), ("0.25", "75"), ("1", "0")])
def test_contract_discounts(payload: dict[str, Any], discount: str, expected: str) -> None:
    payload["scenarios"][0]["prices"]["rates"][0]["discount_fraction"] = discount
    line = result(payload).baseline.items[0]
    assert line.amount == D(expected)
    assert line.discount_fraction == D(discount)


def test_minimum_object_size_and_duration_apply_to_each_copy_and_metadata(
    payload: dict[str, Any],
) -> None:
    s = payload["scenarios"][0]
    rate = s["prices"]["rates"][0]
    rate.update(minimum_object_bytes=128000, minimum_duration_days=90)
    # The temporary storage tariff has no minimum: explicit byte-month estimate is supported.
    temp = copy.deepcopy(rate)
    temp.update(id="temporary", minimum_object_bytes=0, minimum_duration_days=0)
    s["prices"]["rates"].append(temp)
    find(s["migration"]["forecast"], "temporary_storage")["rate_id"] = "temporary"
    for cfg in (s["baseline"], s["candidate"]):
        cfg["footprint"].update(
            data_file_bytes=[1, 256000],
            metadata_file_bytes=[10],
            retention_days=30,
            primary_copies=2,
            backup_copies=1,
            replica_copies=1,
        )
    r = result(payload)
    # (128000 + 256000 + 128000) bytes * 2 copies * 3 duration / 1e9 * $0.1
    assert r.baseline.items[0].amount == D("0.000307")
    assert r.baseline.items[7].amount == D("0.000154")
    assert r.baseline.items[8].amount == D("0.000154")
    assert r.space.baseline_physical_bytes == (1 + 256000 + 10) * 4
    assert r.space.migration_peak_bytes == (1 + 256000 + 10) * 8
    assert r.baseline.total == sum(i.amount for i in r.baseline.items)


def test_gb_gib_and_request_billing_units(payload: dict[str, Any]) -> None:
    s = payload["scenarios"][0]
    s["prices"]["rates"][0]["unit"] = "GiB_month"
    find(s["migration"]["forecast"], "temporary_storage")["quantity"]["unit"] = "GiB_month"
    s["baseline"]["footprint"]["data_file_bytes"] = [2**30]
    r = result(payload)
    assert r.baseline.items[0].amount == D("0.1")
    assert r.baseline.items[3].quantity == 10000000
    assert r.baseline.items[3].per_quantity == 1000
    assert r.baseline.items[3].amount == 10


def test_unchanged_provisioned_capacity_does_not_save_cash(payload: dict[str, Any]) -> None:
    s = payload["scenarios"][0]
    s["candidate"]["recurring"] = copy.deepcopy(s["baseline"]["recurring"])
    for cfg in (s["baseline"], s["candidate"]):
        charge = cfg["recurring"][0]
        charge.update(
            basis="provisioned",
            quantity={
                "value": "1000",
                "unit": "GB_month",
                "source": cfg["footprint"]["data_source"],
            },
        )
    r = result(payload)
    assert r.space.physical_bytes_saved > 0
    assert r.monthly_savings == 0
    assert r.payback_months is None
    assert r.horizon_net_savings == -300
    s["candidate"]["recurring"][0]["quantity"]["value"] = "350"
    with pytest.raises(ValueError, match="achievable_capacity"):
        result(payload)
    s["achievable_capacity_change"] = dict(
        kind="assumption",
        reference="capacity-plan-v1",
        note="Customer can reduce the billed provisioned capacity to 350GB; scenario assumption.",
    )
    assert result(payload).monthly_savings == 65


@pytest.mark.parametrize("mutation", ["remove", "rate", "quantity", "key", "basis"])
def test_shared_fixed_commitments_cannot_disappear_or_shrink(
    payload: dict[str, Any],
    mutation: str,
) -> None:
    s = payload["scenarios"][0]
    for cfg in (s["baseline"], s["candidate"]):
        charge = cfg["recurring"][-1]
        charge.update(basis="shared_fixed", shared_key="existing-plan")
    assert result(payload).monthly_savings == 120
    charge = s["candidate"]["recurring"][-1]
    if mutation == "remove":
        s["candidate"]["recurring"].pop()
    elif mutation == "rate":
        charge["rate_id"] = None
    elif mutation == "quantity":
        charge["quantity"]["value"] = "0"
    elif mutation == "key":
        charge["shared_key"] = "different-plan"
    else:
        charge.update(basis="usage", shared_key=None)
    with pytest.raises(ValueError, match="commitment"):
        result(payload)


@pytest.mark.parametrize("missing", ["quantity", "rate", "component", "metadata", "data"])
def test_missing_never_becomes_zero(payload: dict[str, Any], missing: str) -> None:
    s = payload["scenarios"][0]
    if missing == "quantity":
        s["candidate"]["recurring"][1]["quantity"]["value"] = None
    elif missing == "rate":
        s["candidate"]["recurring"][1]["rate_id"] = "not_in_catalog"
    elif missing == "component":
        s["candidate"]["recurring"].pop(1)
    else:
        s["candidate"]["footprint"][f"{missing}_file_bytes"] = None
    r = result(payload)
    assert r.candidate.total is None
    assert r.candidate.known_subtotal is not None
    assert r.monthly_savings is None
    assert r.horizon_net_savings is None
    assert r.payback_months is None
    assert r.missing_inputs


def test_missing_migration_does_not_hide_known_recurring_savings(payload: dict[str, Any]) -> None:
    payload["scenarios"][0]["migration"]["forecast"].pop()
    r = result(payload)
    assert r.monthly_savings == 120
    assert r.horizon_recurring_savings == 1440
    assert r.migration_forecast.total is None
    assert r.horizon_net_savings is None
    assert r.payback_months is None


@pytest.mark.parametrize(
    "compute,expected,payback", [("120", "120", "2.5"), ("240", "0", None), ("300", "-60", None)]
)
def test_positive_zero_negative_savings(
    payload: dict[str, Any],
    compute: str,
    expected: str,
    payback: str | None,
) -> None:
    payload["scenarios"][0]["candidate"]["recurring"][1]["quantity"]["value"] = compute
    r = result(payload)
    assert r.monthly_savings == D(expected)
    assert r.payback_months == (D(payback) if payback is not None else None)
    assert r.horizon_net_savings == D(expected) * 12 - 300


def test_zero_baseline_has_no_percentage_or_payback(payload: dict[str, Any]) -> None:
    for rate in payload["scenarios"][0]["prices"]["rates"]:
        rate["amount"] = "0"
    r = result(payload)
    assert r.baseline.total == r.candidate.total == r.monthly_savings == 0
    assert r.monthly_savings_percent is None
    assert r.payback_months is None


def test_zero_physical_baseline_and_zero_migration(payload: dict[str, Any]) -> None:
    s = payload["scenarios"][0]
    s["baseline"]["footprint"]["data_file_bytes"] = []
    for c in s["migration"]["forecast"]:
        c["quantity"]["value"] = "0"
    r = result(payload)
    assert r.space.baseline_physical_bytes == 0
    assert r.space.percent_saved is None
    assert r.monthly_savings == 20
    assert r.payback_months == 0
    assert r.horizon_net_savings == 240


def test_actuals_separate_and_nonsteady_payback_not_fabricated(payload: dict[str, Any]) -> None:
    s = payload["scenarios"][0]
    s["migration"].update(
        actual_incurred="500",
        actual_source=dict(
            kind="user_supplied", reference="manual-bill", note="Unverified user supplied actual."
        ),
    )
    s["steady_monthly_usage"] = False
    r = result(payload)
    assert r.migration_actual_incurred == 500
    assert r.migration_forecast.total == 300
    assert r.horizon_net_savings == 1140
    assert r.payback_months is None
    assert r.payback_reason == "steady_monthly_usage_not_established"


def test_ranges_show_known_coverage_and_full_assumptions(payload: dict[str, Any]) -> None:
    alternative = copy.deepcopy(payload["scenarios"][0])
    alternative["name"] = "higher_usage"
    alternative["candidate"]["recurring"][1]["quantity"]["value"] = "180"
    payload["scenarios"].append(alternative)
    unknown = copy.deepcopy(alternative)
    unknown["name"] = "unknown_price"
    unknown["candidate"]["recurring"][0]["rate_id"] = None
    payload["scenarios"].append(unknown)
    report = calculate(CostRequest.model_validate(payload))
    monthly, net, payback = report.ranges
    assert (monthly.minimum, monthly.maximum, monthly.known_scenarios, monthly.total_scenarios) == (
        60,
        120,
        2,
        3,
    )
    assert (net.minimum, net.maximum) == (420, 1140)
    assert (payback.minimum, payback.maximum) == (D("2.5"), 5)
    assert report.request.scenarios[1].assumption


def test_line_rounding_is_half_even_and_independent_of_global_decimal_context(
    payload: dict[str, Any],
) -> None:
    s = payload["scenarios"][0]
    find(s["prices"]["rates"], "compute")["amount"] = "0.0000005"
    s["baseline"]["recurring"][1]["quantity"]["value"] = "1"
    s["candidate"]["recurring"][1]["quantity"]["value"] = "3"
    with localcontext() as ctx:
        ctx.prec = 4
        ctx.traps[Inexact] = True
        r = result(payload)
    assert r.baseline.items[1].amount == D("0.000000")
    assert r.candidate.items[1].amount == D("0.000002")


@pytest.mark.parametrize(
    "mutation",
    [
        "units",
        "component_unit",
        "duplicate",
        "migration_duplicate",
        "logical",
        "retention",
        "negative_bytes",
        "minimum_manual",
    ],
)
def test_invalid_comparison_contracts(payload: dict[str, Any], mutation: str) -> None:
    s = payload["scenarios"][0]
    if mutation == "units":
        s["candidate"]["recurring"][1]["quantity"]["unit"] = "month"
    elif mutation == "component_unit":
        s["candidate"]["recurring"][1]["rate_id"] = "labor"
    elif mutation == "duplicate":
        s["candidate"]["recurring"][1] = copy.deepcopy(s["candidate"]["recurring"][0])
    elif mutation == "migration_duplicate":
        s["migration"]["forecast"][1] = copy.deepcopy(s["migration"]["forecast"][0])
    elif mutation == "logical":
        s["candidate"]["footprint"]["logical_fingerprint"] = "b" * 64
    elif mutation == "retention":
        s["candidate"]["footprint"]["retention_days"] = 30
    elif mutation == "negative_bytes":
        s["candidate"]["footprint"]["data_file_bytes"] = [-1]
    else:
        s["prices"]["rates"][0]["minimum_object_bytes"] = 128000
    with pytest.raises(ValueError):
        result(payload)


def test_arithmetic_invariants_over_volume_and_horizon(payload: dict[str, Any]) -> None:
    # Independent grid: linear storage savings and horizon accounting, no timing assertions.
    for baseline_gb in (0, 1, 1000):
        for candidate_gb in (0, 2, 350):
            for months in (1, 12, 120):
                s = payload["scenarios"][0]
                payload["horizon_months"] = months
                s["baseline"]["footprint"]["data_file_bytes"] = [baseline_gb * 10**9]
                s["candidate"]["footprint"]["data_file_bytes"] = [candidate_gb * 10**9]
                r = result(payload)
                expected = D(baseline_gb - candidate_gb) / 10 + 55
                assert r.monthly_savings == expected
                assert r.horizon_net_savings == expected * months - 300
                assert r.space.physical_bytes_saved == (baseline_gb - candidate_gb) * 10**9


def test_growth_and_price_scenarios_are_explicit_forecasts(payload: dict[str, Any]) -> None:
    growth = copy.deepcopy(payload["scenarios"][0])
    growth["name"] = "growth_average"
    growth["assumption"] = (
        "Twice the retained inventory at the horizon average; same measured shape."
    )
    growth["steady_monthly_usage"] = False
    for cfg in (growth["baseline"], growth["candidate"]):
        cfg["footprint"]["data_file_bytes"][0] *= 2
        cfg["footprint"]["data_source"].update(
            kind="assumption",
            note="Projected horizon-average inventory, not measured future bytes.",
        )
    higher_price = copy.deepcopy(payload["scenarios"][0])
    higher_price["name"] = "higher_storage_price"
    higher_price["assumption"] = "Invented higher storage rate for sensitivity analysis."
    higher_price["prices"]["rates"][0]["amount"] = "0.3"
    payload["scenarios"].extend([growth, higher_price])
    report = calculate(CostRequest.model_validate(payload))
    assert [r.monthly_savings for r in report.results] == [120, 185, 250]
    assert report.results[1].payback_months is None
    assert report.results[0].price_snapshot_id != report.results[2].price_snapshot_id
    assert report.ranges[0].minimum == 120
    assert report.ranges[0].maximum == 250


@pytest.mark.parametrize("field", ["primary_copies", "backup_copies", "replica_copies"])
def test_required_copies_cannot_be_removed_for_savings(
    payload: dict[str, Any],
    field: str,
) -> None:
    payload["scenarios"][0]["baseline"]["footprint"][field] += 1
    with pytest.raises(ValueError, match="required_copies"):
        result(payload)


def test_missing_physical_bytes_does_not_hide_known_provisioned_cost(
    payload: dict[str, Any],
) -> None:
    s = payload["scenarios"][0]
    for cfg in (s["baseline"], s["candidate"]):
        cfg["footprint"]["data_file_bytes"] = None
        cfg["recurring"][0].update(
            basis="provisioned",
            quantity={
                "value": "1000",
                "unit": "GB_month",
                "source": cfg["footprint"]["data_source"],
            },
        )
    r = result(payload)
    assert r.monthly_savings == 55
    assert r.space.physical_bytes_saved is None
    assert r.space.migration_peak_bytes is None
    assert "space.baseline_object_sizes_including_metadata" in r.missing_inputs
