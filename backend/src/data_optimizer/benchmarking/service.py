"""Seeded interleaved trials over private snapshots of verified S05 artifacts."""

from __future__ import annotations

import json
import os
import platform
import random
import statistics
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from data_optimizer.benchmarking.models import (
    BenchmarkReport,
    BenchmarkRequest,
    Observation,
    Summary,
    Trial,
)
from data_optimizer.conversion.models import ConversionManifest
from data_optimizer.conversion.service import read_manifest
from data_optimizer.profiling.models import fingerprint
from data_optimizer.readers.stream import ProfileError
from data_optimizer.sandbox import docker


def schedule(candidates: tuple[str, ...], request: BenchmarkRequest) -> list[tuple[int, str]]:
    rng = random.Random(request.seed)
    order: list[tuple[int, str]] = []
    for repeat in range(request.repeats):
        shuffled = list(candidates)
        rng.shuffle(shuffled)
        order.extend((repeat, key) for key in shuffled)
    return order


def summaries(
    manifests: tuple[ConversionManifest, ...], trials: list[Trial]
) -> tuple[Summary, ...]:
    result = []
    for manifest in manifests:
        for query in manifest.verification_request.workload.queries:
            samples = [
                timing.seconds
                for trial in trials
                if trial.candidate == manifest.key and trial.observation is not None
                for timing in trial.observation.queries
                if timing.query_id == query.id
            ]
            result.append(
                Summary(
                    candidate=manifest.key,
                    query_id=query.id,
                    observations=len(samples),
                    median_seconds=statistics.median(samples) if samples else None,
                    minimum_seconds=min(samples) if samples else None,
                    maximum_seconds=max(samples) if samples else None,
                    stdev_seconds=statistics.stdev(samples) if len(samples) > 1 else None,
                )
            )
    return tuple(result)


