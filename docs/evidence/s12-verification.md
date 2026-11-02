# S12 verification: reports and migration handoff

Verified 2026-11-02 (Asia/Kolkata), main at `4fdcce3`. Clean start; no agent commit,
staging, push, production change or paid/public deployment. Machine-readable results:
[s12-verification-results.json](s12-verification-results.json).

## Delivered story

A user completes an assessment, prepares owned expiring links in the dashboard, downloads
the original calculated evidence and human reports, then supplies the matching private source
to reproduce the recommendation or create a locally validated copy with rollback instructions.

| Boundary | Evidence |
| --- | --- |
| UI renders / refresh | Actual Chrome test, desktop 1440×1000 and narrow 390×844 screenshots; no page overflow or JS errors |
| UI → API | POST handoff and four actual downloaded attachments (JSON/Markdown/HTML/ZIP); session-bound controls clear on tenant switch |
| API → data | Actual PostgreSQL grant/confirmation queries and MinIO hash-checked immutable result; no report mutation |
| Data → response | Bundle and original report fingerprints, exact candidate totals, missing-value labels and retained confirmation version checked |
| Response → engineer | Extracted wheel outside repository exported, ran quoted migration script, reproduced assessment with four actual Docker trials and rejected wrong input |

## Exact commands and outcomes

- `UV_OFFLINE=1 make check` — passed generated-contract drift, Ruff, strict mypy (95 source
  files), ESLint and TypeScript. [Log](s12-check.log).
- `UV_OFFLINE=1 make test` — final **352 backend + 7 frontend** passed; 44 service and 10
  dedicated sandbox tests deselected by the default backend selector. [Log](s12-test.log).
- `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend pytest -q backend/tests/test_reports.py`
  — final 15 report cases passed, including schema-column names that resemble narrative
  metadata. [Log](s12-reports-unit.log).
- `UV_OFFLINE=1 make test-integration` — **44 actual service tests** passed in 62.18s.
  [Log](s12-integration-full.log). After the final typed-redaction adjustment,
  `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend pytest -q -m integration backend/tests/integration/test_report_downloads.py`
  passed both report service flows again in 14.94s. [Log](s12-integration.log).
- `UV_OFFLINE=1 make test-reports-browser` — final **1 Chrome full-service flow** passed in
  42.7s; runner exit 0 and isolated-resource cleanup recorded. It executes actual upload,
  confirmation, assessment, refresh, all four downloads, API comparison and tenant switch.
  [Log](s12-browser.log), [results](s12-browser-results.json), [cleanup](s12-run-status.json).
- `UV_OFFLINE=1 make build` — final wheel/sdist and Vite passed; 272.02 kB JS / 82.66 kB gzip.
  [Log](s12-build.log).
- `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend python scripts/verify-s12-package.py`
  — final extracted wheel outside the repository passed five cases: export (0), immutable
  destination rejection (2), quoted migration script (0), full assessment reproduction (0),
  mismatched source rejection (2). Four real fresh trials produced the same `change` outcome
  and selected configuration. [Results](s12-package-results.json), [log](s12-package.log).
- Ruff also passed `scripts/verify-s12-package.py`, `verify-s12-browser.py` and the configurable
  existing `verify-s11-browser.py`. `git diff --check` passed after final reconciliation.
- A one-off headless Chrome file load inspected the final exported HTML: title correct,
  23,317 characters of report text, zero script elements; screenshot visually inspected.
  Synthetic secret markers were absent from the final exports, browser distribution and S12 logs.
- `UV_OFFLINE=1 make infra-down` stopped only the local project, preserving named volumes.
  [Cleanup log](s12-cleanup.log). Final local-project and labeled-benchmark container lists empty.

## Acceptance evidence

1. **Reproduction:** [export](s12-export/bundle.json), [human report](s12-export/report.md),
   [HTML](s12-export/report.html), [fixed script](s12-export/migrate.sh),
   [fresh reproduced evidence](s12-reproduced-report.json). Three synthetic source events
   (287 bytes, SHA-256 `01974a491f9de8f7d8790b4f999fef94b6219cd7c6246f971f1e6d6598ab1167`)
   selected 138-byte gzip under explicitly invented amplified tariffs. Source preserved.
2. **Reconciliation / copy integrity:** report tests retain exact stored calculated amounts,
   line-item totals, space, workload and raw benchmark evidence; human totals match JSON.
   Baseline rows have no migration/savings/payback. The real script accepts spaces, quotes,
   `$()` and backticks as literal paths; it produces no injection marker. New copy passed
   semantic/multiplicity and supplied-workload integrity. [Migration manifest](s12-migration-result.json).
3. **Ownership / privacy:** real service tests reject foreign tenants, expired/rotated grants,
   unavailable/expired results and deleted datasets; own downloads preserve confirmation ID,
   version and original result bytes. Unnecessary description/source/price prose excluded.
   HTML/Markdown escaping rejects active instruction-like content. Tampered bundles/reports,
   different sources/workloads/engines/images and non-change migrations fail before work.

The browser service bundle includes confirmation provenance; the offline CLI export has no
access to database-only confirmation rows and leaves that provenance unset. Both retain the
original report digest. Nested evidence hashes reference originals before narrative redaction;
only the outer bundle digest validates all exported bytes. It is not a signature.

## Environment and limitations

Python 3.12.3, Node 24.22.2, Chrome 155, Arrow/PyArrow 26.0.0, DuckDB 1.5.6, Docker 29.1.3;
Intel i7-12650H, Linux 7.0.0-28-generic x86_64. Final package and immutable benchmark image
hashes are in the machine-readable results. Existing TestClient deprecation and Node color
warnings remain. Initial test-stub shebang and browser identity-control selector failures were
corrected; all final checks above passed. Review also corrected baseline-row economics and
a schema-field redaction collision before final verification.

No live AI/provider prices, invoices, customer/pilot validation, production migration/canary
switch/rollback exercise, external IdP, cloud/concurrency/tail/cold-cache or broad capacity claim.
Dedicated ten-test sandbox suite was not rerun; real Docker trials ran in service, browser and
package flows. Actual target-reader compatibility, peak capacity, switch and rollback remain
human steps. Strict image/hardware/kernel/Docker matching can require retaining the original
image/environment; changed environments need a separately labeled new assessment. Timing
variation can still change costs/decisions and is surfaced. Local downloaded files outlive
server link expiry and remain the recipient's responsibility. S13 observations not started.
