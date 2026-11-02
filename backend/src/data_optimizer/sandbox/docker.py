"""No shell, no runtime network, read-only input snapshots and bounded output pipes."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from data_optimizer.benchmarking.models import SandboxLimits, TrialStatus

DEFAULT_IMAGE = "data-optimizer-benchmark:s06"


@dataclass(frozen=True)
class SandboxResult:
    status: TrialStatus
    reason: str
    stdout: bytes = b""
    elapsed_seconds: float = 0
    exit_code: int | None = None
    oom_killed: bool = False


def control(arguments: Sequence[str]) -> str:
    return subprocess.run(
        ["docker", *arguments], check=True, capture_output=True, text=True, timeout=15
    ).stdout.strip()


def image_id(image: str = DEFAULT_IMAGE) -> str:
    # Resolve once, then use the immutable image ID for the entire matrix. Never pull at run time.
    result = control(["image", "inspect", "--format", "{{.Id}}", image])
    if not result.startswith("sha256:") or len(result) != 71:
        raise ValueError("invalid_benchmark_image")
    return result


def create_arguments(image: str, name: str, snapshot: Path, limits: SandboxLimits) -> list[str]:
    path = str(snapshot.resolve())
    if "," in path:
        raise ValueError("unsupported_mount_path")
    return [
        "create",
        "--name",
        name,
        "--label",
        "data-optimizer.benchmark=true",
        "--label",
        "data-optimizer.job=" + os.environ.get("DATA_OPTIMIZER_JOB_SCOPE", "local-cli"),
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--user",
        "65534:65534",
        "--memory",
        f"{limits.memory_mib}m",
        "--memory-swap",
        f"{limits.memory_mib}m",
        "--cpus",
        str(limits.cpus),
        "--pids-limit",
        str(limits.pids),
        "--ulimit",
        f"cpu={limits.cpu_seconds}:{limits.cpu_seconds + 1}",
        "--ulimit",
        "core=0:0",
        "--ulimit",
        "nofile=128:128",
        "--ulimit",
        f"fsize={limits.scratch_mib * 1048576}:{limits.scratch_mib * 1048576}",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size={limits.scratch_mib}m,mode=1777",
        "--shm-size",
        "1m",
        "--log-driver",
        "none",
        "--stop-timeout",
        "1",
        "--mount",
        f"type=bind,src={path},dst=/input,readonly",
        "--entrypoint",
        "python",
        image,
    ]


def run(
    image: str,
    snapshot: Path,
    limits: SandboxLimits,
    *,
    cancelled: Callable[[], bool] | None = None,
    budget_deadline: float | None = None,
    # Code-owned command only; never populated from a benchmark request or data.
    command: Sequence[str] = ("-m", "data_optimizer.benchmarking.worker"),
) -> SandboxResult:
    limits = SandboxLimits.model_validate(limits.model_dump())
    name = "data-optimizer-benchmark-" + uuid4().hex
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    created = False
    try:
        if cancelled and cancelled():
            return SandboxResult("cancelled", "cancelled_before_start")
        control([*create_arguments(image, name, snapshot, limits), *command])
        created = True
        started = time.monotonic()
        process = subprocess.Popen(
            ["docker", "start", "--attach", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        output = bytearray()
        count = 0
        deadline = started + limits.wall_seconds
        with selectors.DefaultSelector() as selector:
            assert process.stdout is not None and process.stderr is not None
            selector.register(process.stdout, selectors.EVENT_READ, True)
            selector.register(process.stderr, selectors.EVENT_READ, False)
            while selector.get_map():
                status: TrialStatus | None = None
                if cancelled and cancelled():
                    status = "cancelled"
                elif budget_deadline is not None and time.monotonic() >= budget_deadline:
                    status = "budget_exhausted"
                elif time.monotonic() >= deadline:
                    status = "timeout"
                if status:
                    return SandboxResult(status, status, elapsed_seconds=time.monotonic() - started)
                for key, _ in selector.select(timeout=0.05):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    count += len(chunk)
                    if count > limits.output_bytes:
                        return SandboxResult(
                            "output_limit",
                            "combined_stdout_stderr_quota",
                            elapsed_seconds=time.monotonic() - started,
                        )
                    if key.data:
                        output.extend(chunk)
        process.wait(timeout=max(0.1, deadline - time.monotonic()))
        state = json.loads(control(["inspect", "--format", "{{json .State}}", name]))
        code, oom = int(state["ExitCode"]), bool(state["OOMKilled"])
        status = (
            "memory_limit"
            if oom
            else "cpu_limit"
            if code == 152
            else "timeout"
            if code == 142
            else ("passed" if code == 0 else "failed")
        )
        return SandboxResult(
            status,
            "termination_cause_unavailable" if code == 137 and not oom else "container_exit",
            bytes(output),
            time.monotonic() - started,
            code,
            oom,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            "timeout", "docker_control_timeout", elapsed_seconds=(time.monotonic() - started)
        )
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        return SandboxResult("failed", "sandbox_unavailable_or_invalid_response")
    finally:
        # Removing by unique name kills the container even if the attach client has died.
        if created:
            control(["rm", "--force", name])
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
