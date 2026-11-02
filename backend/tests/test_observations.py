"""Synthetic attribution arithmetic; no real invoices or production savings."""

import json
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from data_optimizer.economics.models import RECURRING, CostRequest
from data_optimizer.observations.models import ObservationInput, PlanInput
from data_optimizer.observations.service import evaluate, original_scenario
from data_optimizer.optimization.assessment import AssessmentReport

ROOT = Path(__file__).resolve().parents[2]


def arithmetic_report() -> AssessmentReport:
    data = json.loads((ROOT / "docs/evidence/s12-measured-change-report.json").read_text())
    key = data["decision"]["selected_candidate_id"]
    data["request"]["replays_per_month"] = "100"
    scenario = data["costs"][key]["request"]["scenarios"][0]
    scenario["prices"]["currency"] = "USD"
    for rate in scenario["prices"]["rates"]:
        if rate["id"] == "storage":
            rate["amount"] = "1000000000"
        if rate["unit"] == "compute_hour":
            rate["amount"] = "1"
    for config, size in [(scenario["baseline"], 100), (scenario["candidate"], 50)]:
        config["footprint"].update(
            data_file_bytes=[size],
            metadata_file_bytes=[],
            primary_copies=1,
            backup_copies=0,
            replica_copies=0,
        )
        for charge in config["recurring"]:
            if charge["quantity"]:
                charge["quantity"]["value"] = (
                    "100" if charge["component"] == "query_compute" else "0"
                )
    data["costs"][key]["request"] = CostRequest.model_validate(
        data["costs"][key]["request"]
    ).model_dump(mode="json")
    return AssessmentReport.model_validate(data)


def plan(**changes) -> PlanInput:
    return PlanInput(
        expected_version=2,
        state="deployed",
        reference_logical_bytes=100,
        deployed_at=datetime(2026, 8, 1, tzinfo=UTC),
        actual_migration_cost="30",
        source="Synthetic fixture",
        note="No real adoption",
        **changes,
    )


def observation(**changes) -> ObservationInput:
    report = arithmetic_report()
    queries = report.request.conversion.workload.queries
    # Saved fixture has six query IDs, all replayed once.
    data = dict(
        period_start="2026-09-01T00:00:00Z",
        period_end="2026-10-01T00:00:00Z",
        currency="USD",
        logical_volume_bytes=100,
        retained_bytes=50,
        workload_replays="100",
        query_mix={
            q.id: str((Decimal(1) / len(queries)).quantize(Decimal("0.000000000001")))
            for q in queries
        },
        access_quantities={c: "0" for c in RECURRING},
        itemized_costs={c: "0" for c in RECURRING},
        source="Synthetic bill",
        coverage="All eleven costs; identical boundary",
        note="Invented arithmetic",
    )
    data["itemized_costs"]["storage"] = "100"
    data.update(changes)
    return ObservationInput.model_validate(data)


def test_unchanged_representation_lower_usage_is_zero_not_verified_savings():
    report = arithmetic_report()
    bills = {c: "0" for c in RECURRING}
    bills["storage"] = "50"
    bills["query_compute"] = "25"
    value = evaluate(
        report,
        plan(),
        observation(logical_volume_bytes=50, workload_replays="50", itemized_costs=bills),
    )
    assert Decimal(value["modeled_adjusted_baseline"]) == 75
    assert Decimal(value["actual_cost"]) == 75
    assert Decimal(value["modeled_savings"]) == 0
    assert value["attribution"] == "modeled_comparable_usage_not_verified_optimization_savings"
    assert "logical_volume_changed_at_least_20_percent" in value["drift_signals"]


@pytest.mark.parametrize(
    "volume,replays,expected", [(200, "200", "600"), (100, "100", "200"), (0, "0", "0")]
)
def test_synthetic_growth_and_zero(volume, replays, expected):
    value = evaluate(
        arithmetic_report(),
        plan(),
        observation(logical_volume_bytes=volume, workload_replays=replays),
    )
    assert Decimal(value["modeled_adjusted_baseline"]) == Decimal(expected)
    assert Decimal(value["modeled_savings"]) == Decimal(expected) - 100


