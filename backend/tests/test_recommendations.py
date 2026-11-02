"""Decision-path fixtures use saved local evidence and explicitly synthetic costs."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from data_optimizer.benchmarking.models import BenchmarkReport
from data_optimizer.economics.benchmark import bind_benchmark
from data_optimizer.economics.models import CostReport, CostRequest
from data_optimizer.economics.service import calculate
from data_optimizer.profiling.models import fingerprint
from data_optimizer.recommendations.models import DecisionPolicy
from data_optimizer.recommendations.service import decide

REPO = Path(__file__).resolve().parents[2]
POLICY = DecisionPolicy(scenario="documented_example")


def rehash(report: BenchmarkReport) -> BenchmarkReport:
    return report.model_copy(
        update={
            "report_fingerprint": fingerprint(
                report.model_dump(mode="json", exclude={"report_fingerprint"})
            )
        }
    )


@pytest.fixture
def matrix() -> BenchmarkReport:
    return BenchmarkReport.model_validate_json(
        (REPO / "docs/evidence/s06-benchmark-fresh.json").read_bytes()
    )


def template() -> CostRequest:
    return CostRequest.model_validate_json((REPO / "examples/s07-cost-request.json").read_bytes())


def cost_set(matrix: BenchmarkReport, mode: str = "change") -> dict[str, CostReport]:
    result = {}
    for manifest in matrix.manifests:
        if manifest.configuration.baseline:
            continue
        bound = bind_benchmark(template(), matrix, manifest.key, Decimal(1000))
        payload = bound.model_dump(mode="json")
        scenario = payload["scenarios"][0]
        # Deliberate synthetic user scenarios: independent of noisy measurement timings.
        for side, amount in (
            ("baseline", "100"),
            ("candidate", "10" if mode == "change" else "200"),
        ):
            for charge in scenario[side]["recurring"]:
                if charge["component"] == "query_compute":
                    charge["quantity"]["value"] = None if mode == "missing" else amount
        result[manifest.key] = calculate(CostRequest.model_validate(payload))
    return result


@pytest.mark.parametrize(
    "mode,outcome",
    [("change", "change"), ("keep", "keep_current"), ("missing", "insufficient_evidence")],
)
def test_three_decision_paths(matrix: BenchmarkReport, mode: str, outcome: str) -> None:
    decision = decide(matrix, cost_set(matrix, mode), POLICY)
    assert decision.outcome == outcome
    assert decision.baseline_candidate_id in {e.candidate_id for e in decision.candidates}
    assert decision.decision_fingerprint == fingerprint(
        decision.model_dump(mode="json", exclude={"decision_fingerprint"})
    )
    if outcome == "change":
        eligible = [e for e in decision.candidates if e.feasibility == "feasible"]
        assert (
            decision.best_tested_candidate_id
            == min(eligible, key=lambda e: (e.horizon_total, e.candidate_id)).candidate_id
        )
        assert all(e.evidence_ids and e.costs for e in eligible)
        assert decision.tradeoff_candidate_ids
    elif outcome == "insufficient_evidence":
        assert decision.selected_candidate_id is None


def test_materiality_and_migration_prevent_forced_change(matrix: BenchmarkReport) -> None:
    decision = decide(
        matrix,
        cost_set(matrix),
        POLICY.model_copy(
            update={
                "minimum_net_savings": Decimal("1000000"),
            }
        ),
    )
    assert decision.outcome == "keep_current"
    assert decision.best_tested_candidate_id != decision.selected_candidate_id


@pytest.mark.parametrize(
    "update,requirement,status",
    [
        ({"allowed_formats": ("ndjson",)}, "reader_compatibility", "violated"),
        ({"allowed_codecs": ("original",)}, "reader_compatibility", "violated"),
        ({"retention_days": 1000}, "retention", "violated"),
        ({"freshness_seconds": 60}, "freshness", "untested"),
        ({"required_capabilities": ("transactions",)}, "capability:transactions", "untested"),
        (
            {"required_capabilities": ("analytical_snapshot",)},
            "capability:analytical_snapshot",
            "passed",
        ),
    ],
)
def test_constraint_coverage(
    matrix: BenchmarkReport, update: dict[str, object], requirement: str, status: str
) -> None:
    policy = DecisionPolicy.model_validate({**POLICY.model_dump(), **update})
    decision = decide(matrix, cost_set(matrix), policy)
    assert any(
        c.requirement == requirement and c.status == status
        for e in decision.candidates
        for c in e.coverage
    )
    if status == "untested":
        assert decision.outcome == "insufficient_evidence"


def test_failed_candidate_never_looks_fast_or_free(matrix: BenchmarkReport) -> None:
    key = next(m.key for m in matrix.manifests if not m.configuration.baseline)
    trials = tuple(
        t.model_copy(update={"status": "timeout", "observation": None}) if t.candidate == key else t
        for t in matrix.trials
    )
    changed = rehash(matrix.model_copy(update={"trials": trials}))
    decision = decide(changed, cost_set(changed), POLICY)
    candidate = next(e for e in decision.candidates if e.candidate_id == key)
    assert candidate.feasibility == "excluded"
    assert candidate.workload_seconds is None
    assert key != decision.selected_candidate_id


def test_partial_repeat_coverage_abstains(matrix: BenchmarkReport) -> None:
    changed = rehash(matrix.model_copy(update={"trials": matrix.trials[:-1]}))
    assert decide(changed, cost_set(changed), POLICY).outcome == "insufficient_evidence"


def test_metadata_and_startup_never_claim_savings() -> None:
    decision = decide(None, {}, POLICY)
    assert decision.outcome == "insufficient_evidence"
    assert decision.candidates == ()
    assert decision.next_questions


@pytest.mark.parametrize("damage", ["hash", "cost", "candidate", "boundary", "duplicate"])
def test_incompatible_or_tampered_evidence_rejected(matrix: BenchmarkReport, damage: str) -> None:
    costs = cost_set(matrix)
    key = next(iter(costs))
    if damage == "hash":
        matrix = matrix.model_copy(update={"report_fingerprint": "a" * 64})
    elif damage == "cost":
        costs[key] = costs[key].model_copy(update={"report_fingerprint": "a" * 64})
    elif damage == "candidate":
        costs["a" * 64] = costs.pop(key)
    elif damage == "boundary":
        payload = costs[key].request.model_dump(mode="json")
        payload["horizon_months"] = 5
        costs[key] = calculate(CostRequest.model_validate(payload))
    else:
        matrix = rehash(matrix.model_copy(update={"trials": matrix.trials + (matrix.trials[0],)}))
    with pytest.raises(ValueError):
        decide(matrix, costs, POLICY)


def with_workload(matrix: BenchmarkReport, **changes: object) -> BenchmarkReport:
    manifests = []
    for manifest in matrix.manifests:
        payload = manifest.model_dump(mode="json")
        workload = payload["verification_request"]["workload"]
        workload.update(changes)
        payload["integrity"]["workload_fingerprint"] = fingerprint(workload)
        payload["integrity"]["request_fingerprint"] = fingerprint(payload["verification_request"])
        payload["integrity"]["report_fingerprint"] = fingerprint(
            {k: v for k, v in payload["integrity"].items() if k != "report_fingerprint"}
        )
        payload["manifest_fingerprint"] = fingerprint(
            {k: v for k, v in payload.items() if k != "manifest_fingerprint"}
        )
        manifests.append(type(manifest).model_validate(payload))
    return rehash(
        matrix.model_copy(
            update={
                "manifests": tuple(manifests),
                "workload_fingerprint": manifests[0].integrity.workload_fingerprint,
            }
        )
    )


def test_concurrency_and_freshness_are_never_inferred(matrix: BenchmarkReport) -> None:
    changed = with_workload(matrix, concurrency=10, concurrency_scope="production")
    decision = decide(changed, cost_set(changed), POLICY)
    assert decision.outcome == "insufficient_evidence"
    assert "concurrency" in decision.next_questions


def test_observed_maximum_constraint_and_infeasible_baseline(matrix: BenchmarkReport) -> None:
    queries = [
        q.model_dump(mode="json") for q in matrix.manifests[0].verification_request.workload.queries
    ]
    for q in queries:
        q["target_latency_seconds"] = "1"
    changed = with_workload(matrix, queries=queries)
    baseline = next(m.key for m in changed.manifests if m.configuration.baseline)
    trials = []
    for t in changed.trials:
        if t.candidate == baseline:
            observation = t.observation.model_copy(
                update={
                    "queries": tuple(
                        q.model_copy(update={"seconds": 2.0}) for q in t.observation.queries
                    )
                }
            )
            t = t.model_copy(update={"observation": observation})
        trials.append(t)
    changed = rehash(changed.model_copy(update={"trials": tuple(trials)}))
    decision = decide(changed, cost_set(changed), POLICY)
    assert decision.outcome == "change"
    assert (
        next(e for e in decision.candidates if e.configuration.baseline).feasibility == "excluded"
    )
    assert decision.selected_candidate_id != baseline


def test_migration_budget_excludes_changes(matrix: BenchmarkReport) -> None:
    policy = POLICY.model_copy(update={"maximum_migration_cost": Decimal("0")})
    decision = decide(matrix, cost_set(matrix), policy)
    assert decision.outcome == "keep_current"
    assert all(
        e.feasibility == "excluded" for e in decision.candidates if not e.configuration.baseline
    )
