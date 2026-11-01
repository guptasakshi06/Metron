"""Actual Docker experiments and destructive-in-container boundary probes."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from data_optimizer.benchmarking.models import BenchmarkRequest, SandboxLimits
from data_optimizer.benchmarking.service import benchmark
from data_optimizer.candidates.models import ConversionRequest
from data_optimizer.conversion.service import convert, list_candidates
from data_optimizer.sandbox import docker
from test_benchmarking import artifacts  # noqa: F401

pytestmark = pytest.mark.benchmark_sandbox


@pytest.fixture(scope="module")
def image() -> str:
    return docker.image_id()


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    tmp_path.chmod(0o755)
    (tmp_path / "allowed.txt").write_text("allowed")
    return tmp_path


def probe(image: str, snapshot: Path, code: str, **updates: object) -> docker.SandboxResult:
    limits = SandboxLimits.model_validate(dict(wall_seconds=10, **updates))
    return docker.run(image, snapshot, limits, command=("-c", code))


def test_actual_fresh_and_warm_matrix(artifacts: tuple[Path, ...], image: str) -> None:  # noqa: F811
    before = {p: (p / "manifest.json").read_bytes() for p in artifacts}
    reports = [
        benchmark(artifacts, BenchmarkRequest(repeats=3, warmups=warmups), image=image)
        for warmups in (0, 1)
    ]
    assert len(reports[0].trials) == 12
    for report in reports:
        assert report.stop_reason == "completed"
        assert all(t.status == "passed" for t in report.trials), report.model_dump_json()
        assert all(s.observations == 3 and s.p95_seconds is None for s in report.summaries)
        assert all(
            t.observation and t.observation.cpu_seconds > 0 and t.observation.peak_rss_kib > 0
            for t in report.trials
        )
        assert report.environment["worker_memory.max"] == str(1024 * 1048576)
        assert report.environment["worker_duckdb"]
    assert all(
        t.observation and t.observation.cache.startswith("fresh_process") for t in reports[0].trials
    )
    assert all(
        t.observation and t.observation.cache.startswith("warm_process") for t in reports[1].trials
    )
    assert all((p / "manifest.json").read_bytes() == data for p, data in before.items())


def test_network_filesystem_and_privileges_are_restricted(image: str, snapshot: Path) -> None:
    result = probe(
        image,
        snapshot,
        """
import os, socket
from pathlib import Path
assert os.getuid() == 65534
assert Path('/input/allowed.txt').read_text() == 'allowed'
for path in ('/input/write', '/app/write', '/etc/write'):
    try:
        Path(path).write_text('no')
        raise AssertionError('write escaped')
    except OSError:
        pass
assert not Path('/var/run/docker.sock').exists()
assert set(p.name for p in Path('/sys/class/net').iterdir()) == {'lo'}
try:
    socket.create_connection(('1.1.1.1', 443), timeout=.2)
    raise AssertionError('network escaped')
except OSError:
    pass
assert 'NoNewPrivs:\\t1' in Path('/proc/self/status').read_text()
print('restricted')
""",
    )
    assert result.status == "passed" and result.stdout.strip() == b"restricted"


def test_engine_external_io_and_extensions_remain_disabled(image: str, snapshot: Path) -> None:
    result = probe(
        image,
        snapshot,
        """
from data_optimizer.workloads.runner import connection
from data_optimizer.integrity.models import IntegrityOptions
with connection(IntegrityOptions()) as db:
    for sql in ["SELECT * FROM read_csv('/etc/passwd')", "LOAD httpfs", "INSTALL httpfs",
                "COPY (SELECT 1) TO '/tmp/query-write'", "SET enable_external_access=true"]:
        try:
            db.execute(sql)
        except Exception:
            pass
        else:
            raise AssertionError('engine restriction escaped')
print('engine_restricted')
""",
    )
    assert result.status == "passed" and result.stdout.strip() == b"engine_restricted"


def test_multiple_manifest_parts_are_loaded_without_rewriting(image: str, tmp_path: Path) -> None:
    from test_benchmarking import REPO

    source = tmp_path / "many.ndjson"
    source.write_bytes((REPO / "examples/s04-events.ndjson").read_bytes() * 32)
    request = ConversionRequest.model_validate_json(
        (REPO / "examples/s05-conversion-request.json").read_bytes()
    )
    listed = list_candidates(source, request).candidates
    configs = (
        listed[0].configuration,
        listed[2].configuration.model_copy(update={"target_file_bytes": 1024}),
    )
    outcomes = [convert(source, tmp_path / "outputs", request, c) for c in configs]
    assert all(o.manifest and o.artifact_prefix for o in outcomes)
    assert outcomes[1].manifest and outcomes[1].manifest.file_count > 1
    directories = tuple(Path(o.artifact_prefix) for o in outcomes if o.artifact_prefix)
    report = benchmark(directories, BenchmarkRequest(repeats=1), image=image)
    assert all(t.status == "passed" for t in report.trials)
    assert len(report.trials) == 2


def test_hang_does_not_stop_another_assessment(image: str, snapshot: Path) -> None:
    limits = SandboxLimits(wall_seconds=0.5)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as executor:
        hanging = executor.submit(
            docker.run, image, snapshot, limits, command=("-c", "import time; time.sleep(100)")
        )
        healthy = executor.submit(probe, image, snapshot, "print('healthy')")
        assert hanging.result().status == "timeout"
        assert healthy.result().stdout.strip() == b"healthy"
    assert time.monotonic() - started < 15


def test_actual_memory_and_cpu_limits(image: str, snapshot: Path) -> None:
    memory = probe(image, snapshot, "x=[bytearray(8*1024*1024) for _ in range(100)]", memory_mib=64)
    assert memory.status == "memory_limit" and memory.oom_killed
    cpu = probe(
        image,
        snapshot,
        "import signal,os; signal.signal(signal.SIGXCPU, lambda *_: os._exit(152))\n"
        "while True: pass",
        cpu_seconds=1,
    )
    assert cpu.status == "cpu_limit"


def test_scratch_and_output_limits(image: str, snapshot: Path) -> None:
    disk = probe(
        image,
        snapshot,
        """
import errno
try:
    from pathlib import Path
    for index in range(4):
        Path('/tmp/full' + str(index)).write_bytes(b'x' * 524288)
except OSError as error:
    assert error.errno in {errno.ENOSPC, errno.EFBIG}
    print('disk_limit')
else:
    raise AssertionError('disk escaped')
""",
        scratch_mib=1,
    )
    assert disk.status == "passed" and disk.stdout.strip() == b"disk_limit"
    output = probe(image, snapshot, "import os; os.write(2,b'x'*100000)", output_bytes=1024)
    assert output.status == "output_limit" and not output.stdout


def test_running_cancellation_and_no_orphans(image: str, snapshot: Path) -> None:
    started = time.monotonic()
    result = docker.run(
        image,
        snapshot,
        SandboxLimits(),
        command=("-c", "import time; time.sleep(100)"),
        cancelled=lambda: time.monotonic() - started > 0.5,
    )
    assert result.status == "cancelled"
    assert not docker.control(["ps", "-aq", "--filter", "label=data-optimizer.benchmark=true"])


def test_running_budget_is_an_explicit_result(image: str, snapshot: Path) -> None:
    result = docker.run(
        image,
        snapshot,
        SandboxLimits(),
        command=("-c", "import time; time.sleep(100)"),
        budget_deadline=time.monotonic() + 0.5,
    )
    assert result.status == "budget_exhausted"
