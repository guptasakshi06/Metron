"""CLI orchestration tests; injected sandbox timing is explicitly test-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_optimizer.benchmarking.models import BenchmarkReport, BenchmarkRequest, Trial
from data_optimizer.benchmarking.service import summaries
from data_optimizer.cli import main
from data_optimizer.conversion.service import read_manifest
from data_optimizer.optimization import assessment
from data_optimizer.optimization.assessment import AssessmentReport, AssessmentRequest, assess
from data_optimizer.profiling.models import fingerprint

REPO = Path(__file__).resolve().parents[2]


def request() -> AssessmentRequest:
    return AssessmentRequest.model_validate(
        {
            "conversion": json.loads((REPO / "examples/s05-conversion-request.json").read_bytes()),
            "cost_template": json.loads((REPO / "examples/s07-cost-request.json").read_bytes()),
            "replays_per_month": "1000",
            "policy": {"scenario": "documented_example"},
            "search": {"max_trials": 4},
            "benchmark": {"repeats": 1},
        }
    )


@pytest.fixture
def fake_benchmark(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def run(
        directories: tuple[Path, ...], request: BenchmarkRequest, **kwargs: object
    ) -> BenchmarkReport:
        manifests = tuple(read_manifest(d) for d in directories)
        trials = []
        for manifest in manifests:
            queries = [
                {
                    "query_id": q.query_id,
                    "seconds": 0.001,
                    "result_rows": 1,
                    "result_fingerprint": q.candidate_fingerprint,
                }
                for q in manifest.integrity.queries
            ]
            trials.append(
                Trial.model_validate(
                    {
                        "ordinal": len(trials),
                        "repeat": 0,
                        "candidate": manifest.key,
                        "status": "passed",
                        "reason": "injected_unit_test_not_measured",
                        "observation": {
                            "load_seconds": 0.01,
                            "workload_seconds": 0.001 * len(queries),
                            "cpu_seconds": 0.01,
                            "peak_rss_kib": 1000,
                            "queries": queries,
                            "cache": "fresh_process_os_cache_uncontrolled",
                        },
                    }
                )
            )
        report = BenchmarkReport(
            report_fingerprint="0" * 64,
            request_fingerprint=fingerprint(request.model_dump(mode="json")),
            workload_fingerprint=manifests[0].integrity.workload_fingerprint,
            environment_fingerprint=fingerprint({"test": "injected"}),
            environment={"test": "injected"},
            request=request,
            manifests=manifests,
            trials=tuple(trials),
            summaries=summaries(manifests, trials),
            stop_reason="completed",
        )
        calls.append(manifests[-1].key)
        return report.model_copy(
            update={
                "report_fingerprint": fingerprint(
                    report.model_dump(mode="json", exclude={"report_fingerprint"})
                )
            }
        )

    monkeypatch.setattr(assessment, "benchmark", run)
    return calls


def test_pipeline_resume_reuses_evidence_and_preserves_source(
    tmp_path: Path,
    fake_benchmark: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "events.ndjson"
    raw = (REPO / "examples/s04-events.ndjson").read_bytes()
    source.write_bytes(raw)
    root = tmp_path / "workspace"
    result = assess(source, root, request())
    assert result.profile and result.profile.input_fingerprint
    assert result.search and len(result.search.history) == 4
    assert result.benchmark and len(result.benchmark.manifests) == 4
    assert result.decision.outcome == "keep_current"
    assert source.read_bytes() == raw
    assert len(fake_benchmark) == 4

    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("completed work must not execute again")

    monkeypatch.setattr(assessment, "benchmark", unexpected)
    monkeypatch.setattr(assessment, "convert", unexpected)
    monkeypatch.setattr(assessment, "profile_file", unexpected)
    resumed = assess(source, root, request())
    assert resumed == result
    assert AssessmentReport.model_validate_json(resumed.model_dump_json()) == result


def test_new_startup_and_metadata_guidance_without_docker(tmp_path: Path) -> None:
    req = request()
    result = assess(None, tmp_path / "work", req)
    assert result.evidence == "scenario_guidance"
    assert result.decision.outcome == "insufficient_evidence"
    assert result.costs == {} and result.benchmark is None
    profile = assessment.profile_file(REPO / "examples/s04-events.ndjson", req.conversion.source)
    path = tmp_path / "metadata.json"
    path.write_text(profile.model_dump_json())
    imported = assess(None, tmp_path / "work", req, metadata=path)
    assert imported.profile == profile and imported.costs == {}
    assert imported.decision.selected_candidate_id is None


def test_cli_immutable_outputs_and_status(tmp_path: Path) -> None:
    req = tmp_path / "request.json"
    req.write_text(request().model_dump_json())
    output = tmp_path / "report.json"
    args = [
        "assess",
        "--request",
        str(req),
        "--root",
        str(tmp_path / "work"),
        "--output",
        str(output),
    ]
    with pytest.raises(SystemExit) as exit:
        main(args)
    assert exit.value.code == 1
    original = output.read_bytes()
    with pytest.raises(SystemExit) as exit:
        main(args)
    assert exit.value.code == 2
    assert output.read_bytes() == original


def test_missing_costs_abstain_and_trials_remain_bounded(
    tmp_path: Path,
    fake_benchmark: list[str],
) -> None:
    req = request().model_copy(update={"cost_template": None})
    result = assess(REPO / "examples/s04-events.ndjson", tmp_path / "work", req)
    assert result.decision.outcome == "insufficient_evidence"
    assert result.costs == {}
    assert len(fake_benchmark) == 4


def test_resume_after_measurement_before_tell_never_reexecutes(
    tmp_path: Path,
    fake_benchmark: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_tell = assessment.tell

    def interrupted(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected_interruption_after_saved_measurement")

    monkeypatch.setattr(assessment, "tell", interrupted)
    source = REPO / "examples/s04-events.ndjson"
    workspace = tmp_path / "resume"
    with pytest.raises(RuntimeError, match="injected_interruption"):
        assess(source, workspace, request())
    assert len(fake_benchmark) == 1
    monkeypatch.setattr(assessment, "tell", original_tell)
    result = assess(source, workspace, request())
    assert len(fake_benchmark) == 4
    assert result.search and len(result.search.history) == 4
    assert result.search.pending is None


def test_resume_rejects_changed_artifacts(tmp_path: Path, fake_benchmark: list[str]) -> None:
    workspace = tmp_path / "changed"
    assess(REPO / "examples/s04-events.ndjson", workspace, request())
    artifact = next(workspace.glob("artifacts/*/assessments/*/*/part-*.original"))
    artifact.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="invalid_conversion_manifest_or_artifacts"):
        assess(REPO / "examples/s04-events.ndjson", workspace, request())
