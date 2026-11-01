# Decision 0002: S02 tenant identity and dataset ingestion

Date: 2026-11-02 (Asia/Kolkata)

## Tenant schema and migration policy

- Use psycopg and numbered PostgreSQL SQL files. Each migration runs in its own transaction under a PostgreSQL advisory lock. The migration ledger stores SHA-256; an already-applied migration whose bytes change is rejected.
- Ship migration SQL inside the application wheel so an installed CLI can migrate without a source checkout.
- Tenant ownership is `NOT NULL` on owned rows. Composite foreign keys prevent a dataset, upload session, artifact, requirements snapshot or audit actor from linking across tenants. Dataset versions are immutable rows; updates create a new version with a same-project predecessor.
- Keep deletion tombstones and audit history. Physical object deletion is retryable; metadata is not hard-cascaded away.

## Authentication boundary

- Local development selects one of two fixed identities, `alice` or `bob`, using `X-Local-Identity`; omission selects Alice for a frictionless local demo. The selector never names a tenant and is accepted only when `AUTH_MODE=local`, `APP_ENV=development`, API bind is an IP loopback address, and the direct socket peer is loopback. Forwarded headers do not influence this decision; the developer server disables Uvicorn proxy-header interpretation.
- External mode uses PyJWT RS256 verification with a configured public key, exact issuer and audience, and required expiration, issuer, audience and subject claims. The database maps `(issuer, subject)` to a principal and tenant. Any tenant claim in the token is ignored. No live IdP or external deployment was provisioned or validated in S02.
- External mode currently uses one static public key. Key rollover/JWKS, provider onboarding and production TLS/proxy configuration are operational deployment work and must be completed before external exposure.

## Artifact storage and validation

- MinIO is the local S3-compatible store. Objects use server-generated `tenants/{tenant}/datasets/{dataset}/uploads/{session}/original` keys. Bucket contents and credentials are private; public ACLs and client-controlled keys are not used.
- Upload and artifact download use authenticated API streaming instead of presigned links, so ownership, session expiry and deletion state are checked on every request. The API counts streamed bytes even when `Content-Length` is missing or false, hashes with SHA-256, writes to a mode-0700 temporary directory and does not load the whole upload into API memory.
- File structure is checked in a subprocess with CPU, address-space, output and wall-time limits. Supported representations are UTF-8 CSV with a unique non-empty header and rectangular rows; NDJSON with nonblank JSON object records; Parquet decoded using PyArrow; and gzip-wrapped NDJSON. Other archive/codec types are rejected. This validates physical structure only; it does not infer a typed schema, preserve source ordering guarantees or convert data.
- Raw cap defaults to 256 MiB; decompressed cap defaults to 1 GiB; temporary disk reservation defaults to 1 GiB; up to four active transfers/finalizations and three open upload sessions per tenant are allowed. Upload sessions expire after 15 minutes; retention defaults to seven days and is configurable from 1–30 days. These are policy defaults, not measured throughput guarantees.

## Deletion and recovery

- Project/dataset deletion first marks rows inaccessible and tombstoned, records an audit event, then attempts an idempotent S3 delete. Failed physical deletion remains `delete_pending`; `data-optimizer cleanup-expired` retries. Expired incomplete sessions, failed transfers and dataset copies past retention use the same path.
- Completed object retention follows the dataset expiry, not the shorter upload-session TTL. The API denies expired content immediately even if the cleanup command has not run.
- Deletion covers only copies stored by this application. It does not touch external source systems. A download that already started cannot be recalled. Local MinIO has no object versioning enabled; external storage must separately configure encryption, TLS, version/lifecycle policy and backup/deletion expectations.
