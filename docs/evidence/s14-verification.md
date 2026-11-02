# S14 local release verification — 2026-11-02

All required local gates passed. [Machine ledger](s14-verification-results.json) records
command exits, source/lock hashes, branch/HEAD and the final immutable benchmark image.
The initial/final branch is `main`, HEAD `103910b`; no staging/commit/push was performed.

## Commands and evidence

Run from the repository root with the existing pinned `.tools` environment:

| Command | Actual result | Evidence |
| --- | --- | --- |
| `make infra-up` | Local PostgreSQL/Redis/MinIO healthy | Session startup; later real service tests |
| `make benchmark-image` | Rebuilt locked image with explicit system Arrow allocator | [Build log](s14-image.log) |
| `make check` | Drift/Ruff/strict mypy (99 files)/ESLint/TypeScript pass | [Log](s14-check.log) |
| `make test` | 380 backend + 7 frontend pass; 59 service/Docker deselected | [Log](s14-test.log) |
| `make test-integration` | 49 real service tests pass, 100.64 s | [Log](s14-integration.log) |
| Targeted `pytest -q -m integration backend/tests/integration/test_assessments.py::test_transient_storage_failure_retries_without_duplicate_assessment` | One pass after adding credential/raw-marker log assertions | [Log](s14-log-redaction.log) |
| `make test-benchmark` | All 10 real Docker cases pass, 35.07 s | [Log](s14-sandbox.log) |
| `make test-release-browser` | All 12 Chrome/service/RQ/Docker stories pass, 1.7 min; cleanup/exit 0 | [Log](s14-browser.log), [JSON](s14-browser-results.json), [cleanup](s14-run-status.json) |
| `make evaluate` | Seven whole-dataset cases, exhaustive/adaptive assessments pass | [Log](s14-evaluation.log), [case ledger](s14-evaluation/results.json) |
| `make calibrate` | 20 passing maximum-query/repeat-envelope trials plus four strict-latency trials; invalid caps rejected | [Log](s14-calibration.log), [workload ledger](s14-capacity/workload-results.json) |
| `make build` | Python wheel/sdist and Vite production build pass | [Log](s14-build.log) |
| `make verify-clean` | Fresh temporary Python/npm dependency directories: locked setup/check/test/build and **make demo** all exit 0 | [Log](s14-clean.log), [command ledger](s14-clean/clean-results.json) |
| `uv run --locked --project backend python scripts/profile-resource-check.py --output docs/evidence/s14-profile-resources.json` | Real 60,000-row profile and above-memory quota response | [Log](s14-profile-resources.log), [measurements](s14-profile-resources.json) |
| `pytest -q backend/tests/test_release_parquet.py --tb=short` | Actual dictionary/Zstd validation/profile/four conversions pass | Included in full/clean test runs; initial focused run 1 pass |
| `pytest -q backend/tests/test_reports.py --tb=short` | 17 portable report/context tests pass | [Log](s14-report-regressions.log) |
| `make infra-down` | Only project containers/network removed; named volumes retained | [Log](s14-cleanup.log), [final audit](s14-final-audit.json) |

The targeted pytest commands use `.tools/uv-bin/uv run --locked --project backend`.
Service/browser suites ran sequentially against shared demo-tenant advisory locks. CLI
evaluation, calibration and clean builds sometimes shared host resources; timings are
observations on this loaded host, never dedicated-throughput measurements.

## Complete flow and recovery

The final browser suite covers optional no-key intake/edit/confirmation, actual measured
change and already-compressed keep-current, CSV/Parquet uploads, startup/unknown cost
guidance, reviewed local profiler import, malformed/workload error recovery, refresh,
active cancellation, exact displayed API costs/line items, all report downloads and
observations/reverts/reassessment. The service suite additionally exercises actual worker
SIGKILL recovery and unchanged published trial reuse, queue loss/retry/admission, input
immutability, cross-tenant denial, expiring/rotating authenticated grants, raw expiration,
delete/cleanup failure recovery and all eight migrations on empty isolated schemas.

