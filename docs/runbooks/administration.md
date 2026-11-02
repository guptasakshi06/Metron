# Local administration and recovery

This release supports one host with separate API, dispatcher and worker processes sharing
a private worker workspace. PostgreSQL owns business state; Redis/RQ carries UUID-only JSON
deliveries; MinIO retains private raw copies/results. The benchmark worker image runs as
an unprivileged user with no network, read-only inputs/root, bounded tmpfs and cgroup limits.
Profiling/conversion use bounded subprocesses, not separate network namespaces. The API
must not receive a Docker socket or unrestricted access to worker scratch in an external
deployment. Local process separation is not production OS isolation.

## Settings, access and monitoring

Copy `.env.example` only for local development. Configure all processes consistently;
`make dev` reads the same settings as CLI workers. Local identity mode accepts fixed
Alice/Bob identities from direct loopback peers only; forwarded headers cannot authorize
a remote peer. `APP_ENV=production` rejects `AUTH_MODE=local`. External use requires a
maintained login/identity service, verified RS256 public key, exact issuer/audience and
database principal mappings, authenticated frontend token flow, HTTPS, private service
network, private object-store credentials/encryption, host quotas and retention policy.
External login refresh, key rotation and a live IdP remain untested. Use deployment-specific
secrets; no `VITE_` provider keys, shipped demo passwords or public MinIO/DB/socket ports.

`/health` proves process liveness; `/ready` probes actual services but does not validate
migration completeness. Run `make migrate` (checksum ledger), `make job-metrics`, and inspect
sanitized dispatcher/worker logs. Queue age, retries, stop reasons and active work are real
state. Logs must not contain raw records, tokens, provider keys, bill notes or parser errors.
The release tests use explicit synthetic secret markers. Retain logs under an appropriate
local policy; the app does not provide a production monitoring/alerting service.

Default limits are policies, not guaranteed capacity: 256 MiB raw, 1 GiB decoded, 30-second
upload validation, seven-day copies, two active/one running job per tenant, three attempts,
30-second lease and 2 GiB monitored workspace. Full worker requests also carry independent
limits. Inspect [measured envelopes](../release-readiness.md) before accepting larger jobs.
The workspace monitor is not a hard filesystem quota; provision a separate bounded volume.

## Expiration and cleanup

```sh
make cleanup-expired
make cleanup-assessments
make dispatch-jobs  # runs continuously; reconciles durable intent and stale leases
make worker
```

Raw/upload expiration first tombstones access and records retryable deletion. Cleanup can
be rerun after an object-store outage; expiry/deletion prevents reads immediately even
before bytes are removed. Completed uploads expire by their chosen copy-retention date,
not by upload-session TTL. Cleanup never deletes external source systems. Assessment scratch
and labeled containers are removed only within owned/expired job scope. Never run global
`docker prune` or delete shared workspace while jobs are active. A killed parent/daemon may
leave stopped containers/snapshots; recover the durable assessment and rerun scoped cleanup.

Download grants require owner authentication on every access and expire within ten minutes
or earlier raw-copy expiry/deletion. They are not anonymous signed S3 URLs. Revoking a grant
cannot erase downloaded files. Reports, savings history and reassessment comparisons inherit
the input retention gate; long-term metadata-only history after raw expiry is not implemented.
Decide retention before upload; backups must never silently extend user-visible retention.

## Backup and restore drill

Stop admission and quiesce API/dispatcher/workers before a coordinated recovery point.
Back up metadata, object bytes and compatible worker checkpoints together. Retain image
digests, dependency locks, migrations and private configuration separately. Redis may be
reconstructed from PostgreSQL intent; it is not the source of assessment truth. Reconstructing
without published checkpoints can rerun work before durable trial publication; exactly-once
execution in that interval is not guaranteed.

Use PostgreSQL 17 tools and protected backup destinations. For the default local project:

```sh
docker compose -p data-optimizer-local -f infra/compose.yaml exec -T postgres \
  pg_dump -U data_optimizer -d data_optimizer -Fc --no-owner --no-acl > metadata.dump
# Create a NEW empty recovery database; never overwrite a running application's database.
docker compose -p data-optimizer-local -f infra/compose.yaml exec -T postgres \
  createdb -U data_optimizer data_optimizer_recovery
docker compose -p data-optimizer-local -f infra/compose.yaml exec -T postgres \
  pg_restore -U data_optimizer -d data_optimizer_recovery --exit-on-error --no-owner --no-acl \
  < metadata.dump
```

On hosts with legacy Compose, replace `docker compose` with `docker-compose`. Restore only
trusted archives: dumps include executable schema/functions. See PostgreSQL's
[pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html) and
[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html) contracts.

The S14 automated drill uses `pg_dump -Fc -n ISOLATED_SCHEMA` from the pinned running image,
restores to a newly generated database, verifies all eight migration checksums plus exact
result/bundle/history bytes, owner denial and immutable triggers, then drops only that
temporary database. It also removes/restores one test result object to verify a missing
object returns a sanitized 503. The existing private object bucket is retained through the
metadata drill; an independent object-store disaster restore is **not** claimed.

For a local stopped-stack storage backup, copy/snapshot the Compose `minio_data` and
`postgres_data` volumes using the host's backup tool while services are stopped. Discover
actual volume names using Compose; never infer paths or modify Docker's live volume files.
Store encrypted, access-controlled copies and verify hashes. External S3 recovery needs
versioning/backup and lifecycle rules consistent with the application's tombstones and
chosen retention; this is a deployment prerequisite requiring a provider-specific drill.

Before reopening traffic: point the recovery API at the new database and matching private
bucket/workspace; apply checksum-verified migrations; enforce expired/deleted tombstones;
check owned result SHA-256/length and exports/history; test the second tenant; reconcile
queued/stale jobs; run cleanup and metrics; then resume admission deliberately. Retain the
prior stack and copies for rollback. Never disable immutable triggers to force a restore.
No production restore, production reader switch or paid backup service was exercised.
