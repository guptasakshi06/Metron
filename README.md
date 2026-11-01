# Data Optimizer

Data Optimizer compares analytical dataset representations against a stated workload. It is designed to recommend the best tested feasible option, explain its evidence and preserve unknowns. This repository is being implemented one sprint at a time; the current sprint is recorded in [SPRINT_HANDOFF.md](SPRINT_HANDOFF.md).

## Current implementation: S02

The application has versioned contracts, real health/readiness checks, tenant-scoped project and dataset metadata, authenticated bounded uploads for CSV, NDJSON and Parquet, structural validation, private MinIO object storage, immutable dataset versions, and retention/deletion recovery. The frontend is still a connectivity shell; profiling, assessment, recommendation and report workflows are scheduled for later sprints. It does not display fabricated assessment results.

### Runtime versions

S01 selected Python 3.12, Node.js 24.22.2 LTS and uv 0.13.6. Node and uv are installed in the ignored project-local `.tools/` directory by the bootstrap script; no system-wide changes are made. The frontend package lock and backend `uv.lock` pin resolved dependencies, including PyJWT, boto3 and PyArrow. Use the bundled Node/npm before running frontend commands because the system Node may be older.

On supported Linux x86_64/aarch64 hosts with `curl`, `tar`, `xz` and `sha256sum`:

```bash
bash scripts/bootstrap-tools.sh
export PATH="$PWD/.tools/node24/bin:$PWD/.tools/uv-bin:$PATH"
make setup
```

The script verifies the official Node.js archive against the release checksum and installs a pinned uv release under `.tools`. If downloads are unavailable, install Python 3.12, Node 24 LTS and uv 0.13.6 using their official instructions, then use `make setup`.

### Start the local app

```bash
export PATH="$PWD/.tools/node24/bin:$PWD/.tools/uv-bin:$PATH"
make infra-up       # optional; needs Docker Engine and Compose v2 or legacy docker-compose
make dev            # API http://127.0.0.1:8000 and frontend http://127.0.0.1:5173
```

`make infra-up` starts local-only PostgreSQL, Redis and MinIO in the `data-optimizer-local` Compose project. Defaults bind to loopback ports 55432, 56379, 59000 and 59001 to avoid colliding with common existing services. Development credentials are placeholders and must never be used outside a local machine. Ports can be changed through `.env`; copy `.env.example` to `.env` to override them. `make infra-down` stops only this project and preserves its named volumes.

Apply the PostgreSQL schema and initialize local demo principals and the private object bucket:

```bash
make migrate
make seed-local
make storage-init
```

`GET /health` means only that the API process is alive. `GET /ready` checks PostgreSQL with `SELECT 1`, Redis with `PING`, and MinIO's readiness endpoint. It returns HTTP 503 with per-service status while any required service is unavailable and HTTP 200 only when every probe passes; it does not claim that migrations have been applied.

In a second terminal, inspect the health and versioned policy:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/v1/contracts
```

The frontend fetches those actual routes through its Vite development proxy. A failed API connection and a reachable API whose dependencies are down appear as different states.

### Developer commands

```bash
make setup       # locked Python sync and npm ci
make check       # Ruff, mypy, ESLint and TypeScript
make test        # backend contract/API checks and frontend status checks
make test-integration # real PostgreSQL/MinIO tests; not run by make test
make build       # Python wheel/sdist and Vite production output
make demo        # exits nonzero until the measured assessment pipeline exists
```

See [the ingestion runbook](docs/runbooks/ingestion.md) for API examples, the local identity boundary, file validation and retention cleanup. The runbook uses the synthetic fixture at `examples/s02-events.csv`.

The local processing limits in `.env.example` are provisional policy defaults, not measured capacity: 256 MiB raw upload, a separate 1 GiB decompressed limit, at most 12 candidates and 5 timed repeats, 60 seconds per query, 15 minutes per assessment and a 2 GiB worker memory budget. S06 and S14 must calibrate these values on recorded hardware.

### Dataset and evidence boundaries

The data scope is CSV, NDJSON and Parquet. S02 accepts CSV and NDJSON text plus gzip-wrapped NDJSON and Parquet files, validates actual structure under byte and subprocess resource bounds, fingerprints original bytes, and stores them tenant-scoped. Dataset IDs are stable UUIDs and every replacement is a new immutable version. S02 does not infer typed profiles or transform data. Existing contracts preserve timezone-aware timestamps, explicit units, decimal precision and unknown values. Future recommendations must distinguish user-supplied, local-profile, server-measured, synthetic and projected evidence. A `change` decision requires measured evidence, an experiment reference and passed integrity.

No benchmark, savings calculation, assessment table, queue or live external identity-provider integration is implemented. Local auth is only for loopback development; see [decision 0002](docs/decisions/0002-s02-ingestion.md) and the runbook before changing auth/storage settings. The upload and decompression limits are configurable policy bounds, not measured capacity or cloud guarantees.
