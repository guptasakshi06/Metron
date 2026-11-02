"""Saved real S06 measurement consumption, incomplete trial handling and CLI safety."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from data_optimizer.benchmarking.models import BenchmarkReport
from data_optimizer.cli import main
from data_optimizer.economics.benchmark import bind_benchmark
from data_optimizer.economics.models import CostReport, CostRequest
from data_optimizer.economics.service import calculate
from data_optimizer.profiling.models import fingerprint

REPO = Path(__file__).resolve().parents[2]


def request() -> CostRequest:
    return CostRequest.model_validate_json((REPO / "examples/s07-cost-request.json").read_bytes())


def benchmark() -> BenchmarkReport:
    # Actual saved local fixture measurements from S06, not a live Docker execution here.
    return BenchmarkReport.model_validate_json(
        (REPO / "docs/evidence/s06-benchmark-fresh.json").read_bytes()
    )


def rehash(report: BenchmarkReport) -> BenchmarkReport:
    return report.model_copy(
        update={
            "report_fingerprint": fingerprint(
                report.model_dump(mode="json", exclude={"report_fingerprint"})
            )
        }
    )


def alternative(report: BenchmarkReport) -> str:
    return next(m.key for m in report.manifests if not m.configuration.baseline)


def test_bind_measured_bytes_and_forecast_only_with_explicit_replay_assumption() -> None:
    b = benchmark()
    selected = alternative(b)
    adapted = bind_benchmark(request(), b, selected, Decimal(10000))
    scenario = adapted.scenarios[0]
    manifest = next(m for m in b.manifests if m.key == selected)
    assert scenario.candidate.footprint.data_file_bytes == tuple(
        a.physical_bytes for a in manifest.artifacts
    )
    assert scenario.candidate.footprint.metadata_source.kind == "synthetic"
    assert scenario.candidate.footprint.data_source.kind == "local_measurement"
    assert b.report_fingerprint in scenario.candidate.footprint.data_source.reference
    assert scenario.candidate.recurring[1].quantity.value > 0
    assert scenario.migration.forecast[0].quantity.value > 0
    assert calculate(adapted).results[0].candidate.total is not None
    unknown = bind_benchmark(request(), b, selected, None)
    r = calculate(unknown).results[0]
    assert r.monthly_savings is None
    assert "candidate.query_compute.quantity" in r.missing_inputs
    zero = bind_benchmark(request(), b, selected, Decimal(0))
    assert zero.scenarios[0].candidate.recurring[1].quantity.value == 0


@pytest.mark.parametrize("status", ["timeout", "memory_limit", "cancelled", "budget_exhausted"])
def test_partial_or_failed_trials_are_unknown_never_free(status: str) -> None:
    b = benchmark()
    selected = alternative(b)
    trials = tuple(
        t.model_copy(update={"status": status, "observation": None})
        if t.candidate == selected and t.repeat == 0
        else t
        for t in b.trials
    )
    b = rehash(b.model_copy(update={"trials": trials}))
    adapted = bind_benchmark(request(), b, selected, Decimal(0))
    r = calculate(adapted).results[0]
    assert r.baseline.total is not None
    assert r.candidate.total is None
    assert r.monthly_savings is None


def test_missing_repeated_trial_is_not_complete() -> None:
    b = benchmark()
    selected = alternative(b)
    b = rehash(
        b.model_copy(
            update={
                "trials": tuple(t for t in b.trials if t.candidate != selected or t.repeat != 0)
            }
        )
    )
    r = calculate(bind_benchmark(request(), b, selected, Decimal(100))).results[0]
    assert r.candidate.total is None


@pytest.mark.parametrize("field", ["report", "environment", "manifest", "lineage"])
def test_benchmark_tampering_or_incompatible_lineage_rejected(field: str) -> None:
    b = benchmark()
    selected = alternative(b)
    if field == "report":
        b = b.model_copy(update={"report_fingerprint": "0" * 64})
    elif field == "environment":
        b = rehash(b.model_copy(update={"environment": {"tampered": "value"}}))
    elif field == "manifest":
        b = rehash(
            b.model_copy(
                update={
                    "manifests": (
                        b.manifests[0].model_copy(update={"physical_bytes": 1}),
                        *b.manifests[1:],
                    )
                }
            )
        )
    else:
        b = rehash(b.model_copy(update={"workload_fingerprint": "0" * 64}))
    with pytest.raises(ValueError):
        bind_benchmark(request(), b, selected, Decimal(100))


@pytest.mark.parametrize("replays", [Decimal(-1), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_replay_assumption(replays: Decimal) -> None:
    b = benchmark()
    with pytest.raises(ValueError):
        bind_benchmark(request(), b, alternative(b), replays)


def test_cli_publishes_reconciled_report_and_preserves_existing_files(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    args = [
        "cost",
        "--request",
        str(REPO / "examples/s07-cost-request.json"),
        "--output",
        str(output),
    ]
    main(args)
    report = CostReport.model_validate_json(output.read_bytes())
    assert report.results[0].horizon_net_savings == 1140
    original = output.read_bytes()
    with pytest.raises(SystemExit) as e:
        main(args)
    assert e.value.code == 2
    assert output.read_bytes() == original
    assert len(list(tmp_path.iterdir())) == 1


def test_cli_measured_adapter_and_missing_inputs_exit(tmp_path: Path) -> None:
    b = benchmark()
    output = tmp_path / "measured.json"
    args = [
        "cost",
        "--request",
        str(REPO / "examples/s07-cost-request.json"),
        "--benchmark",
        str(REPO / "docs/evidence/s06-benchmark-fresh.json"),
        "--candidate",
        alternative(b),
        "--output",
        str(output),
    ]
    with pytest.raises(SystemExit) as e:
        main(args)
    assert e.value.code == 1
    r = CostReport.model_validate_json(output.read_bytes()).results[0]
    assert r.space.baseline_physical_bytes == 287
    assert r.monthly_savings is None
    args[-1] = str(tmp_path / "known.json")
    main([*args, "--replays-per-month", "10000"])
    r = CostReport.model_validate_json((tmp_path / "known.json").read_bytes()).results[0]
    assert r.monthly_savings is not None


def test_cli_rejects_invalid_input_without_output(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": "s07.1", "horizon_months": 0}))
    with pytest.raises(SystemExit) as e:
        main(["cost", "--request", str(bad), "--output", str(tmp_path / "none.json")])
    assert e.value.code == 2
    assert not (tmp_path / "none.json").exists()
