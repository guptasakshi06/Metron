# S07 verification — 2026-11-02, Asia/Kolkata

Completed immutable offline pricing and itemized economics (`s07.1`). This evidence covers
software arithmetic and local saved-fixture consumption, not provider/customer validation.

## Commands and results

Executed from the repository root with existing locked dependencies:

| Command | Result |
| --- | --- |
| `UV_OFFLINE=1 make check` | Passed Ruff, strict mypy on 65 source files, ESLint and TypeScript |
| `UV_OFFLINE=1 make test` | 261 backend + 3 frontend passed; 18 service and 9 Docker tests deselected |
| `UV_OFFLINE=1 make build` | Python wheel/sdist and Vite production build passed |
| `UV_OFFLINE=1 UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend pytest -q backend/tests/test_economics.py backend/tests/test_cost_cli.py` | 70 S07 tests passed |
| `UV_OFFLINE=1 UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend ruff check scripts/verify-s07.py` | Passed |
| `UV_OFFLINE=1 UV_CACHE_DIR=.tools/uv-cache .tools/uv-bin/uv run --locked --project backend python scripts/verify-s07.py --output-dir docs/evidence` | Three packaged CLI cases passed; source hashes unchanged |
| `git diff --check` | Passed |

Python 3.12.3, existing uv 0.13.6, Node 24.22.2, Vite 7.3.7. No new dependencies,
migrations, API routes or frontend behavior. A pre-existing Starlette/httpx TestClient
deprecation warning remains. No service/Docker suites were rerun because S07 changes no
service or sandbox execution path; the shared atomic report writer's annotation now
accepts a Pydantic BaseModel and is exercised by both benchmark and cost CLI tests.

## Required acceptance evidence

1. **Itemized reconciliation.** All eleven recurring and five migration components carry
   units, snapshot IDs, source references, formulas and discounts. Tests and the packaged
   CLI reconcile totals to rounded line items. Unknowns preserve null totals plus known
   subtotals. Decimal calculations remain independent of the caller's precision/traps.
2. **Capacity boundary.** A 1,000 GB to 350 GB used-space reduction under an unchanged
   1,000 GB provisioned allocation produces zero storage cash savings. An explicit feasible
   capacity-change assumption is required before using a reduced allocation. Shared fixed
   commitments cannot disappear, change key/rate, shrink or switch pricing basis.
3. **Boundary correctness.** Known, unknown, zero and negative savings; zero baselines;
   nonsteady usage; free/unknown migration; actual-versus-forecast separation; equal content,
   retention/copies; metadata; minimum object sizes/durations; GB/GiB; per-thousand requests;
   0/25/100% discounts; half-even rounding; growth/workload/price scenarios; and a 27-case
   volume/horizon invariant grid passed. Failed/stopped/missing benchmark repeats remain
   unknown rather than free. Corrupt reports, incompatible lineage, bad units, duplicate
   components, nonfinite rates and relabeled synthetic prices are rejected.

## Packaged CLI evidence

The script extracted the final wheel to private temporary storage, confirmed imports use
that wheel, and invoked `python -m data_optimizer.cli cost` from outside the repository.
Each case also retried its existing output: exit 2, exact existing bytes preserved.
Original request, price fixture and saved S06 source hashes were unchanged.

- [Synthetic report](s07-synthetic-cost.json): $300.000000 baseline monthly,
  $180.000000 candidate, $300.000000 migration, $120.000000 recurring savings,
  2.500000000000-month simple payback and $1,140.000000 twelve-month net.
  Physical saving 650,000,000,000 bytes (65%); assumed coexistence peak
  1,350,000,000,000 bytes. Entire scenario is invented arithmetic.
- [Saved benchmark adapter report](s07-benchmark-cost.json): actual saved S06 data bytes
  (287 baseline, 138 gzip candidate) with explicitly supplied 10,000 sample workload
  replays/month, synthetic prices/other usage and zero metadata assumption. The fixture
  assumptions produce **negative** $4.998322 monthly savings and no payback; this is an
  arithmetic result under those assumptions, not observed savings or a production verdict.
  Benchmark timings were reused from S06; no new query/Docker measurements were made.
- [Unknown-usage report](s07-unknown-usage-cost.json): exit 1 with saved null baseline and
  candidate totals, null savings/payback and explicit missing replay-derived query usage.
- [Machine verification summary](s07-verification-results.json): timestamps, exit codes,
  hashes, result values and exact evidence boundary.

No provider rate retrieval, invoice reconciliation, cloud extrapolation, production change,
customer validation, ranking or user interface is claimed. Tariff scope, rounding,
forecast assumptions and reproduction commands are in [pricing method](../pricing-method.md).
