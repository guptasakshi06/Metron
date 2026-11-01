# S05 verification — 2026-11-02 (Asia/Kolkata)

All datasets used here are synthetic, and all processing used the local filesystem.
No API/cloud benchmark, production deployment, price or customer validation is claimed.

## Commands actually executed

From the repository root, with existing locked setup:

```bash
UV_OFFLINE=1 make check
UV_OFFLINE=1 make test
UV_OFFLINE=1 make build
UV_OFFLINE=1 UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend \
  python scripts/verify-s05.py --output docs/evidence/s05-cli-results.json
UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend \
  ruff check scripts/verify-s05.py
git diff --check
```

- `make check`: Ruff, strict mypy on 51 source files, ESLint and TypeScript passed.
- `make test`: 179 backend tests passed, including all 25 new S05 conversion tests;
  18 service-dependent integration tests deselected. Three frontend tests passed.
  One pre-existing Starlette/httpx TestClient deprecation warning.
- `make build`: Python sdist/wheel and Vite 7.3.7 production build passed.
- Actual CLI smoke passed, including candidate-list, full matrix, repeat reuse, rejected
  semantic loss and extracted-wheel CLI/worker. Package extraction/import happened in a
  temporary directory with its own PYTHONPATH; the editable environment was not replaced.
- Smoke script Ruff and `git diff --check` passed.

No service integration rerun was needed: S05 adds no API, database migration, authentication
or object-storage behavior. `make demo` remains deliberately unavailable until the complete
assessment pipeline exists. No S06 benchmark work was executed.

## Acceptance evidence

1. Primary event fixture: all exact integrity checks and six workload queries pass for the
   baseline and gzip NDJSON, Snappy Parquet and Zstandard Parquet, plus row-group and sort
   variants. Data bytes: baseline 287; gzip 138; Snappy 1,523; each Zstandard variant 1,593.
   Tiny input overhead makes Parquet larger; this is not a recommendation or savings claim.
2. Explicit exclusions: missing keys, mixed types, nested-to-Parquet, varying decimal scale,
   unsupported codecs, stale runtime context, unknown columns, original-byte/order constraints,
   partition count, partition minimum rows and file-count limits. Intentional negative-zero
   decimal loss fails canonical equality, retaining failed report evidence and publishing
   nothing. Output-byte quota failure and cancellation preserve source bytes and remove partials.
3. Reuse: second actual CLI run returns six `reused` outcomes; published manifest count stays
   6 → 6. Unit/integration-of-core tests also cover concurrent same-key requests publishing
   once; changed input/requirements create distinct keys; damaged files/manifests or unexpected
   files fail closed; orphaned same-key partials are rebuilt without removing unrelated work.

Additional tests round-trip CSV with text IDs and decimal overrides, already compressed
Parquet with declared metadata, partitioned multi-file Parquet with retained columns and
row-group bounds, concatenated multi-member gzip, duplicate multiplicity, missing-workload
honesty, invalid schema/configuration boundaries and actual running-worker cancellation.
The cancellation exercise stops a real worker; orphan recovery creates a deliberately
incomplete staged directory. A parent SIGKILL/power-loss test was not run. Inherited-lock
crash behavior is implemented but no crash durability or multi-host claim is made.

Exact local CLI observations, source fingerprint, engine versions, byte totals and actual
wall/RSS observations are in [s05-cli-results.json](s05-cli-results.json). The smoke script
removes its generated copies/artifacts in cleanup; checked-in evidence is metadata only.
See [candidate support](../candidate-support.md) for the production boundary, policy limits,
codec/version coverage, manifest conventions and reproduction commands.
