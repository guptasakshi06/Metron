"""Public local verifier and atomic, fingerprint-checked evidence persistence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from data_optimizer.integrity.models import IntegrityReport, VerificationRequest
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import fingerprint
from data_optimizer.readers.stream import ProfileError

MAX_REPORT_BYTES = 2_097_152


def read_evidence(path: Path) -> IntegrityReport:
    with path.open("rb") as source:
        data = source.read(MAX_REPORT_BYTES + 1)
    if len(data) > MAX_REPORT_BYTES:
        raise ProfileError("integrity_report_byte_quota")
    try:
        report = IntegrityReport.model_validate_json(data)
        if report.report_fingerprint != fingerprint(
            report.model_dump(mode="json", exclude={"report_fingerprint"})
        ):
            raise ValueError("fingerprint mismatch")
        return report
    except ValueError:
        raise ProfileError("invalid_integrity_evidence") from None


def write_evidence(path: Path, report: IntegrityReport, sources: tuple[Path, ...] = ()) -> None:
    for source in sources:
        if path.resolve() == source.resolve() or (path.exists() and os.path.samefile(path, source)):
            raise ProfileError("output_must_preserve_source")
    data = report.model_dump_json(indent=2).encode()
    if len(data) > MAX_REPORT_BYTES:
        raise ProfileError("integrity_report_byte_quota")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".integrity-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify_files(
    baseline: Path,
    candidate: Path,
    request: VerificationRequest,
) -> IntegrityReport:
    request = VerificationRequest.model_validate(request.model_dump())
    before = (
        input_digest(baseline, request.baseline.max_raw_bytes),
        input_digest(candidate, request.candidate.max_raw_bytes),
    )
    with tempfile.TemporaryDirectory(prefix="data-optimizer-integrity-") as directory:
        output = Path(directory) / "evidence.json"
        environment = dict(os.environ)
        environment.update(
            OPENBLAS_NUM_THREADS="1",
            OMP_NUM_THREADS="1",
            ARROW_NUM_THREADS="1",
            ARROW_DEFAULT_MEMORY_POOL="system",
        )
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "data_optimizer.integrity.worker",
                    str(baseline.resolve()),
                    str(candidate.resolve()),
                    str(output),
                ],
                input=request.model_dump_json().encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=request.limits.timeout_seconds + 2,
                check=False,
                env=environment,
            )
        except subprocess.TimeoutExpired:
            raise ProfileError("integrity_time_quota") from None
        if process.returncode != 0:
            raise ProfileError("integrity_resource_quota")
        try:
            response = json.loads(process.stdout)
        except ValueError:
            raise ProfileError("integrity_worker_failed") from None
        if "error" in response:
            raise ProfileError(response["error"])
        report = read_evidence(output)
    after = (
        input_digest(baseline, request.baseline.max_raw_bytes),
        input_digest(candidate, request.candidate.max_raw_bytes),
    )
    if (
        before != after
        or (report.baseline and report.baseline.input_fingerprint != before[0])
        or (report.candidate and report.candidate.input_fingerprint != before[1])
    ):
        raise ProfileError("input_changed_during_integrity")
    return report