def test_partial_period_prorates_storage_but_uses_period_replay_counts():
    value = evaluate(
        arithmetic_report(),
        plan(),
        observation(period_end="2026-09-16T00:00:00Z", workload_replays="50"),
    )
    assert Decimal(value["period_months_30_days"]) == Decimal("0.5")
    assert Decimal(value["modeled_adjusted_baseline"]) == 100
    assert Decimal(value["original_projected_cost"]) == 75


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"itemized_costs": {"storage": "10"}}, "incomplete_itemized_bill"),
        ({"currency": "EUR"}, "currency_mismatch_no_fx_conversion"),
        ({"logical_volume_bytes": None}, "logical_volume_missing"),
        ({"query_mix": {"other": "1"}}, "query_mix_missing_or_changed"),
    ],
)
def test_unknowns_and_incompatible_evidence_abstain(change, reason):
    value = evaluate(arithmetic_report(), plan(), observation(**change))
    assert value["modeled_savings"] is None
    assert reason in value["missing_inputs"]


def test_negative_savings_and_excluded_revision():
    obs = observation(itemized_costs={c: "100" for c in RECURRING})
    value = evaluate(arithmetic_report(), plan(), obs)
    assert Decimal(value["modeled_savings"]) == -900
    assert (
        evaluate(arithmetic_report(), plan(), obs.model_copy(update={"excluded": True}))[
            "modeled_savings"
        ]
        is None
    )


def test_revert_invalidates_period_beyond_reader_reversal():
    p = plan().model_copy(
        update={"state": "reverted", "reverted_at": datetime(2026, 9, 15, tzinfo=UTC)}
    )
    value = evaluate(arithmetic_report(), p, observation())
    assert value["modeled_savings"] is None
    assert "period_outside_deployment" in value["missing_inputs"]


def test_fixed_commitments_do_not_scale_with_lower_usage():
    report = arithmetic_report()
    key = report.decision.selected_candidate_id
    data = report.model_dump(mode="json")
    base = data["costs"][key]["request"]["scenarios"][0]["baseline"]
    for c in base["recurring"]:
        if c["component"] == "query_compute":
            c["basis"] = "provisioned"
    value = evaluate(
        AssessmentReport.model_validate(data),
        plan(),
        observation(logical_volume_bytes=50, workload_replays="50"),
    )
    assert Decimal(value["modeled_adjusted_baseline"]) == 150


def test_original_billing_minima_not_silently_scaled():
    report = arithmetic_report()
    key = report.decision.selected_candidate_id
    data = report.model_dump(mode="json")
    data["costs"][key]["request"]["scenarios"][0]["prices"]["rates"][0]["minimum_object_bytes"] = (
        100
    )
    value = evaluate(AssessmentReport.model_validate(data), plan(), observation())
    assert value["modeled_adjusted_baseline"] is None
    assert "minimum_billing_topology_unsupported" in value["missing_inputs"]


def test_decimal_context_independence_and_inputs_not_mutated():
    report, obs, p = arithmetic_report(), observation(), plan()
    before = report.model_dump_json()
    expected = evaluate(report, p, obs)
    with localcontext() as ctx:
        ctx.prec = 6
        assert evaluate(report, p, obs) == expected
    assert report.model_dump_json() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"period_end": "2026-09-01T00:00:00Z"},
        {"period_start": "2026-09-01T00:00:00"},
        {"query_mix": {"scan": "0.2"}},
        {"retained_bytes": -1},
        {"itemized_costs": {"storage": "NaN"}},
        {"access_quantities": {"bad": "3"}},
        {"expected_version": 1},
        {"period_end": "2099-01-01T00:00:00Z"},
    ],
)
def test_bad_observations_rejected(changes):
    with pytest.raises(ValidationError):
        observation(**changes)


def test_guidance_cannot_be_an_adopted_change():
    report = arithmetic_report()
    report = report.model_copy(
        update={"decision": report.decision.model_copy(update={"outcome": "keep_current"})}
    )
    with pytest.raises(ValueError):
        original_scenario(report)


def test_schema_drift_suppresses_counterfactual_and_input_drift_is_advisory():
    report = arithmetic_report()
    changed = observation(schema_fingerprint="f" * 64, input_fingerprint="e" * 64)
    result = evaluate(report, plan(), changed)
    assert result["modeled_adjusted_baseline"] is None
    assert result["modeled_savings"] is None
    assert "schema_changed_reassess" in result["drift_signals"]
    assert "input_changed_reassess" in result["drift_signals"]


def test_extreme_volume_and_short_period_return_unknown_instead_of_validation_crash():
    result = evaluate(
        arithmetic_report(),
        plan(),
        observation(
            logical_volume_bytes=2**63 - 1,
            workload_replays="999999999999999999",
            period_end="2026-09-01T00:00:00.000001Z",
        ),
    )
    assert result["modeled_savings"] is None
    assert "quantity_model_range_exceeded" in result["missing_inputs"]
