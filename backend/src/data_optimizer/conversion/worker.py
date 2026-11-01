"""Resource-bounded local process; benchmark isolation is S06."""

from __future__ import annotations

import json
import resource
import sys
from pathlib import Path

from data_optimizer.candidates.models import CandidateConfig, ConversionRequest
from data_optimizer.readers.stream import ProfileError


def main() -> None:
    try:
        payload = json.loads(sys.stdin.buffer.read(524_289))
        request = ConversionRequest.model_validate(payload["request"])
        config = (
            CandidateConfig.model_validate(payload["configuration"])
            if payload.get("configuration")
            else None
        )
        memory = request.limits.memory_mib * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (request.limits.timeout_seconds, request.limits.timeout_seconds + 1),
        )
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        file_limit = max(request.max_output_bytes, request.limits.max_spill_bytes)
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
        from data_optimizer.conversion.engine import run

        result = run(Path(sys.argv[1]), Path(sys.argv[2]), request, config, payload["key"])
    except ProfileError as error:
        reason = str(error)
        status = (
            "excluded"
            if reason
            in {
                "partition_count_quota",
                "partition_small_file_amplification",
                "conversion_file_count_quota",
            }
            else "failed"
        )
        result = {"status": status, "reasons": [reason]}
    except MemoryError:
        result = {"status": "failed", "reasons": ["conversion_memory_quota"]}
    except Exception:
        result = {"status": "failed", "reasons": ["conversion_unsupported_or_worker_error"]}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
