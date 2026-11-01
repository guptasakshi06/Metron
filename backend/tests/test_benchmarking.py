"""Deterministic scheduling and evidence/budget behavior without timing assertions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from data_optimizer.benchmarking.models import BenchmarkRequest, Trial
from data_optimizer.benchmarking.service import benchmark, schedule, write_report
from data_optimizer.candidates.models import ConversionRequest
from data_optimizer.conversion.service import convert, list_candidates
from data_optimizer.profiling.models import fingerprint
from data_optimizer.sandbox import docker

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ...]:
    root = tmp_path_factory.mktemp("benchmark-inputs")
    source = root / "events.ndjson"
    source.write_bytes((REPO / "examples/s04-events.ndjson").read_bytes())
    request = ConversionRequest.model_validate_json(
        (REPO / "examples/s05-conversion-request.json").read_bytes()
    )
    configurations = list_candidates(source, request).candidates[:4]
    outputs = [
        convert(source, root / "artifacts", request, c.configuration) for c in configurations
    ]
    assert all(o.status == "validated" and o.artifact_prefix for o in outputs)
    return tuple(Path(o.artifact_prefix) for o in outputs if o.artifact_prefix)


def test_schedule_is_seeded_interleaved_and_complete() -> None:
    request = BenchmarkRequest(seed=42, repeats=5)
    candidates = tuple(str(i) for i in range(4))
    result = schedule(candidates, request)
    assert result == schedule(candidates, request)
    assert result != schedule(candidates, request.model_copy(update={"seed": 17}))
    for repeat in range(5):
        assert sorted(c for r, c in result if r == repeat) == list(candidates)


@pytest.mark.parametrize(
    "update",
    [
        {"repeats": 6},
        {"limits": {"cpus": 0}},
        {"limits": {"memory_mib": 0}},
        {"limits": {"scratch_mib": 0}},
        {"sql": "DROP TABLE x"},
        {"warmups": -1},
    ],
)
def test_invalid_or_executable_requests_rejected(update: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BenchmarkRequest.model_validate(update)


def test_failed_trials_cannot_contain_measurements() -> None:
    with pytest.raises(ValidationError):
        Trial(ordinal=0, repeat=0, candidate="a" * 64, status="passed", reason="missing")


@pytest.fixture
def offline_runtime(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls = []
    monkeypatch.setattr(docker, "image_id", lambda image: "sha256:" + "a" * 64)
    monkeypatch.setattr(docker, "control", lambda args: "test-only-not-measured")

    def failure(*args: object, **kwargs: object) -> docker.SandboxResult:
        calls.append("trial")
        return docker.SandboxResult("timeout", "injected_test_timeout")

    monkeypatch.setattr(docker, "run", failure)
    return calls


def test_budget_and_failed_summaries_remain_unknown(
    artifacts: tuple[Path, ...], offline_runtime: list[str], tmp_path: Path
) -> None:
    report = benchmark(artifacts, BenchmarkRequest(repeats=3, max_trials=1))
    assert offline_runtime == ["trial"]
    assert report.stop_reason == "budget_exhausted"
    assert len(report.trials) == 12
    assert [t.status for t in report.trials] == ["timeout"] + ["budget_exhausted"] * 11
    assert all(s.median_seconds is None and s.observations == 0 for s in report.summaries)
    assert report.report_fingerprint == fingerprint(
        report.model_dump(mode="json", exclude={"report_fingerprint"})
    )
    destination = tmp_path / "report.json"
    write_report(destination, report, artifacts)
    assert json.loads(destination.read_bytes())["stop_reason"] == "budget_exhausted"
    with pytest.raises(FileExistsError):
        write_report(destination, report, artifacts)
    with pytest.raises(ValueError, match="preserve_artifacts"):
        write_report(artifacts[0] / "new.json", report, artifacts)


def test_cancellation_skips_remaining_trials(
    artifacts: tuple[Path, ...], offline_runtime: list[str]
) -> None:
    report = benchmark(artifacts, BenchmarkRequest(repeats=2), cancelled=lambda: True)
    assert report.stop_reason == "cancelled" and not offline_runtime
    assert len(report.trials) == 8 and all(t.status == "cancelled" for t in report.trials)


def test_missing_or_corrupt_manifest_is_explicit(
    tmp_path: Path, offline_runtime: list[str]
) -> None:
    report = benchmark((tmp_path,), BenchmarkRequest())
    assert len(report.trials) == 1 and report.trials[0].status == "integrity_failed"
    assert not report.manifests and not offline_runtime


def test_mixed_or_duplicate_matrices_rejected(
    artifacts: tuple[Path, ...], offline_runtime: list[str]
) -> None:
    with pytest.raises(ValueError, match="one_baseline"):
        benchmark(artifacts[1:], BenchmarkRequest())
    with pytest.raises(ValueError, match="duplicate"):
        benchmark((artifacts[0], artifacts[0]), BenchmarkRequest())
    with pytest.raises(ValueError, match="snapshot_byte_quota"):
        benchmark(artifacts, BenchmarkRequest(max_input_bytes=1))
    assert not offline_runtime
