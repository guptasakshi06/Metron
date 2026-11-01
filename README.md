# Data Optimizer

Data Optimizer compares analytical dataset representations against a stated workload. It is designed to recommend the best tested feasible option, explain its evidence and preserve unknowns. This repository is being implemented one sprint at a time; the current sprint is recorded in [SPRINT_HANDOFF.md](SPRINT_HANDOFF.md).

## S01 foundation

The current application foundation includes versioned request/domain contracts, an API liveness route, honest dependency readiness, and a frontend connection shell. Dataset assessment and recommendation workflows are not available yet. The UI displays service connectivity only and does not show sample assessment results.

### Runtime versions

S01 uses Python 3.12, Node.js 24.22.2 LTS and uv 0.13.6. Node and uv are installed in the ignored project-local `.tools/` directory by the bootstrap script; no system-wide changes are made. The frontend package lock and backend `uv.lock` pin resolved dependencies. Use the bundled Node/npm before running frontend commands because the system Node may be older.

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

The API starts without tables or infrastructure. `GET /health` means only that the API process is alive. `GET /ready` checks PostgreSQL with `SELECT 1`, Redis with `PING`, and MinIO's readiness endpoint. It returns HTTP 503 with per-service status while any required service is unavailable and HTTP 200 only when every probe passes. No schema readiness is claimed in S01.

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
make build       # Python wheel/sdist and Vite production output
make demo        # exits nonzero until the measured assessment pipeline exists
```

The local processing limits in `.env.example` are provisional policy defaults, not measured capacity: 256 MiB raw upload, a separate 1 GiB decompressed limit, at most 12 candidates and 5 timed repeats, 60 seconds per query, 15 minutes per assessment and a 2 GiB worker memory budget. S06 and S14 must calibrate these values on recorded hardware.

### Dataset and evidence boundaries

The initial data scope is CSV, NDJSON and Parquet. S01 defines contracts only; it does not parse or transform datasets. IDs are stable UUIDs, timestamps must be timezone-aware, measurements have explicit nonnegative/positive bounds and monetary values use decimal precision with currency. Optional unknown measurements stay `null`. Contracts reject unknown fields. Recommendations distinguish user-supplied, local-profile, server-measured, synthetic and projected evidence. A `change` decision requires measured evidence, an experiment reference and passed integrity.

No benchmark, savings calculation, object upload, assessment table, tenant authentication, queue or production integration is implemented in S01. Do not interpret local disk behavior or the provisional limits as cloud guarantees.
