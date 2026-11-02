# Asynchronous assessments (S09)

The service wraps the real local S08 profile → conversion/integrity → Docker measurements →
itemized cost → decision pipeline. The dashboard is S10. Prices in the shipped fixture are
explicitly invented; measured timings/bytes are local sample observations.

## Start locally

From the project root, after `make setup`:

```bash
make infra-up
make migrate
make seed-local
make storage-init
make benchmark-image
make dev
```

In two additional terminals at the same project root:

```bash
make dispatch-jobs
```

```bash
make worker
```

`make dev` starts the API/frontend only. The dispatcher and worker are separate processes;
start both to execute jobs. All processes must use the same environment, queue, database,
bucket and **absolute/shared local** `ASSESSMENT_WORK_DIR`. The API needs no Docker calls;
only the worker uses Docker. Never expose Redis, local auth or the Docker socket publicly.
Local identities are fixed `alice` (default) and `bob`, selected by `X-Local-Identity` on loopback.
For external use, first configure verified JWT authentication and separate OS/container access.

## Submit and inspect

Upload/finalize an owned CSV, NDJSON or Parquet dataset using the
[ingestion runbook](ingestion.md). For example, after obtaining PROJECT_ID and DATASET_ID
from those responses, generate the submission from the existing typed fixture:

```bash
.tools/uv-bin/uv run --locked --project backend python - PROJECT_ID DATASET_ID <<'PY'
import json
import sys
from pathlib import Path
request = json.loads(Path('examples/s08-assessment-request.json').read_text())
Path('/tmp/s09-submission.json').write_text(json.dumps({
    'project_id': sys.argv[1], 'dataset_id': sys.argv[2], 'request': request,
}))
PY
curl -fsS -X POST http://127.0.0.1:8000/v1/assessments \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: local-example-1' \
  --data-binary @/tmp/s09-submission.json
```

Replace the positional PROJECT_ID/DATASET_ID placeholders with actual returned UUIDs. The
fixture reader expects the NDJSON event fixture and its workload/schema; edit `request`
for other data. Schema overrides, workload and price assumptions are explicit inputs, not
inferred customer facts. Client conversion ownership IDs are replaced by the authenticated
server IDs. Resource ceilings are capped by settings and recorded in the returned report.

HTTP 202 returns `id`, input/request fingerprints, status, progress, immutable requirements ID
and expiry. Use the returned ID in place of ASSESSMENT_ID:

```bash
curl -fsS http://127.0.0.1:8000/v1/assessments/ASSESSMENT_ID
curl -fsS http://127.0.0.1:8000/v1/assessments/ASSESSMENT_ID/recommendations
curl -fsS http://127.0.0.1:8000/v1/assessments/ASSESSMENT_ID/result
curl -fsS -X POST http://127.0.0.1:8000/v1/assessments/ASSESSMENT_ID/cancel
curl -fsS 'http://127.0.0.1:8000/v1/assessments?project_id=PROJECT_ID'
```

The list returns the newest 100 visible owned assessments. All reads, including result bytes,
recheck project/dataset/profile ownership, deletion and expiry; another tenant receives 404.
Raw transformed files remain private worker artifacts and have no arbitrary-path API.
`/result` is the full measured JSON evidence report; `/recommendations` returns its decision.
Report/export bundles and migration commands are S12.

Idempotency keys are required, tenant-scoped and limited to 128 characters. The same normalized
submission/key returns the same logical assessment, even after completion; changed inputs return
409. A deleted/expired original assessment returns 404 rather than creating a duplicate.
A request above 512 KiB returns 413, invalid contracts/reader format return 422, active-job quota
returns 429. A result not yet published returns 409; a dependency/integrity failure returns 503.

For reviewed metadata, use `profile_id` from the S03 import endpoint instead of `dataset_id`.
For startup-only guidance omit both. These produce `needs_input`, `scenario_guidance` and
`insufficient_evidence`, with no benchmark or computed savings.
Profiles produced from uploaded raw data are explicitly `server_profile` with
`raw_data_inspected_by_server=true`; a supplied local report cannot claim that provenance. A raw-data assessment also
uses `needs_input` if required workload/cost/capability evidence is missing. Inputs are immutable;
submit a new assessment/key after clarification.

## Recovery, cancellation and retention

PostgreSQL stores queued dispatch intent in the same transaction as assessment creation.
The dispatcher polls every two seconds. Redis loss/unavailability does not discard that row.
Successful queue deliveries are reconciled after 30 seconds by default. Workers heartbeat
once a second and hold PostgreSQL session locks, preventing duplicate concurrent execution.
One assessment per tenant runs at a time, with at most two active admitted by default.

Run these after restarting infrastructure/worker processes:

```bash
.tools/uv-bin/uv run --locked --project backend data-optimizer dispatch-jobs --once
.tools/uv-bin/uv run --locked --project backend data-optimizer worker --once
make job-metrics
```

`--once` means one dispatch pass or RQ burst. An unexpired running lease must expire first.
Transient DB/storage failures retry up to three attempts with delays 2, 4… capped at 60 seconds;
nontransient pipeline/input failures terminate with a controlled reason. Schema clarification
returns `needs_input` (for example `schema_override_mismatch`); reader quota failures retain
their explicit code (for example `raw_byte_quota`) instead of masquerading as missing input. A dead DB connection
may prevent persisting the error; lease recovery handles that attempt later. Lost/stale RQ
records are reconciled against PostgreSQL. Do not delete checkpoints to "retry" a job.

A cancellation response is a request, not proof an active container has stopped. Poll until
`cancelled`; queued work cancels immediately and active processes check once a second or at
stage boundaries. Docker cancellation kills/removes the scoped active container. Completed
validated work may remain in a partial result, with lifecycle and `stop_reason` identifying the
stop. Hard outer time/workspace quotas also stop the assessment with their explicit reason.
Search/benchmark budget stops retain measured coverage and never imply exhaustive optimality.

Results/workspaces expire with the source dataset, or the default seven-day copy retention
for metadata/startup runs. Deletion or expiry immediately denies result access and stops active
work at the next heartbeat. Explicitly run both cleanup commands:

```bash
make cleanup-expired
make cleanup-assessments
```

Cleanup retries private object deletion and removes job-scoped files/containers/evidence only
while holding the worker lock. Rerun after a transient failure or while a worker was still exiting.
It preserves external sources and immutable request/audit tombstones. No automatic production
retention scheduler is installed. Abrupt worker death can leave scoped scratch/containers until
recovery or cleanup; published valid trials are reused. A crash before durable publication can
repeat an unrecorded trial. This is not an exactly-once external billing guarantee.

Settings: `MAX_ACTIVE_ASSESSMENTS_PER_TENANT=2`, `MAX_JOB_ATTEMPTS=3`,
`JOB_LEASE_SECONDS=30`, `MAX_JOB_OUTPUT_BYTES=268435456` per configuration,
`MAX_JOB_WORKSPACE_BYTES=2147483648` monitored at heartbeats/stage boundaries, plus existing
reader/integrity/query/assessment limits. The workspace ceiling is not a hard filesystem quota.
Use host filesystem quotas for an externally accessible deployment. Production topology,
maximum capacity, multi-host failover, cold-cache/cloud latency and real savings remain unverified.

Verification: `make test-integration` requires PostgreSQL, MinIO, Redis, Docker and the benchmark
image. It includes actual subprocess RQ jobs and loopback Uvicorn HTTP, SIGKILL recovery and
active-container cancellation. `make test-benchmark` verifies the lower-level Docker boundary.
