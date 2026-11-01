# Local ingestion runbook

This runbook covers the local PostgreSQL and MinIO implementation in S02. It is not a production deployment recipe.

## Start and initialize

From the repository root:

```bash
cp .env.example .env  # optional; these values are local development defaults
make infra-up
make migrate
make seed-local
make storage-init
make dev
```

`make infra-up` binds PostgreSQL, Redis and MinIO to loopback ports 55432, 56379, 59000 and 59001. `make infra-down` stops only `data-optimizer-local` and preserves named volumes. The default development identity is `alice`; `bob` is a second isolated tenant for local checks. These identities contain no customer records.

## Create, upload and retrieve a dataset

The example file is a synthetic fixture at `examples/s02-events.csv`. The API stores the original bytes; it does not convert or profile them.

```bash
export DATA_OPTIMIZER_PROJECT_ID="$(curl -fsS -H 'X-Local-Identity: alice' \
  -H 'Content-Type: application/json' \
  -d '{"name":"local events"}' http://127.0.0.1:8000/v1/projects | jq -r .project_id)"

export DATA_OPTIMIZER_UPLOAD="$(curl -fsS -H 'X-Local-Identity: alice' \
  -H 'Content-Type: application/json' \
  -d '{"format":"csv","filename":"events.csv","retention_days":7}' \
  "http://127.0.0.1:8000/v1/projects/${DATA_OPTIMIZER_PROJECT_ID}/datasets")"

export DATA_OPTIMIZER_SESSION_ID="$(printf '%s' "$DATA_OPTIMIZER_UPLOAD" | jq -r .upload_session_id)"
export DATA_OPTIMIZER_DATASET_ID="$(printf '%s' "$DATA_OPTIMIZER_UPLOAD" | jq -r .dataset_id)"

curl -fsS -X PUT -H 'X-Local-Identity: alice' \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @examples/s02-events.csv \
  "http://127.0.0.1:8000/v1/uploads/${DATA_OPTIMIZER_SESSION_ID}"

curl -fsS -X POST -H 'X-Local-Identity: alice' \
  "http://127.0.0.1:8000/v1/uploads/${DATA_OPTIMIZER_SESSION_ID}/finalize"

curl -fsS -H 'X-Local-Identity: alice' \
  "http://127.0.0.1:8000/v1/datasets/${DATA_OPTIMIZER_DATASET_ID}"
```

The finalized metadata includes the dataset version, detected format, raw byte count, decompressed byte count, SHA-256 fingerprint and tenant-scoped artifact ID/content route. The content route streams the original upload. Metadata does not reveal the internal object key or storage credentials.

Defaults bound raw uploads to 256 MiB, expanded content to 1 GiB, temporary upload storage to 1 GiB, a transfer to five minutes, and validation to 30 seconds/512 MiB. CSV fields and NDJSON records are capped at 1 Mi characters, JSON strings at 256 Ki characters and nesting at 100 levels. These are configured safety ceilings, not measured capacity claims. Parquet validation checks bounded footer/metadata before decoding and caps decoded buffers under the same expanded-byte budget. Gzip-wrapped NDJSON allows concatenated members subject to the aggregate expanded-byte budget and rejects nested gzip; other archive formats are unsupported.

## Tenant isolation checks

Create a project as Alice, then try to list or fetch that project, its datasets and artifact URL as Bob. Owned resources appear as HTTP 404 to another tenant. Bob can create and upload his own data independently. `X-Local-Identity` accepts only `alice` and `bob`; it is a development selector and is not an authentication scheme for external access.

Run real service integration tests with:

```bash
make test-integration
```

The test fixture creates a random PostgreSQL schema and MinIO bucket, applies migrations twice, seeds local demo identities, and removes only those generated test resources at teardown. The command fails if PostgreSQL or MinIO cannot be reached; it does not skip the integration suite.

## Authentication mode for an external deployment

Do not expose local mode. Set `APP_ENV=production` and `AUTH_MODE=jwt`; configure `AUTH_ISSUER`, `AUTH_AUDIENCE` and `AUTH_PUBLIC_KEY` from the trusted identity provider's RS256 signing key. Provision the exact verified `(issuer, subject)` mapping to a tenant in `principals`; do not accept a tenant ID from a request or JWT claim. Serve the API over TLS, use non-development database/storage credentials, restrict the S3 bucket to the application identity, configure object encryption and operational lifecycle/backup policy, and validate proxy/network boundaries before any external access. S02 did not exercise a live IdP or production environment.

## Expiration and deletion recovery

Uploaded bytes are retained for the chosen dataset retention period (default seven days, maximum 30). The upload reference expires after 15 minutes. Dataset metadata and content routes stop serving expired copies immediately; physical cleanup runs when:

```bash
make cleanup-expired
```

The command handles expired completed copies, incomplete/failed uploads and deletion tombstones. It validates the generated object-key layout before deletion. Storage outages leave durable pending rows for a later retry. Delete project/dataset API requests only affect this application's stored copies; they never delete external source data. Audit rows remain available after deletion.
