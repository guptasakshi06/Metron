"""Fresh process boundary for local untrusted parsing. No application settings/network."""

from __future__ import annotations

import json
import math
import resource
import sys
from pathlib import Path

from data_optimizer.profiling.models import ProfileOptions


def main() -> None:
    try:
        options = ProfileOptions.model_validate_json(sys.stdin.buffer.read(65_537))
        memory = options.memory_mib * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(
            resource.RLIMIT_CPU, (options.timeout_seconds, math.ceil(options.timeout_seconds) + 1)
        )
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2_097_152, 2_097_152))
        from data_optimizer.profiling.engine import profile
        from data_optimizer.readers.stream import ProfileError

        try:
            report = profile(Path(sys.argv[1]), options)
            Path(sys.argv[2]).write_text(report.model_dump_json(), encoding="utf-8")
            print(json.dumps({"ok": True}))
        except ProfileError as error:
            print(json.dumps({"error": str(error)}))
        except MemoryError:
            print(json.dumps({"error": "profile_memory_quota"}))
        except Exception:
            print(json.dumps({"error": "invalid_structure_or_unsupported_type"}))
    except Exception:
        print(json.dumps({"error": "profile_worker_failed"}))


if __name__ == "__main__":
    main()
