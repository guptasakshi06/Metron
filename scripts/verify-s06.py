"""Reproduce actual CLI benchmark evidence and bounded Docker resource probes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from data_optimizer.benchmarking.models import (
    BenchmarkReport,
    BenchmarkRequest,
    SandboxLimits,
)
from data_optimizer.candidates.models import ConversionRequest
from data_optimizer.conversion.service import convert, list_candidates
from data_optimizer.profiling.engine import input_digest
from data_optimizer.sandbox import docker

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    image = docker.image_id()
    source = REPO / "examples/s04-events.ndjson"
    before = input_digest(source, 1048576)
    records = []
    with tempfile.TemporaryDirectory(prefix="verify-s06-") as temporary:
        root = Path(temporary)
        request = ConversionRequest.model_validate_json(
            (REPO / "examples/s05-conversion-request.json").read_bytes()
        )
        candidates = list_candidates(source, request).candidates[:4]
        outcomes = [
            convert(source, root / "copies", request, c.configuration)
            for c in candidates
        ]
        assert all(o.manifest and o.artifact_prefix for o in outcomes)
        directories = [str(o.artifact_prefix) for o in outcomes]
        # Reproduce using the built, extracted distributable, outside the source tree.
        wheels = list((REPO / "backend/dist").glob("*.whl"))
        assert len(wheels) == 1, "Run make build first"
        wheel_root = root / "wheel"
        with zipfile.ZipFile(wheels[0]) as wheel:
            wheel.extractall(wheel_root)
        assert (wheel_root / "data_optimizer/benchmarking/worker.py").is_file()
        environment = dict(os.environ, PYTHONPATH=str(wheel_root))
        for warmups, label in ((0, "fresh"), (1, "warm")):
            benchmark_request = root / "request.json"
            benchmark_request.write_text(
                BenchmarkRequest(repeats=3, warmups=warmups, seed=42).model_dump_json()
            )
            report_path = root / f"{label}.json"
            command = [
                sys.executable,
                "-m",
                "data_optimizer.cli",
                "benchmark",
                *directories,
                "--request",
                str(benchmark_request),
                "--output",
                str(report_path),
            ]
            result = subprocess.run(
                command,
                check=False,
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert result.returncode == 0, result.stderr
            report = BenchmarkReport.model_validate_json(report_path.read_bytes())
            assert len(report.trials) == 12 and all(
                t.status == "passed" for t in report.trials
            )
            shutil.copyfile(
                report_path, args.output_dir / f"s06-benchmark-{label}.json"
            )
        snapshot = root / "probe"
        snapshot.mkdir(mode=0o755)
        probes = [
            (
                "wall",
                "import time; time.sleep(100)",
                SandboxLimits(wall_seconds=0.4),
                "timeout",
            ),
            (
                "memory",
                "x=[bytearray(8*1024*1024) for _ in range(100)]",
                SandboxLimits(memory_mib=64),
                "memory_limit",
            ),
            (
                "cpu",
                (
                    "import signal,os; signal.signal(signal.SIGXCPU, lambda *_: os._exit(152))\n"
                    "while True: pass"
                ),
                SandboxLimits(cpu_seconds=1),
                "cpu_limit",
            ),
            (
                "output",
                "import os; os.write(1,b'x'*100000)",
                SandboxLimits(output_bytes=1024),
                "output_limit",
            ),
        ]
        for name, code, limits, expected in probes:
            result = docker.run(image, snapshot, limits, command=("-c", code))
            assert result.status == expected, result
            record = asdict(result)
            record["stdout"] = result.stdout.decode()
            records.append(dict(probe=name, limits=limits.model_dump(), **record))
        started = time.monotonic()
        result = docker.run(
            image,
            snapshot,
            SandboxLimits(),
            command=("-c", "import time; time.sleep(100)"),
            cancelled=lambda: time.monotonic() - started > 0.5,
        )
        assert result.status == "cancelled"
        record = asdict(result)
        record["stdout"] = result.stdout.decode()
        records.append(dict(probe="cancellation", **record))
    assert input_digest(source, 1048576) == before
    assert not docker.control(
        ["ps", "-aq", "--filter", "label=data-optimizer.benchmark=true"]
    )
    (args.output_dir / "s06-resource-results.json").write_text(
        json.dumps(
            {
                "version": 1,
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "image_id": image,
                "fixture_sha256": before,
                "original_unchanged": True,
                "orphan_containers": 0,
                "cli": "extracted_wheel_in_separate_working_directory",
                "raw_reports": ["s06-benchmark-fresh.json", "s06-benchmark-warm.json"],
                "probes": records,
            },
            indent=2,
        )
        + "\n"
    )
    print("Actual CLI and Docker benchmark/resource evidence passed.")


if __name__ == "__main__":
    main()
