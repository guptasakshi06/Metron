"""Fixed container entry point. No SQL, executable input or external paths accepted."""

from __future__ import annotations

import errno
import json
import math
import os
import platform
import resource
import signal
import time
from pathlib import Path
from typing import Any

from data_optimizer.benchmarking.models import BenchmarkRequest, Observation, QueryTiming
from data_optimizer.candidates.generator import context
from data_optimizer.conversion.service import read_manifest
from data_optimizer.integrity.canonical import encode
from data_optimizer.profiling.models import fingerprint
from data_optimizer.readers.stream import ProfileError
from data_optimizer.workloads.compiler import compile_query
from data_optimizer.workloads.runner import (
    connection,
    load_relation,
    logical_types,
    result_fingerprint,
)


def boundary(request: BenchmarkRequest) -> dict[str, str]:
    """Fail closed when this is not the expected cgroup v2 runtime."""
    root = Path("/sys/fs/cgroup")
    memory = (root / "memory.max").read_text().strip()
    cpu = (root / "cpu.max").read_text().strip()
    pids = (root / "pids.max").read_text().strip()
    swap = (root / "memory.swap.max").read_text().strip()
    quota, period = cpu.split()
    if (
        memory == "max"
        or int(memory) > request.limits.memory_mib * 1048576
        or quota == "max"
        or int(quota) / int(period) > request.limits.cpus + 0.001
        or pids == "max"
        or int(pids) > request.limits.pids
        or swap != "0"
        or set(p.name for p in Path("/sys/class/net").iterdir()) != {"lo"}
    ):
        raise ProfileError("sandbox_controls_unavailable")
    return {"memory.max": memory, "memory.swap.max": swap, "cpu.max": cpu, "pids.max": pids}


def measure(request: BenchmarkRequest) -> dict[str, Any]:
    controls = boundary(request)
    manifest = read_manifest(Path("/input/artifact"))
    verification = manifest.verification_request
    integrity = manifest.integrity
    workload = verification.workload
    if (
        manifest.reader != verification.candidate
        or integrity.workload_status != "passed"
        or integrity.workload_fingerprint != fingerprint(workload.model_dump(mode="json"))
        or integrity.candidate is None
        or {q.query_id for q in integrity.queries} != {q.id for q in workload.queries}
    ):
        raise ProfileError("benchmark_requires_passed_matching_workload")
    # Verification and file hashing precede timing; OS cache is explicitly uncontrolled.
    logical, _ = logical_types(integrity.candidate)
    compiled = [(q, compile_query(q, logical)) for q in workload.queries]
    paths = tuple(Path("/input/artifact") / a.path for a in manifest.artifacts)
    limits = verification.limits.model_copy(
        update={
            "query_memory_mib": min(
                verification.limits.query_memory_mib, max(32, request.limits.memory_mib // 2)
            )
        }
    )
    expected = {q.query_id: q for q in integrity.queries}
    observation = None
    for iteration in range(request.warmups + 1):
        cpu_start = time.process_time()
        started = time.perf_counter()
        with connection(limits) as db:
            load_relation(db, paths, manifest.reader, integrity.candidate, limits)
            loaded = time.perf_counter()
            timings = []
            for query, sql in compiled:
                before = time.perf_counter()
                result = db.execute(sql.sql, sql.parameters).fetchmany(limits.max_result_rows + 1)
                seconds = time.perf_counter() - before
                if len(result) > limits.max_result_rows:
                    raise ProfileError("workload_result_row_quota")
                for row in result:
                    encode(row)
                digest = result_fingerprint(result, bool(query.order_by))
                # Exact repeat fingerprint of this candidate, even for a tolerant baseline check.
                if digest != expected[query.id].candidate_fingerprint:
                    raise ProfileError("benchmark_result_integrity_failed")
                timings.append(
                    QueryTiming(
                        query_id=query.id,
                        seconds=seconds,
                        result_rows=len(result),
                        result_fingerprint=digest,
                    )
                )
        if iteration == request.warmups:
            observation = Observation(
                load_seconds=loaded - started,
                workload_seconds=sum(t.seconds for t in timings),
                cpu_seconds=time.process_time() - cpu_start,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                queries=tuple(timings),
                cache=(
                    "warm_process_os_cache_uncontrolled"
                    if request.warmups
                    else "fresh_process_os_cache_uncontrolled"
                ),
            )
    return {
        "status": "passed",
        "reason": "matching_integrity_and_query_results",
        "observation": observation.model_dump(mode="json") if observation else None,
        "environment": dict(context().engine_versions, kernel=platform.release(), **controls),
    }


def main() -> None:
    # Avoid host core-dump handlers on SIGXCPU; report its conventional exit explicitly.
    signal.signal(signal.SIGXCPU, lambda *_: os._exit(152))
    result: dict[str, Any]
    try:
        path = Path("/input/request.json")
        if path.stat().st_size > 65536:
            raise ProfileError("benchmark_request_byte_quota")
        request = BenchmarkRequest.model_validate_json(path.read_bytes())
        # Kernel alarm also bounds this worker if its parent orchestrator dies.
        signal.signal(signal.SIGALRM, lambda *_: os._exit(142))
        signal.alarm(math.ceil(request.limits.wall_seconds))
        result = measure(request)
    except MemoryError:
        result = {"status": "memory_limit", "reason": "python_memory_limit"}
    except OSError as error:
        result = {
            "status": "disk_limit" if error.errno in {errno.ENOSPC, errno.EFBIG} else "failed",
            "reason": "worker_io_failure",
        }
    except ProfileError:
        result = {"status": "integrity_failed", "reason": "manifest_or_result_validation_failed"}
    except Exception as error:
        import duckdb

        result = {
            "status": "memory_limit"
            if isinstance(error, duckdb.OutOfMemoryException)
            else "failed",
            "reason": "worker_resource_or_unsupported_input",
        }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
