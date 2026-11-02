# Data Optimizer

Data Optimizer compares analytical dataset representations against a stated workload. It is designed to recommend the best tested feasible option, explain its evidence and preserve unknowns. This repository is being implemented one sprint at a time; the current sprint is recorded in [SPRINT_HANDOFF.md](SPRINT_HANDOFF.md).

## Current implementation: S10

The application has versioned contracts, real health/readiness checks, tenant-scoped project and dataset metadata, authenticated bounded uploads for CSV, NDJSON and Parquet, structural validation, private MinIO object storage, immutable dataset versions, retention/deletion recovery, bounded local typed profiling, reproducible sampling, metadata-only exports and reviewed tenant-scoped profile import. The dashboard now supports project intake, reviewed uploads or metadata, workload/schema/cost editing, asynchronous assessments, cancellation/refresh recovery, baseline comparison and itemized evidence. Recommendations use real local worker measurements; pricing is unknown by default or explicitly synthetic/user supplied. Reports and migration export bundles remain S12.

S04 adds a validated analytical workload DSL, parameterized execution against a fixed
in-memory DuckDB dataset, exact typed cross-format integrity checks preserving duplicate
counts, capability exclusions and versioned local JSON evidence. See the
[workload/integrity runbook](docs/runbooks/workloads-integrity.md) for a passing and a
rejected CLI example. Output equality is a correctness check; performance remains unmeasured.

S05 adds bounded candidate enumeration and atomic local assessment copies: baseline,
gzip NDJSON, Snappy/Zstandard Parquet and workload-guided layouts, with exact integrity,
resource/byte manifests and verified reuse. Run `data-optimizer candidate-list` or
`data-optimizer convert`; see [candidate support and commands](docs/candidate-support.md).
S06 adds Docker-isolated local benchmarking of verified manifests, seeded interleaved
repeats, typed load/query timings, honest cache labels, raw evidence and explicit resource
failures. See [benchmark method and reproduction](docs/benchmark-method.md).
S07 adds immutable synthetic offline price snapshots, reconciled itemized costs, physical
space/copy accounting, migration economics, explicit unknowns and scenario ranges. Run
`data-optimizer cost --request examples/s07-cost-request.json --output /tmp/s07-cost.json`;
see [pricing method, billing boundaries and saved benchmark adapter](docs/pricing-method.md).
S08 ranking and S09 durable asynchronous orchestration are implemented; see the sections below.

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
make infra-up       # required for assessments; Docker Engine + Compose
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

The dashboard uses the Vite `/api` proxy. Connection failures, authorization/expiry and backend dependency errors are actionable in the workspace; the system endpoints above provide per-service readiness diagnostics.

### Developer commands

```bash
make setup       # locked Python sync and npm ci
make check       # generated contract drift, Ruff, mypy, ESLint and TypeScript
make test        # backend contract/API checks and frontend component checks
make test-integration # real PostgreSQL/MinIO tests; not run by make test
make benchmark-image # build the locked local Linux benchmark image
make test-benchmark # real Docker benchmark and isolation tests; not run by make test
make build       # Python wheel/sdist and Vite production output
make demo        # packaged measured CLI demonstration, synthetic prices
make contracts   # regenerate frontend types from executable backend models
make test-browser # real isolated browser/API/RQ/Docker flows; requires Chrome + local infra
```

See [the ingestion runbook](docs/runbooks/ingestion.md) for API examples, the local identity boundary, file validation and retention cleanup. The runbook uses the synthetic fixture at `examples/s02-events.csv`.

The local processing limits in `.env.example` remain provisional policy defaults. The S06
offline benchmark has separate explicit request limits: 1 CPU, 1 GiB memory without swap,
64 MiB scratch, 30 CPU seconds, 45 wall seconds per trial and 600 seconds per matrix.
The fixture/resource evidence establishes those tested paths, not maximum supported dataset
capacity. See the benchmark method; S14 retains operational capacity calibration.

### Dataset and evidence boundaries

The data scope is CSV, NDJSON and Parquet. S02 accepts CSV and NDJSON text plus gzip-wrapped NDJSON and Parquet files, validates actual structure under byte and subprocess resource bounds, fingerprints original bytes, and stores them tenant-scoped. Dataset IDs are stable UUIDs and every replacement is a new immutable version. S03 adds local profiles with conservative, explicit typed semantics; S05 adds bounded local lossless conversion. Existing contracts preserve timezone-aware timestamps, explicit units, decimal precision and unknown values. Future recommendations must distinguish user-supplied, local-profile, server-measured, synthetic and projected evidence. A `change` decision requires measured evidence, an experiment reference and passed integrity.

The benchmark measures full typed decoding/loading followed by in-memory queries; it does
not establish native Parquet pushdown, cloud latency or concurrency. S07 economics produces
labeled forecasts using explicit usage and synthetic or user supplied rates. Ranking,
assessment tables, queues and live external identity-provider integration remain future
work. Local auth is only for loopback development; see
[decision 0002](docs/decisions/0002-s02-ingestion.md) before changing auth/storage settings.

### Local profiling (S03)

