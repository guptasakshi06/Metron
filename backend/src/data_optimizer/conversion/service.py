"""Local assessment prefixes, locked atomic publication and verified idempotent reuse."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from data_optimizer.candidates.generator import context
from data_optimizer.candidates.models import CandidateConfig, CandidateList, ConversionRequest
from data_optimizer.conversion.models import ConversionManifest, ConversionOutcome
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import fingerprint
from data_optimizer.readers.stream import ProfileError


def read_manifest(directory: Path) -> ConversionManifest:
    path = directory / "manifest.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4_194_304:
        raise ProfileError("invalid_conversion_manifest")
    try:
        result = ConversionManifest.model_validate_json(path.read_bytes())
        if result.manifest_fingerprint != fingerprint(
            result.model_dump(mode="json", exclude={"manifest_fingerprint"})
        ):
            raise ValueError("manifest_fingerprint_mismatch")
        report = result.integrity
        if report.report_fingerprint != fingerprint(
            report.model_dump(mode="json", exclude={"report_fingerprint"})
        ):
            raise ValueError("integrity_fingerprint_mismatch")
        if report.request_fingerprint != fingerprint(
            result.verification_request.model_dump(mode="json")
        ):
            raise ValueError("verification_request_mismatch")
        if report.baseline is None or report.baseline.input_fingerprint != result.input_fingerprint:
            raise ValueError("baseline_fingerprint_mismatch")
        for artifact in result.artifacts:
            output = directory / artifact.path
            if (
                not output.is_file()
                or output.is_symlink()
                or not output.resolve().is_relative_to(directory.resolve())
                or output.stat().st_size != artifact.physical_bytes
                or input_digest(output, artifact.physical_bytes) != artifact.sha256
            ):
                raise ValueError("artifact_fingerprint_mismatch")
        actual = {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}
        if actual != {a.path for a in result.artifacts} | {"manifest.json"}:
            raise ValueError("unexpected_artifact")
        return result
    except (ValueError, OSError):
        raise ProfileError("invalid_conversion_manifest_or_artifacts") from None


def worker(
    path: Path,
    directory: Path,
    request: ConversionRequest,
    config: CandidateConfig | None,
    key: str,
    cancelled: Callable[[], bool] | None = None,
    lock_fd: int | None = None,
) -> dict[str, Any]:
    environment = dict(os.environ)
    environment.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", ARROW_NUM_THREADS="1")
    payload = json.dumps(
        {
            "request": request.model_dump(mode="json"),
            "configuration": config.model_dump(mode="json") if config else None,
            "key": key,
        }
    ).encode()
    if len(payload) > 524_288:
        raise ProfileError("conversion_request_byte_quota")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "data_optimizer.conversion.worker",
            str(path.resolve()),
            str(directory.resolve()),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
        pass_fds=(lock_fd,) if lock_fd is not None else (),
    )
    deadline = time.monotonic() + request.limits.timeout_seconds + 2
    try:
        first = True
        while True:
            if cancelled and cancelled():
                return {"status": "cancelled", "reasons": ["conversion_cancelled"]}
            if time.monotonic() >= deadline:
                return {"status": "failed", "reasons": ["conversion_time_quota"]}
            try:
                stdout, _ = process.communicate(input=payload if first else None, timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                first = False
        if process.returncode != 0:
            return {"status": "failed", "reasons": ["conversion_resource_quota"]}
        if len(stdout) > 4_194_304:
            raise ProfileError("conversion_response_byte_quota")
        result: dict[str, Any] = json.loads(stdout)
        return result
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def list_candidates(
    path: Path,
    request: ConversionRequest,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> CandidateList:
    request = ConversionRequest.model_validate(request.model_dump())
    before = input_digest(path, request.source.max_raw_bytes)
    with tempfile.TemporaryDirectory(prefix="data-optimizer-candidates-") as temporary:
        result = worker(path, Path(temporary), request, None, "", cancelled=cancelled)
    if result.get("status"):
        raise ProfileError(result.get("reasons", ["candidate_generation_failed"])[0])
    candidates = CandidateList.model_validate(result)
    if (
        candidates.input_fingerprint != before
        or input_digest(path, request.source.max_raw_bytes) != before
    ):
        raise ProfileError("input_changed_during_conversion")
    return candidates


def convert(
    path: Path,
    root: Path,
    request: ConversionRequest,
    config: CandidateConfig,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> ConversionOutcome:
    request = ConversionRequest.model_validate(request.model_dump())
    config = CandidateConfig.model_validate(config.model_dump())
    if config.context != context():
        return ConversionOutcome(status="excluded", reasons=("execution_context_mismatch",))
    before = input_digest(path, request.source.max_raw_bytes)
    key = fingerprint(
        {
            "input": before,
            "request": request.model_dump(mode="json"),
            "configuration": config.model_dump(mode="json"),
        }
    )
    prefix = root / str(request.tenant_id) / "assessments" / str(request.assessment_id)
    prefix.mkdir(parents=True, exist_ok=True, mode=0o700)
    prefix = prefix.resolve()
    final = prefix / key
    partial = prefix / (".partial-" + key)
    # A source under an output prefix could otherwise be removed by recovery cleanup.
    if path.resolve().is_relative_to(final) or path.resolve().is_relative_to(partial):
        raise ProfileError("output_must_preserve_source")
    lock_dir = prefix / ".locks"
    lock_dir.mkdir(exist_ok=True, mode=0o700)
    with (lock_dir / key).open("a+b") as lock:
        lock_deadline = time.monotonic() + request.limits.timeout_seconds + 2
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= lock_deadline:
                    return ConversionOutcome(status="failed", reasons=("conversion_lock_timeout",))
                if cancelled and cancelled():
                    return ConversionOutcome(status="cancelled", reasons=("conversion_cancelled",))
                time.sleep(0.05)
        if cancelled and cancelled():
            return ConversionOutcome(status="cancelled", reasons=("conversion_cancelled",))
        if final.exists():
            manifest = read_manifest(final)
            if (
                manifest.key != key
                or manifest.configuration != config
                or manifest.request_fingerprint != fingerprint(request.model_dump(mode="json"))
                or manifest.input_fingerprint != before
            ):
                raise ProfileError("incompatible_conversion_manifest")
            if input_digest(path, request.source.max_raw_bytes) != before:
                raise ProfileError("input_changed_during_conversion")
            return ConversionOutcome(status="reused", manifest=manifest, artifact_prefix=str(final))
        # Fixed-name partials are recoverable after a whole parent/worker crash under this lock.
        if partial.is_symlink():
            raise ProfileError("unsafe_partial_prefix")
        if partial.exists():
            shutil.rmtree(partial)
        partial.mkdir(mode=0o700)
        try:
            result = worker(path, partial, request, config, key, cancelled, lock.fileno())
            if result.get("status") != "validated":
                return ConversionOutcome.model_validate(result)
            if cancelled and cancelled():
                return ConversionOutcome(status="cancelled", reasons=("conversion_cancelled",))
            manifest = read_manifest(partial)
            if (
                manifest.key != key
                or manifest.configuration != config
                or manifest.request_fingerprint != fingerprint(request.model_dump(mode="json"))
                or manifest.input_fingerprint != before
            ):
                raise ProfileError("incompatible_conversion_manifest")
            if input_digest(path, request.source.max_raw_bytes) != before:
                raise ProfileError("input_changed_during_conversion")
            # All file handles are closed; same-filesystem rename publishes the directory.
            os.rename(partial, final)
            return ConversionOutcome(
                status="validated", manifest=manifest, artifact_prefix=str(final)
            )
        finally:
            if partial.exists():
                shutil.rmtree(partial)