The new [backup drill](s14-backup-restore.json) restores a custom PostgreSQL archive into a
new database, compares exact result/bundle/manual history, checks owner denial and immutable
triggers, and proves missing object → sanitized 503 → successful restoration. It retains
the original test bucket and does not claim an independent object-store disaster restore.
The new [upload drill](s14-upload-capacity.json) measures real validation/storage/hash reads
at 1/16 MiB and rejects cap+1 at the configured 16 MiB cap.

The clean dependency rehearsal uses cached tool binaries/downloads, fresh venv/node_modules,
and committed unit-test measurement fixtures. Its packaged demo creates fresh measured
change/keep/guidance/resume evidence, then exports and independently reproduces the report.
It does not use historical demo reports or application services. Copies of its actual
artifacts are in [s14-demo](s14-demo/s08-verification-results.json), including the
[readable handoff](s14-demo/handoff/report.html) and [fresh reproduction](s14-demo/reproduced.json).
The temporary source/dependency directories were removed after the run.

Final dataset regeneration matches every recorded input SHA-256 and confirms the
categorical fixture contains 768 records/384 unique events. The operational secret-marker
scan passes. Final browser ports 8010/5174 are closed, no labeled benchmark containers or
local project containers remain, and project volumes are retained.

## Fixes, intermediate failures and visual inspection

- Initial held-out dictionary/Zstd Parquet candidate worker crashed under RLIMIT_AS.
  Explicit Arrow system allocator passed the focused reproduction and final full holdout;
  existing limits stay enforced. [Decision 0014](../decisions/0014-s14-local-release.md)
  records the observed cause boundary and changed execution-context lineage.
- Four legacy report tests first stopped at the newly incompatible historical context.
  They now stub that context only when isolating later gates; two separate tests prove
  real pre-S14 context rejection. Historical measurements were preserved unchanged.
- The first full browser run passed 10 and failed two S10 expectations for text changed
  by S13. Updated the expected current evidence wording; the final 12/12 run passes.
  New evidence prefixes preserve prior sprint screenshots and JSON. Any initial historical
  screenshots generated by the runner were restored to their original committed bytes.
- The categorical fixture initially lacked identical pairs because category varied per
  row. Corrected the generator and reran the complete matrix, confirming 384 doubled
  events and matching final fingerprints. No optimizer/tariff tuning occurred.
- The first clean-install attempt exposed a tool path containing spaces; the clean-copy
  harness now uses a relative tool symlink. An offline retry lacked cached locked packages;
  the successful locked install downloaded the missing packages. No global package change.
- Desktop handoff and narrow dashboard/history screenshots were visually inspected:
  readable controls/provenance, expected internal table scrolling, no page-wide overflow.
  Browser keyboard/JS-error assertions pass. Screenshots include
  [handoff](s14-handoff-desktop.png), [dashboard](s14-dashboard-narrow.png) and
  [history](s14-history-narrow.png).

## Acceptance and limits

1. Fresh dependency directories run the documented packaged demo, generate a complete
   measured report and independently reproduce the decision: **passed**.
2. Required local correctness/isolation/integration/recovery gates with actual evidence:
   **passed**. Exact scope and calibrated envelopes are in [release readiness](../release-readiness.md).
3. S14 tasks/ledger/decisions/continuation pointers reconcile to `COMPLETE_MVP`: **passed**
   after final handoff update. No automatic post-MVP work.

Hosted CI, live optional AI, external IdP, real provider rates/bills/customer/pilot outcomes,
production object-store lifecycle/disaster recovery, production reader canary/rollback,
power-loss/multi-host/exactly-once pre-publication recovery, native/cloud/concurrent/tail/cold
performance and configured maximum upload capacity remain unverified. Existing
Starlette/httpx deprecation, Node color warnings and favicon 404 persist. No public/paid
deployment, external message, source-system mutation or fabricated customer saving.