Run `uv run --locked --project backend data-optimizer profile INPUT --format csv --output /tmp/profile.json`. This requires no network or API key and exports redacted metadata. See [the profiling runbook](docs/runbooks/profiling.md) for typed overrides, sampling, review/import commands and resource checks, and [dataset semantics](docs/dataset-semantics.md) for supported boundaries. Optional API import uses migration `0004_local_profiles.sql`; run `make migrate` before using it.

## Local assessment and decisions (S08)

Run the real profile → validated copies → Docker benchmark → itemized forecast → decision pipeline:

```bash
uv run --locked --project backend data-optimizer assess examples/s04-events.ndjson \
  --request examples/s08-assessment-request.json \
  --root /tmp/s08-workspace --output /tmp/s08-report.json
```

Requires the local benchmark image (`make benchmark-image`). The example prices are deliberately
amplified **synthetic** rates for tiny-fixture demonstration, not provider quotes or customer savings.
Use a new output filename; reuse the same workspace to resume without repeating completed trials.
Omit the source, or use `--metadata REVIEWED_PROFILE.json`, for scenario guidance without historical
savings. Exit 1 saves an insufficient-evidence report. See [decision method](docs/decision-method.md)
for requirements, materiality, adaptive search and checkpoints. `make demo` builds and runs the
packaged three-path local demonstration into a new temporary evidence directory.

## Asynchronous assessments (S09)

Run `make migrate`, then start `make dispatch-jobs` and `make worker` in separate terminals
while `make dev` runs the API/frontend. Uploads can now complete real background assessments
and expose owned status, recommendations and raw JSON evidence. See the
[assessment runbook](docs/runbooks/assessments.md) for endpoint examples, idempotency, quotas,
retry/cancellation/retention semantics and restart commands. `make job-metrics` reports
operational counts; `make cleanup-assessments` removes expired/deleted private job artifacts.
The S10 dashboard is available at the local frontend URL. See the [browser user flow](docs/user-flow.md).


## Assessment dashboard (S10)

After infrastructure/migrations/seed/storage initialization, build `make benchmark-image`
and run `make dev`, `make dispatch-jobs`, and `make worker` in separate terminals. Open
[the dashboard](http://127.0.0.1:5173), create a project, review retention before uploading
a copy, edit the workload/schema and cost assumptions, and run an assessment. Local-only
Alice/Bob identities are selectable; configured JWT mode instead accepts a verified token
in memory. Costs remain unknown unless explicitly supplied; the optional synthetic example
is invented and clearly labeled. The result includes measured local sample bytes/timings,
feasibility and complete modeled line items, including no-change and missing-evidence paths.

The [dashboard guide](docs/user-flow.md) documents metadata review, draft/session privacy,
refresh/cancellation, schema clarification and raw evidence. [S10 verification](docs/evidence/s10-verification.md)
records the real-service browser checks and responsive screenshots. External login-provider
validation, live prices, production measurements and public deployment remain unverified.

### Optional structured assistance

S11 adds review/edit/confirm intake and grounded evidence cards. The full assessment
works with `LLM_PROVIDER=disabled`. To enable explicitly approved provider requests,
configure server-only `LLM_PROVIDER=openai` and `LLM_API_KEY` after running `make migrate`.
See [AI boundaries and setup](docs/ai-boundaries.md) for model, limits, privacy and
fallback behavior. Run `make test-assistance-browser` for isolated real-service flows;
live provider behavior is separately unverified.

### Report and migration exports (S12)

After an assessment, use **Prepare expiring report links** to download JSON, Markdown,
HTML or the complete ZIP containing all three and `migrate.sh`. Downloads require the
same verified session; links expire after ten minutes or earlier copy retention/deletion.
The export omits business descriptions and free-text provenance notes; schema/workload
parameters remain necessary and may be sensitive. Review before sharing.

Offline export of a saved result:

```sh
uv run --locked --project backend data-optimizer export --report /tmp/result.json --output-dir /tmp/new-handoff
uv run --locked --project backend data-optimizer reproduce /tmp/new-handoff/bundle.json --source examples/s04-events.ndjson --root /tmp/new-replay --output /tmp/new-replay.json
```

Use new destinations and the exact source that produced the report. Reproduction checks
input, workload, engine and benchmark-environment compatibility, then runs the real pipeline.
`sh /tmp/new-handoff/migrate.sh SOURCE NEW_WORKSPACE NEW_RESULT.json` deliberately creates
and validates a local copy for a tested `change`; it preserves originals and switches no reader.
See [export/reproduction guide](docs/runbooks/reports.md) for APIs, validation, canary and rollback.

## Adoption and observed outcomes

S13 adds append-only adoption plans, reviewed manual observation JSON entry/upload, separate
actual/projection/modeled savings history, drift signals and deliberate immutable reassessment.
Start in **Adoption & savings history** on a saved assessment. These are user-supplied records
and comparable-usage models, never provider-verified savings. See the
[observation runbook](docs/runbooks/observations.md) for units, assumptions, reconciliation,
reverts and APIs. `make test-observations-browser` exercises the real local stack.