def benchmark(
    directories: tuple[Path, ...],
    request: BenchmarkRequest,
    *,
    image: str = docker.DEFAULT_IMAGE,
    cancelled: Callable[[], bool] | None = None,
) -> BenchmarkReport:
    request = BenchmarkRequest.model_validate(request.model_dump())
    if not 1 <= len(directories) <= 12:
        raise ValueError("benchmark_candidate_count_quota")
    started = time.monotonic()
    deadline = started + request.assessment_seconds
    manifests: list[ConversionManifest] = []
    trials: list[Trial] = []
    by_key: dict[str, Path] = {}
    for directory in directories:
        try:
            manifest = read_manifest(directory)
            if (
                manifest.reader != manifest.verification_request.candidate
                or manifest.integrity.workload_status != "passed"
                or manifest.integrity.workload_fingerprint
                != fingerprint(manifest.verification_request.workload.model_dump(mode="json"))
            ):
                raise ProfileError("unverified_workload")
        except (ProfileError, OSError, ValueError):
            trials.append(
                Trial(
                    ordinal=len(trials),
                    repeat=0,
                    candidate=fingerprint({"invalid_artifact_reference": str(directory)}),
                    status="integrity_failed",
                    reason="invalid_manifest_artifacts_or_workload",
                )
            )
            continue
        if manifest.key in by_key:
            raise ValueError("duplicate_benchmark_candidate")
        manifests.append(manifest)
        by_key[manifest.key] = directory
    if manifests:
        first = manifests[0]
        if sum(m.configuration.baseline for m in manifests) != 1 or any(
            m.input_fingerprint != first.input_fingerprint
            or m.request_fingerprint != first.request_fingerprint
            or m.integrity.workload_fingerprint != first.integrity.workload_fingerprint
            for m in manifests
        ):
            raise ValueError("matrix_requires_one_baseline_and_matching_input_request_workload")
    if sum(m.physical_bytes for m in manifests) > request.max_input_bytes:
        raise ValueError("benchmark_snapshot_byte_quota")
    immutable_image = docker.image_id(image)
    environment = {
        "image_id": immutable_image,
        "host_kernel": platform.release(),
        "host_machine": platform.machine(),
        "docker_version": docker.control(["version", "--format", "{{.Server.Version}}"]),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unavailable",
        ),
        "boundary": "docker_cgroup_v2_network_none_readonly_tmpfs",
        "measurement": "typed_full_read_load_then_in_memory_queries_no_native_pushdown",
        "os_cache": "uncontrolled_and_pre_read_by_integrity_hashing",
        "cpu_scope": "process_cpu_for_timed_load_and_queries",
        "rss_scope": "linux_process_high_water_includes_imports_validation_warmups",
        "disk_scope": "bounded_tmpfs_scratch_plus_1MiB_shm_and_docker_dev_tmpfs",
    }
    stop = "completed"
    with tempfile.TemporaryDirectory(prefix="data-optimizer-benchmark-") as temporary:
        root = Path(temporary)
        # Only expose the private candidate snapshot, never the original artifact root.
        snapshots = {}
        for manifest in manifests:
            target = root / manifest.key
            target.mkdir(mode=0o755)
            artifact = target / "artifact"
            artifact.mkdir(mode=0o755)
            (artifact / "manifest.json").write_text(manifest.model_dump_json())
            for item in manifest.artifacts:
                output = artifact / item.path
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                # Do not follow a replaced source symlink or copy beyond its recorded bound.
                fd = os.open(by_key[manifest.key] / item.path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as source, output.open("wb") as destination:
                    remaining = item.physical_bytes
                    while remaining:
                        chunk = source.read(min(65536, remaining))
                        if not chunk:
                            raise ProfileError("snapshot_input_changed")
                        destination.write(chunk)
                        remaining -= len(chunk)
                    if source.read(1):
                        raise ProfileError("snapshot_input_changed")
                output.chmod(0o644)
            # Rehash copied files before passing them to the isolated worker.
            read_manifest(artifact)
            snapshots[manifest.key] = target
        attempts = 0
        for repeat, key in schedule(tuple(by_key), request):
            elapsed = time.monotonic()
            if stop == "completed":
                if cancelled and cancelled():
                    stop = "cancelled"
                elif elapsed >= deadline or attempts >= request.max_trials:
                    stop = "budget_exhausted"
            if stop != "completed":
                trials.append(
                    Trial(
                        ordinal=len(trials),
                        repeat=repeat,
                        candidate=key,
                        status=stop,
                        reason="remaining_trial_not_executed",
                    )
                )
                continue
            (snapshots[key] / "request.json").write_text(request.model_dump_json())
            outcome = docker.run(
                immutable_image,
                snapshots[key],
                request.limits,
                cancelled=cancelled,
                budget_deadline=deadline,
            )
            attempts += 1
            status, reason, observation = outcome.status, outcome.reason, None
            if status == "passed":
                try:
                    payload = json.loads(outcome.stdout)
                    response = Trial(
                        ordinal=len(trials),
                        repeat=repeat,
                        candidate=key,
                        status=payload["status"],
                        reason=payload["reason"],
                        observation=payload.get("observation"),
                    )
                    status, reason = response.status, response.reason
                    if status == "passed":
                        observation = Observation.model_validate(payload["observation"])
                        manifest = next(m for m in manifests if m.key == key)
                        expected = {
                            q.query_id: q.candidate_fingerprint for q in manifest.integrity.queries
                        }
                        if (
                            len(observation.queries) != len(expected)
                            or {q.query_id: q.result_fingerprint for q in observation.queries}
                            != expected
                        ):
                            raise ValueError("result_mismatch")
                        for name, value in payload["environment"].items():
                            if not isinstance(name, str) or not isinstance(value, str):
                                raise ValueError("invalid_environment")
                            field = "worker_" + name
                            if field in environment and environment[field] != value:
                                raise ValueError("worker_environment_drift")
                            environment[field] = value
                except (ValueError, KeyError, TypeError):
                    status, reason, observation = "failed", "invalid_worker_response", None
            trials.append(
                Trial(
                    ordinal=len(trials),
                    repeat=repeat,
                    candidate=key,
                    status=status,
                    reason=reason,
                    observation=observation,
                    elapsed_seconds=outcome.elapsed_seconds,
                    exit_code=outcome.exit_code,
                    oom_killed=outcome.oom_killed,
                )
            )
            if status in {"cancelled", "budget_exhausted"}:
                stop = status
    report = BenchmarkReport(
        report_fingerprint="0" * 64,
        request_fingerprint=fingerprint(request.model_dump(mode="json")),
        workload_fingerprint=manifests[0].integrity.workload_fingerprint
        if manifests
        else fingerprint({"workload": "unavailable"}),
        environment_fingerprint=fingerprint(environment),
        request=request,
        environment=environment,
        manifests=tuple(manifests),
        trials=tuple(trials),
        summaries=summaries(tuple(manifests), trials),
        stop_reason=stop,
    )
    return report.model_copy(
        update={
            "report_fingerprint": fingerprint(
                report.model_dump(mode="json", exclude={"report_fingerprint"})
            )
        }
    )


def write_report(path: Path, report: BaseModel, sources: tuple[Path, ...]) -> None:
    if any(path.resolve().is_relative_to(p.resolve()) for p in sources):
        raise ValueError("report_must_preserve_artifacts")
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL prevents accidental overwrite of any existing source, request or evidence.
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(report.model_dump_json(indent=2).encode())
            stream.close()
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
