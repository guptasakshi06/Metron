# S04 verification record

Date: 2026-11-02 (Asia/Kolkata). Local synthetic fixtures; no production/customer data.
Branch: main, existing commit 869c28e. S03 and S04 changes remain uncommitted.

## Commands and observed outcomes

Run from the repository root:

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv add --project backend 'duckdb>=1.4,<2'` | Resolved DuckDB 1.5.6; lockfile updated |
| `UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv add --project backend 'pytz>=2025.2'` | Resolved pytz 2026.6; required for tested TIMESTAMPTZ results |
| `UV_OFFLINE=1 make check` | Passed Ruff, strict mypy (42 source files), ESLint and TypeScript |
| `UV_OFFLINE=1 make test` | Passed 152 backend tests and 3 frontend tests; 18 service integration tests deselected |
| `UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend pytest -q backend/tests/test_workloads.py backend/tests/test_integrity.py` | Final 60 S04 tests passed after final schema-metadata and empty-object regressions |
| `UV_OFFLINE=1 make build` | Final Python sdist/wheel and frontend production build passed |
| `git diff --check` | Passed after handoff formatting correction |

One pre-existing Starlette/httpx TestClient deprecation warning remains. The full suite
passed at 152 tests before the last two S04 regressions; the final focused run includes
both new tests and all other S04 tests. Service-dependent tests were not rerun because
S04 introduces no API/database/object-store integration. Docker services were not started.

CLI commands actually executed:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend data-optimizer \
  integrity-check examples/s04-events.ndjson examples/s04-reordered.ndjson \
  --request examples/s04-integrity-request.json --output docs/evidence/s04-passed.json
UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend data-optimizer \
  integrity-check examples/s04-events.ndjson examples/s04-corrupted.ndjson \
  --request examples/s04-integrity-request.json --output docs/evidence/s04-failed.json
```

Observed exits: 0 for equivalent rows, 1 for changed duplicate multiplicity. Each file
contains five content checks and six actual query comparisons. Both mark performance
not_measured. `s04-cross-format.json` additionally records a passing CSV-to-Parquet
comparison from the generated golden fixtures through the public subprocess verifier.
Generated source hashes were checked before/after and remained unchanged.

Final wheel smoke extracted the built wheel into a temporary directory, set PYTHONPATH
to that extraction, asserted `data_optimizer.__file__` came from the extraction, and
ran `python -m data_optimizer.cli integrity-check` against the example input/request
from a working directory outside the repository. Its child worker also used the
extracted package. Exit 0 and a fingerprint-validated passed report were observed.
The smoke reused installed locked dependencies; it was not a fresh-machine install.

Coverage includes real DuckDB parameterized queries; valid CSV/NDJSON/gzip/Parquet;
lost rows, decimal precision loss, duplicate replacement, shifted/naive timestamps,
coerced IDs, missing/null changes, nested/mixed capabilities, schema metadata beyond
display truncation, exact high-precision decimal query values, null/time/group semantics,
ordering and numeric tolerances. Direct engine attempts at host reads, network reads,
writes, extension install/load and configuration changes were denied. Actual row/spill
quotas fail closed. The parent timeout and raw-spill cleanup test injects TimeoutExpired;
it is a deterministic control-path test, not a measured hanging-query experiment.

## Boundaries

S04 is local correctness evidence, with private temporary raw canonical spill. Engine
settings and resource limits are not a production OS sandbox. Performance/concurrency,
cloud behavior, customer validation and live IdP integration remain unverified. Benchmark
isolation is S06; tenant-scoped assessment evidence persistence/orchestration is S09.
