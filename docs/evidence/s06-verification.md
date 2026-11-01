# S06 verification — 2026-11-02, Asia/Kolkata

S06's three acceptance gates passed locally. This is synthetic fixture and boundary
evidence, not production/cloud capacity or a recommendation.

## Commands and results

Run from the project root using the existing project-local tools:

| Command | Observed result |
| --- | --- |
| `UV_OFFLINE=1 make benchmark-image` | Built locked local image; runtime ID recorded in raw reports |
| `UV_OFFLINE=1 make check` | Ruff, strict mypy (58 source files), ESLint and TypeScript passed |
| `UV_OFFLINE=1 make test` | 191 backend and 3 frontend tests passed; 18 service tests and 9 Docker tests deselected |
| `UV_OFFLINE=1 make test-benchmark` | All 9 real Docker tests passed in 27.10 seconds |
| `UV_OFFLINE=1 make build` | Python wheel/sdist and Vite production build passed |
| `UV_OFFLINE=1 UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend python scripts/verify-s06.py --output-dir docs/evidence` | Actual CLI from extracted wheel, fresh/warm matrices and resource probes passed |
| `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend ruff check scripts/verify-s06.py` | Passed |

The default backend suite includes 12 new deterministic S06 tests; its pre-existing
Starlette/httpx TestClient deprecation warning remains. No PostgreSQL/MinIO integration
suite was rerun: S06 changes no service endpoints, migrations or storage operations.
The shared typed loader's S04 integrity/workload tests pass in the full suite.

## Hardware and observed measurements

Docker 29.1.3 on Linux `7.0.0-28-generic`, x86_64, Intel Core i7-12650H. Image
`sha256:2408f9bd11b4153494e1dc1bb4fe960f2151a00e971b98b1334f763ffa011ed6`.
Python 3.12.3, PyArrow/Arrow C++ 26.0.0, DuckDB 1.5.6, container zlib 1.2.13.
Conversion manifests retain their separate host runtime context (including zlib 1.3).
Image base and dependency hashes are pinned in `infra/worker/`.

Each matrix used 3 interleaved repeats, seed 42, 1 CPU, 1024 MiB memory, no swap,
64 MiB scratch, 64 pids, 30 CPU seconds, 45 wall seconds and 1 MiB combined output.
Worker cgroup evidence was `memory.max=1073741824`, `memory.swap.max=0`,
`cpu.max=100000 100000`, `pids.max=64` for every measured trial. All 24 CLI trials
reproduced the six stored workload-result fingerprints. The original source hash is
unchanged; no labeled benchmark containers remained after cleanup.

The primary fixture has three records and is deliberately tiny. Observed load ranges below
include typed decoding/insertion and database setup; they are not native scan benchmarks.

| Representation | Physical data bytes | Fresh-process load ms (min–max) | Warm-process load ms (min–max) |
| --- | ---: | ---: | ---: |
| Baseline NDJSON | 287 | 9.01–10.06 | 7.89–9.73 |
| gzip NDJSON | 138 | 9.24–10.54 | 8.60–10.17 |
| Snappy Parquet | 1523 | 19.63–21.61 | 9.19–11.07 |
| Zstandard Parquet | 1593 | 20.24–22.61 | 9.06–11.50 |

The sum of six query execute/fetch times ranged 2.58–4.04 ms in fresh processes and
1.46–1.94 ms after one full untimed replay. Process peak RSS ranged 102648–121764 KiB.
Per-query raw timings, median, min/max and sample standard deviation are preserved in
[fresh evidence](s06-benchmark-fresh.json) and [warm evidence](s06-benchmark-warm.json).
Three observations per query do not validate p95; all p95 fields are null. OS cache is
uncontrolled and is pre-read by hash verification in both modes. These numbers do not
identify a general format winner or establish supported upload capacity.

## Acceptance evidence

1. **Comparable repeatable experiments:** the CLI's baseline/gzip/Snappy/Zstandard matrices
   passed all repeated result-fingerprint checks in both cache modes. Deterministic unit
   tests cover seeded round scheduling. A separate Docker test loads a 96-row fixture
   from multiple actual Parquet parts, without concatenation or source rewriting.
2. **Resource isolation:** actual Docker probes stop an excessive allocation at 64 MiB
   with OOMKilled and exit 137 (~0.204 s), a CPU loop at 1 CPU second with exit 152
   (~1.155 s), sleeping work at a 0.4-second wall limit (~0.402 s), output at 1024 bytes
   (~0.125 s), and active callback cancellation (~0.452 s after attach). See
   [raw resource results](s06-resource-results.json). Docker tests additionally fill a
   1 MiB tmpfs with multiple files, enforce combined stderr output limits, stop an active
   assessment budget, and verify another concurrent assessment completes while a hanging
   one times out. These timings exclude create/removal overhead.
3. **Integrity lineage:** complete manifests and passed S04 reports accompany each usable
   trial; worker and parent verify current query hashes. Corrupt/missing evidence is an
   explicit integrity failure with no timings; failed/budget/cancelled summaries retain
   null measurements. Request/environment/report fingerprints and artifact part hashes
   are preserved.

Actual boundary probes also deny network access, input/root writes, external DuckDB
readers, COPY output, extension load/install and configuration unlocking. Containers run
as UID 65534 without Docker socket/capabilities and with no-new-privileges.

## Limits and continuation

The benchmark measures full typed load plus in-memory queries; native file-reader
pushdown and persistent serving performance are unmeasured. Physical scanned bytes remain
null. Host cache/CPU frequency/I/O contention are uncontrolled. Conversion resource/time
metrics retain S05 provenance. Generic non-OOM exit 137 remains an unknown failure rather
than a fabricated CPU or memory diagnosis; CPU/alarm handlers avoid host core-dump handling
when Python can deliver the signal. Hard kills during native code can remain ambiguous.

Parent-SIGKILL/power-loss/Docker-daemon-loss recovery was not tested. Normal and handled
cancellation/timeout cleanup passed; worker alarms/CPU limits provide a fallback, but
stopped containers/snapshots may need deliberate cleanup after a crash. No API, live cloud,
customer/pilot, price or production result is claimed. See [benchmark method](../benchmark-method.md).
Next is S07 pricing and economics; S08 must respect this benchmark execution model.
