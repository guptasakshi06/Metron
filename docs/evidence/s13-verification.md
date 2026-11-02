# S13 verification — savings observations and deliberate reassessment

Verified locally on 2026-11-02 (Asia/Kolkata), starting from clean `main` at `67a9b05`.
No agent commit/push, public deployment, paid provisioning, external messages, real reader
switch, real bill verification or production observation took place.

Story: an owner opens measured assessment evidence → records adoption versions → enters or
reviews manual observation JSON → saves immutable PostgreSQL revisions → receives original-price
comparable-usage calculations → sees separate actual/projection/modeled totals → deliberately
runs and compares a new assessment without changing prior evidence.

| Boundary | Result | Evidence |
| --- | --- | --- |
| Browser renders/refreshes history | passed | `s13-history-desktop.png`, `s13-history-narrow.png`; Chrome flow checks no page-wide overflow |
| Client → authenticated API | passed | `s13-dev.log`, browser revisions/state updates; typed request fields and bounded file review |
| API → PostgreSQL | passed | 47 service tests; actual migration, optimistic conflicts, append-only triggers, overlap rejection, author/audit retention |
| Stored evidence → calculations | passed | 25 arithmetic/validation cases, original itemized tariffs, real measured assessment result from MinIO; synthetic manual observations |
| Response → UI | passed | Browser exact string comparisons for actual, projection, adjusted baseline, savings and cumulative benefit |
| Reassessment | passed | Two actual Docker-backed assessment runs in browser; different IDs, comparison, original report byte equality; `s13-browser-comparison.json` |
| Ownership/retention | passed locally | Cross-tenant reads/writes, deleted input and expired parent reject history; logical metadata preserved |
| Packaged application | passed | `s13-package-results.json`: eight checksummed migrations, contracts and owned history/comparison routes from extracted wheel outside repository |

Commands and final outcomes:

- `make infra-up`: started project-local PostgreSQL/Redis/MinIO, preserving unrelated containers.
- `.tools/uv-bin/uv run --locked --project backend pytest -q backend/tests/test_observations.py --tb=short`:
  **25 passed**, including lower usage, growth/zero, partial period, missing bills, currency/mix/schema
  mismatch, negative savings, reverted periods, fixed commitments, minima, context precision and extreme quantities.
- `.tools/uv-bin/uv run --locked --project backend pytest -q -m integration backend/tests/integration/test_observations_api.py --tb=short`:
  initial final targeted run **3 passed** (14.88s), before adding the second-period cumulative assertion.
  All three, including that assertion, subsequently passed in the full final suite.
- `make check`: **passed** generated contract drift, Ruff, strict mypy on 99 source files, ESLint and TypeScript. `s13-check.log`.
- `make test`: **377 backend + 7 frontend passed**, 47 service + 10 sandbox tests explicitly deselected.
  Backend 28.79s; `s13-test.log`. 25 new arithmetic/validation cases.
- `make test-integration`: final sequential run **47 passed**, 79.22s. `s13-integration-full.log`.
  Uses actual isolated PostgreSQL/MinIO/Redis, RQ workers and Docker where required by the test.
- `make test-observations-browser`: **1 complete scenario passed**, 20.5s, runner exit 0 and cleanup.
  Real Chrome/API/PostgreSQL/MinIO/Redis/RQ/Docker; invented adoption/bill input. `s13-browser.log`,
  `s13-browser-results.json`, `s13-run-status.json`, input revision history and comparison JSON.
- `make build`: **passed** wheel/sdist/Vite, final JS 282.14 kB / 85.30 kB gzip. `s13-build.log`.
- `.tools/uv-bin/uv run --locked --project backend python scripts/verify-s13-package.py`:
  **passed** extracted-wheel import/contracts/routes and migration checksum. `s13-package.log`.
- Script Ruff checks and `git diff --check`: **passed**.
- `make migrate`: applied local pending migrations **0004 through 0008** to the existing development
  database. Every service/browser fixture also applied all eight migrations to fresh schemas and
  verified repeated migration application returns none. `s13-migrate.log`.
- `make infra-down`: **passed**, retained volumes; labeled benchmark container listing empty.
  Browser/service fixtures removed their isolated schemas, buckets, queues and workspaces.
  `s13-cleanup.log`.

Arithmetic assertions use invented values, not noisy timing-derived expectations:

| Case | Modeled baseline / actual / modeled savings (USD) |
| --- | --- |
| Unchanged representation, half volume and half replay count | 75 / 75 / 0 |
| Doubled volume and replay count | 600 / 100 / 500 |
| Zero volume and usage, actual charge remains | 0 / 100 / -100 |
| Half-month, half replay count | 100 / 100 / 0; original projection 75 |
| Large unfavorable actual costs | 200 / 1100 / -900 |
| Missing bill, changed mix/schema, mismatched currency, unsupported billing minima | Savings unknown |

The service suite also sums two disjoint periods and subtracts actual migration spend only once;
missing/incompatible periods make cumulative benefit unknown. Revisions, exclusions and a revert
preserve the original report and all inputs. Browser scenario checks growth, lowered usage with an
equal adjusted bill (zero modeled savings), negative savings, missing bill, EUR/USD mismatch, revert,
refresh, deliberate reassessment and a tenant switch. Values in saved history are all synthetic
user entries; the underlying profiling/conversion/integrity/Docker assessment is actual local work.

Intermediate issues resolved before final checks: nonterminating decimal fractions required an
explicit rounding tolerance; ownership is checked before validating foreign plan bodies; a duplicate
React sibling key was corrected; text-area selectors gained explicit accessible labels; the existing
scrollable-table wrapper prevents narrow-screen page overflow. Existing `/favicon.ico` 404 is
explicitly excluded from the console assertion; other console errors and page errors fail the test.
A concurrent full-service attempt left one direct-execution assistance test queued (46 passed,
1 failed). Shared demo tenant admission locks span schemas; the sequential full rerun passed all
47. Do not run full-service and browser workers concurrently on the same demo tenant/database.
Existing Starlette/httpx deprecation and Node color warnings remain.

No new runtime dependencies or stack changes. Python 3.12.3, Node 24.22.2, uv 0.13.6,
DuckDB 1.5.6, PyArrow 26.0.0 and the existing immutable benchmark image. No separate sandbox suite
rerun because sandbox implementation did not change; real sandbox trials ran in service/browser
assessments. No new maximum-capacity, cloud latency, cold-cache, tail/concurrency, external identity,
live provider, customer/pilot or invoice accuracy claim.

Known attribution and retention boundaries: linear volume/query scaling, fixed object topology,
30-day modeled months and original tariffs; gaps are not estimated, currency is not converted,
minimum-billing topology is unsupported. Observations are user supplied, never provider verified
or causal savings proof. History access inherits assessment/raw-copy expiry/deletion (default
seven-day retention); choose a suitable explicit retention period before upload. This sprint does
not silently retain raw copies longer or provide long-term access after expiry. Details in
[runbook](../runbooks/observations.md) and [decision 0013](../decisions/0013-s13-observations.md).

All eight S13 tasks and three required local acceptance gates have evidence above. S14 remains
unstarted and owns integrated evaluation, capacity/operational calibration and local release readiness.
