"""Bound local parsing/query work in a fresh Linux process; S06 adds isolation."""

from __future__ import annotations

import json
import resource
import sys
from pathlib import Path

from data_optimizer.integrity.models import VerificationRequest


def main() -> None:
    try:
        request = VerificationRequest.model_validate_json(sys.stdin.buffer.read(262_145))
        limits = request.limits
        memory = limits.memory_mib * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(
            resource.RLIMIT_CPU, (limits.timeout_seconds, limits.timeout_seconds + 1)
        )
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits.max_spill_bytes, limits.max_spill_bytes))
        from data_optimizer.integrity.engine import verify

        report = verify(
            Path(sys.argv[1]), Path(sys.argv[2]), request, scratch_root=Path(sys.argv[3]).parent
        )
        Path(sys.argv[3]).write_text(report.model_dump_json(), encoding="utf-8")
        print(json.dumps({"ok": True}))
    except MemoryError:
        print(json.dumps({"error": "integrity_memory_quota"}))
    except Exception:
        print(json.dumps({"error": "integrity_worker_failed"}))


if __name__ == "__main__":
    main()
