# S10 dashboard verification

Date: 2026-11-02, Asia/Kolkata. Branch `main`, starting/final HEAD `0b2d086`.
No staging, commit, push, public deployment, paid provisioning or customer-data mutation.

**Story:** browser project intake → bounded/reviewed evidence → executable workload and
explicit cost inputs → owned asynchronous API → PostgreSQL/RQ/Docker worker → MinIO result →
comparison, coverage, line items and reproducibility details in the browser.

| Boundary / gate | Result | Evidence |
| --- | --- | --- |
| Project, input and requirement UI → API | passed | Eight real-service Chrome tests, including all three raw formats and gzip |
| API → durable jobs → real worker/storage | passed | Actual local profile/conversion/integrity/benchmark/cost/decision executions; final service/worker logs |
| API result → displayed comparison/economics | passed | Every candidate's bytes/horizon total and expanded candidate's recurring/migration/net totals and all line items compared exactly to API decimal strings |
| Keep current and insufficient evidence | passed | Compressed NDJSON keeps baseline; no dataset and reviewed metadata return needs_input with questions, no claimed benchmarks |
| Refresh and cancellation | passed | Refresh after creation recovers assessment ID/result; cancellation during actual benchmarking becomes cancelled and survives refresh |
| Ownership/session | passed | Alice → Bob unmounts previous result, Bob gets 404 for Alice result, switching back recovers Alice evidence |
| Validation/failure recovery | passed | Malformed upload 422 remains unusable, subsequent valid upload works; invalid query shows field path and preserves JSON; malformed JSON disables submission; component tests verify service-error input preservation |
| Layout and keyboard | passed within tested scope | Desktop 1440×1000 and narrow 390×844 screenshots manually inspected; no page-wide horizontal overflow, tables scroll inside labeled regions; first keyboard Tab focuses visible skip link; no JS page errors |

## Commands and results

- `make infra-up`: actual local PostgreSQL/Redis/MinIO started; the existing S06 image was available.
- `UV_OFFLINE=1 make check`: passed generator drift check, Ruff, strict mypy on 79 source files,
  ESLint and TypeScript. Log: [s10-check.log](s10-check.log).
- `UV_OFFLINE=1 make test`: **305 backend + 4 frontend passed**; 42 service/Docker tests deselected
  by the normal command. Log: [s10-test.log](s10-test.log). Two new backend preflight/discovery tests.
- Final `PATH="$PWD/.tools/node24/bin:$PATH" npm --prefix frontend test -- --run`: **4 passed**
  after final session-storage namespace changes. Log: [s10-frontend-test.log](s10-frontend-test.log).
- `UV_OFFLINE=1 make build`: passed Python wheel/sdist and Vite production build; frontend
  JS 263.31 kB / 80.06 kB gzip. Log: [s10-build.log](s10-build.log).
- `UV_OFFLINE=1 make test-browser`: final **8 passed in 44.8 seconds**, command exit **0**;
  explicit post-cleanup status [s10-run-status.json](s10-run-status.json). Final unchanged UI suite
  also passed all eight immediately before this final instrumented cleanup/report-harvesting run.
  [Browser log](s10-browser.log), [machine-readable results](s10-browser-results.json).
- `.tools/uv-bin/uv run --locked --project backend ruff check scripts/generate-frontend-contracts.py scripts/verify-s10-browser.py`:
  passed. Generator `--check` repeated successfully after final edits.
- `git diff --check`: passed. `make infra-down` stopped only `data-optimizer-local`, preserving
  named volumes. No benchmark containers or local project containers remained. Browser runner
  removed its ephemeral schema/bucket/queue/workspace and stopped API/frontend/dispatch/worker.

Runtime: Python 3.12.3, Node 24.22.2, npm 11.19.1 (with bundled Node in PATH), uv 0.13.6,
Playwright 1.64.1, Google Chrome 155.0.8059.79. Existing locked DuckDB/PyArrow and Docker image
from S09 were reused; no benchmark engine or backend dependency change.

## Artifacts and observed evidence

- [Desktop screenshot](s10-desktop.png), [narrow screenshot](s10-narrow.png): real completed raw
  fixture assessment, comparison and expanded itemized cost evidence. Long IDs wrap; wide tables
  remain scrollable. Top/intake and result crops were also inspected locally during QA.
- [Measured change API report](s10-measured-change-report.json): actual local 287-byte synthetic
  event sample compared with gzip/Snappy/Zstandard alternatives; gzip 138 bytes selected using
  the deliberately amplified invented tariff. Baseline 12-month total 344.400000 USD, selected
  gzip 165.600000 USD under that fixture; these are modeled synthetic costs, not customer savings.
- [Keep-current report](s10-keep-current-report.json): already compressed input retains baseline.
- [Metadata report](s10-metadata-report.json), [startup report](s10-startup-report.json): scenario
  guidance with no benchmark and explicit local-supplied provenance where metadata exists.
- [Source hashes/results](s10-verification-results.json). API/worker/dispatcher logs are saved
  as `s10-dev.log`, `s10-worker.log`, `s10-dispatch.log`; they contain IDs/stages and HTTP status,
  not records, credentials or request bodies. API reports were harvested before test cleanup.

## Corrections and limits

Intermediate browser runs exposed exact-label ambiguity in selects/the JSON editor and long
fingerprint overflow at 390 pixels. Explicit labels and wrapping fixed both. A test keyboard
reset was corrected to reload before checking first-Tab focus. One tool session initially
reported a termination code after a passing suite; the final runner now writes an explicit
post-cleanup exit record, and its complete command returned 0. No intermediate failure is
counted as final acceptance evidence.

The request editor is deliberately technical JSON for full schemas, workload operations and
cost scenarios, with progressive common fields and templates. It preserves supported engine
bounds; it is not an automatic schema or business-requirement inference UI. Metadata reports
are previewed/reviewed before transfer. Default costs remain unknown, synthetic prices require
a deliberate action. Currency amounts are exact API strings; missing amounts show Unknown.

JWT token entry/sign-out gating is component-tested; a live external IdP, token refresh/redirect
login and publicly accessible deployment are **not verified**. No live provider pricing, invoices,
customer/pilot savings, production latency/concurrency, true cold cache, tail latency or broad
accessibility audit is claimed. Keyboard skip link, labeled controls, visible focus, native form
controls and the two recorded viewport layouts were checked; screen readers, other browsers and
mobile devices were not exercised. The separate 32-service and 10-Docker regression suites were
not rerun because those existing backend paths were unchanged; this sprint's browser suite does
execute real services/RQ/Docker. Existing TestClient deprecation and Node color-environment warning
remain. Reports/migration bundles remain S12 and observation tracking S13. No S11 implementation.
