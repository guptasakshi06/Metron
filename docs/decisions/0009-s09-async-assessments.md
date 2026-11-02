# Decision 0009: durable assessment intent and fenced local RQ execution

Date: 2026-11-02 (Asia/Kolkata)

- PostgreSQL owns immutable input/request/requirements references, idempotency, quotas,
  lifecycle, attempt counts, cancellation, progress, leases and result references. Migration
  0005 adds assessments plus append-only versioned assessment evidence for server profiles,
  candidate configurations, experiment matrices, price snapshots and recommendations.
  Existing imported `profiles` retain their `local_profile` provenance. Server raw profiling
  marks `server_profile`/`raw_data_inspected_by_server=true` and recomputes evidence hashes;
  the import endpoint rejects attempts to assert server provenance. Evidence shares
  tenant/assessment foreign keys and content fingerprints rather than introducing five
  independently mutable copies of the core contracts.
- The assessment row is the transactional outbox: creation commits queued intent without
  depending on Redis. A separate dispatcher reconciles every two seconds; a successful
  enqueue only postpones reconciliation, never removes durable intent. Deterministic RQ IDs
  suppress queue growth; missing queue entries and stale started records are recoverable.
  Queue payloads contain only an assessment UUID and code-owned function, using RQ's JSON
  serializer. Redis must remain private/trusted. No API route imports worker execution code.
- Use RQ 2.12.0 with locked croniter 6.2.4. Checked official [queue documentation](https://python-rq.org/docs/),
  [workers](https://python-rq.org/docs/workers/) and [job lifecycle](https://python-rq.org/docs/jobs/).
  The worker reads credentials/configuration locally; they are never serialized into jobs.
- One session advisory lock per assessment fences concurrent deliveries; a second lock limits
  each tenant to one running assessment. Admission allows two active assessments per tenant
  by default under a tenant row lock. Dispatch selects the oldest due assessment per tenant
  and orders tenants by last delivery. This is bounded local admission, not a distributed
  weighted fairness or billing scheduler.
- Heartbeats refresh a 30-second lease and check cancellation, source/metadata deletion,
  retention, wall time and workspace bytes. Three attempts and capped exponential delays
  bound transient retries. Worker death recovers after lease expiry and reconciliation.
  Shared durable local workspace and existing fingerprint-checked S08 checkpoints preserve
  published measurements. Database locks are the authority even when RQ delivery repeats.
- Cancellation reaches profiling, candidate generation, conversion and Docker trials.
  Check actual state at stage boundaries and before publication. Progress counts completed
  configurations/trials, never invented percentages. Keep valid partial evidence and a stopped
  lifecycle/reason; missing decision inputs produce `needs_input` with scenario guidance.
- Original copies are downloaded with byte/hash checks. Private result JSON is uploaded to
  MinIO and bound by SHA-256/length. All API reads recheck tenant, project, source and expiry.
  Job-scoped temporary directories and Docker labels permit retention cleanup and orphan
  recovery without touching unrelated files/containers. Cleanup uses the same worker lock.
- The API supplies server-owned tenant/assessment IDs and clamps processing ceilings.
  Logs contain IDs, stages, counts and controlled failure categories; no rows, request bodies,
  credentials or exception text. Metrics expose status counts and oldest age.

## Boundaries

This is a single-host local MVP worker topology with a durable shared workspace. An API
process never invokes Docker; production must additionally enforce OS/container separation
and deny the API account Docker socket access. Docker itself remains privileged infrastructure.
A power loss or crash before durable measurement publication can repeat an unrecorded trial;
no exactly-once external execution/billing guarantee is claimed. Recovery does not charge money
or invoke providers. Workspace quota is monitored once per second plus stage boundaries; per-file,
subprocess and Docker limits are enforced separately. It is not a filesystem-wide hard disk quota.

After a process dies, the next admitted worker removes only containers with that assessment's
label. Expired/deleted job cleanup also removes scoped containers, private scratch, result JSON
and evidence. Run cleanup explicitly; no production scheduler is provisioned. Input/audit tombstones
remain for idempotency/accountability. No automatic production migration, cloud performance,
real tariff/customer saving, multi-host failover, external IdP or public deployment is verified.

Run commands and API examples: [assessment runbook](../runbooks/assessments.md).
