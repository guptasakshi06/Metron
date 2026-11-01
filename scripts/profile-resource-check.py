"""Reproducible synthetic S03 resource exercise; no network or retained raw fixtures."""

from __future__ import annotations

import argparse
import json
import platform
import resource
import tempfile
import time
from pathlib import Path

from data_optimizer.profiling.models import ProfileOptions
from data_optimizer.profiling.service import profile_file
from data_optimizer.readers.stream import ProfileError

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
results: dict = {
    "evidence": "synthetic_local_execution",
    "python": platform.python_version(),
    "platform": platform.platform(),
    "limits_are_policy_not_capacity": True,
}
with tempfile.TemporaryDirectory(prefix="s03-resource-") as directory:
    source = Path(directory) / "larger.ndjson"
    with source.open("wb") as output:
        for i in range(60_000):
            output.write(
                json.dumps(
                    {"id": f"{i:08}", "category": i % 3, "text": "x" * 160}
                ).encode()
                + b"\n"
            )
    started = time.monotonic()
    report = profile_file(
        source, ProfileOptions(format="ndjson", sample_rows_per_stratum=256)
    )
    assert report.row_count == 60_000 and report.profiled_rows == 256
    results["larger"] = {
        "physical_bytes": source.stat().st_size,
        "rows": report.row_count,
        "profiled_rows": report.profiled_rows,
        "seconds": round(time.monotonic() - started, 3),
        "memory_limit_mib": 1024,
        "outcome": "completed",
    }
    large = Path(directory) / "above-memory.ndjson"
    with large.open("wb") as output:
        record = b'{"x":"' + b"x" * 1000 + b'"}\n'
        block = record * 1024
        for _ in range(163):
            output.write(block)
    started = time.monotonic()
    try:
        larger = profile_file(large, ProfileOptions(format="ndjson", memory_mib=128))
        assert larger.row_count == 163 * 1024
        outcome = "completed"
    except ProfileError as error:
        assert str(error) in {
            "profile_memory_quota",
            "profile_resource_quota",
            "profile_time_quota",
        }
        outcome = str(error)
    results["above_memory"] = {
        "physical_bytes": large.stat().st_size,
        "memory_limit_mib": 128,
        "outcome": outcome,
        "seconds": round(time.monotonic() - started, 3),
    }
results["child_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results))
