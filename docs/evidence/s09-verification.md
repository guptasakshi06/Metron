# S09 verification — 2026-11-02 (Asia/Kolkata)

S09 completed with real local PostgreSQL, MinIO, Redis/RQ subprocess workers and Docker.
No external provider, production dataset or public deployment was used.

| Command | Result |
| --- | --- |
| `UV_OFFLINE=1 make check` | Ruff, strict mypy (78 files), ESLint, TypeScript passed |
| `UV_OFFLINE=1 make test` | 303 backend + 3 frontend tests passed |
| `UV_OFFLINE=1 make test-integration` | All 31 then-present service tests passed in 38.60s |
| `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend pytest -m integration backend/tests/integration/test_assessments.py::test_operational_commands_report_real_state_and_cleanup -q` | Final additional operational CLI test passed in 0.49s; actual DB status metrics, cleanup and dispatch commands |
| `UV_OFFLINE=1 make benchmark-image` | Hash-locked image rebuilt with RQ and final source |
| `UV_OFFLINE=1 make test-benchmark` | All 10 real Docker tests passed in 28.09s on final image |
| `UV_OFFLINE=1 make build` | Final wheel/sdist and Vite production build passed |
| `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend python scripts/verify-s09-package.py` | Four commands available outside repository; all five SQL migrations packaged |
| `uv run --locked --project backend ruff check scripts/verify-s09-package.py` | Passed |
| `make infra-down` | Only project-local services/network removed; named volumes preserved |

Logs: [checks](s09-check.log), [unit/frontend tests](s09-test.log),
[service integration](s09-integration.log), [Docker tests](s09-benchmark.log),
[build](s09-build.log). Source hashes/environment/boundaries:
[s09-verification-results.json](s09-verification-results.json).
Final wheel hash: [s09-package-results.json](s09-package-results.json).

## Verified behavior

- Actual loopback Uvicorn HTTP project creation, NDJSON streaming upload/finalization,
  assessment HTTP 202, real RQ execution, measured recommendation and private result download.
  Four actual configurations passed integrity and timed repeats; synthetic amplified prices
  explain the fixture's `change` outcome, not a customer savings claim.
- PostgreSQL migrations on empty isolated schemas and repeated checksum-verified application.
  Immutable inputs/requirements and append-only evidence are bound by tenant and assessment.
- Four concurrent identical submissions produce one logical ID. Changed idempotency inputs
  conflict; tenant active-job quota, one-running-job admission and other-tenant progress work.
  Cross-tenant status/cancel/recommendation/result access returns 404.
- Worker work-horse SIGKILL after a published matrix; new RQ worker recovers after lease
  reconciliation. Existing matrix hashes remain unchanged and final matrix has twelve unique
  candidate/repeat pairs, with two durable attempts. Unpublished work can run again.
- Lost/transient queue delivery and partial Redis queue-list loss are repaired from PostgreSQL.
  Reconciliation does not grow an unconsumed queue. Storage publication outage retries without
  duplicating the assessment; terminal redelivery does not add attempts.
- Active Docker cancellation removes the running scoped container and stops remaining
  configurations. Queued cancellation executes no attempt. Trusted partial evidence remains
  separated from the stopped lifecycle. Lower-level sandbox restrictions/resource gates pass.
- Local metadata import stays `local_profile`/not server-inspected and yields scenario guidance.
  Server raw profiles use `server_profile`/server-inspected; forged server-origin imports fail.
  Unknown costs/workloads never become computed savings. Schema clarification and raw-byte
  quota failures have explicit reasons. Oversized API requests and expired access are rejected.
- Result/project deletion denies access immediately. Retryable cleanup removes owned result
  objects, workspace and expired evidence while preserving source systems/audit tombstones.
- Operational metrics/cleanup/dispatcher CLI smoke ran against real isolated service state.

## Limits and intermediate failures

Python 3.12.3, RQ 2.12.0, croniter 6.2.4, PyArrow 26.0.0, DuckDB 1.5.6.
Final benchmark image: `sha256:c870f0d43bc38227568597123a76e587230aecec3b66fcdc5dbc30cb2ed6d09d`.
The existing Starlette/httpx TestClient deprecation warning remains.

One intermediate full unit run returned `invalid_structure_or_unsupported_type` in the existing
128 MiB quota test. Isolated resource diagnostics returned MemoryError, the isolated test passed,
and subsequent full unit suites passed unchanged. Its exact intermittent cause remains unproven;
S14 retains resource/capacity calibration. No test expectation was weakened. Early implementation
failures (typing/imports and a restart test initially killing the RQ parent but leaving its separate
work-horse process group alive) were corrected before final verification.

This is a local single-host shared-workspace topology, not multi-host failover or exactly-once
external billing. Cancellation/retention and monitored workspace limits are checked each second
and at stage boundaries; filesystem-wide hard disk quotas remain deployment work. Source paths,
raw records and credentials are not logged. The API never invokes Docker, but production must
also enforce OS/container socket isolation. No live prices/bills, cloud or cold-cache latency,
external IdP, customer validation, public deployment or production migration was performed.
The browser assessment dashboard is S10 and was not implemented or tested here.
