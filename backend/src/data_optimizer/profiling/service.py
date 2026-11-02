"""Public bounded profiler, immutable local cache and report import/export."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import (
    ProfileOptions,
    ProfileReport,
    fingerprint,
    validate_report,
)
from data_optimizer.readers.stream import ProfileError

MAX_REPORT_BYTES = 2_097_152


def read_report(path: Path) -> ProfileReport:
    with path.open("rb") as source:
        data = source.read(MAX_REPORT_BYTES + 1)
    if len(data) > MAX_REPORT_BYTES:
        raise ProfileError("report_byte_quota")
    try:
        return validate_report(data)
    except ValueError:
        raise ProfileError("invalid_metadata_report") from None


def write_report(path: Path, report: ProfileReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".profile-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(report.model_dump_json(indent=2))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def profile_file(
    path: Path,
    options: ProfileOptions,
    cache: Path | None = None,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> ProfileReport:
    original = input_digest(path, options.max_raw_bytes)
    import platform

    import pyarrow

    engines = {"python": platform.python_version(), "pyarrow": pyarrow.__version__}
    settings_hash = fingerprint(options.model_dump(mode="json"))
    key = fingerprint([original, settings_hash, engines, "s03.1"])
    cache_path = cache / f"{key}.json" if cache else None
    if cache_path and cache_path.is_file():
        cached = read_report(cache_path)
        if (
            cached.input_fingerprint == original
            and cached.settings_fingerprint == settings_hash
            and cached.engine_versions == engines
            and cached.profiler_version == "s03.1"
        ):
            return cached
        raise ProfileError("incompatible_cached_profile")
    with tempfile.TemporaryDirectory(prefix="data-optimizer-profile-") as directory:
        output = Path(directory) / "report.json"
        environment = dict(os.environ)
        environment.update(
            OPENBLAS_NUM_THREADS="1",
            OMP_NUM_THREADS="1",
            ARROW_NUM_THREADS="1",
            ARROW_DEFAULT_MEMORY_POOL="system",
        )
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "data_optimizer.profiling.worker",
                    str(path.resolve()),
                    str(output),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
            )
            deadline = time.monotonic() + options.timeout_seconds + 2
            first = True
            try:
                while True:
                    if cancelled and cancelled():
                        raise ProfileError("assessment_cancelled")
                    if time.monotonic() >= deadline:
                        raise ProfileError("profile_time_quota")
                    try:
                        stdout, _ = process.communicate(
                            input=options.model_dump_json().encode() if first else None, timeout=0.1
                        )
                        break
                    except subprocess.TimeoutExpired:
                        first = False
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()
        except subprocess.TimeoutExpired:
            raise ProfileError("profile_time_quota") from None
        if process.returncode != 0:
            raise ProfileError("profile_resource_quota")
        try:
            response = json.loads(stdout)
        except ValueError:
            raise ProfileError("profile_worker_failed") from None
        if "error" in response:
            raise ProfileError(response["error"])
        report = read_report(output)
    if report.input_fingerprint != original:
        raise ProfileError("input_changed_during_profile")
    if cache_path:
        if cache_path.resolve() == path.resolve():
            raise ProfileError("output_must_preserve_source")
        write_report(cache_path, report)
    return report
