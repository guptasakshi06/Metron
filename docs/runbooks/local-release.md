# Clean local start and release verification

Use Linux with Python 3.12, Docker Engine/cgroup v2, Compose, curl, tar, xz, sha256sum and
Make. Allow image/package downloads and free disk for dependencies and temporary copies.
The bootstrap supplies pinned Node/uv without changing system tools. No cloud account,
LLM credential or paid service is required. Infrastructure binds to loopback only.

```sh
make setup
export PATH="$PWD/.tools/node24/bin:$PWD/.tools/uv-bin:$PATH"
make infra-up
make migrate
make seed-local
make storage-init
make benchmark-image
make demo
```

`make demo` builds a wheel, imports it outside the repository, measures baseline and
alternatives, demonstrates keep-current/metadata/startup paths and checkpoint reuse,
exports JSON/Markdown/HTML, and independently reproduces the change from that export.
It prints a new `/tmp/data-optimizer-demo.*` evidence directory. Open its
`handoff/report.html`; retain it if wanted before cleaning temporary files.
Prices are deliberately amplified synthetic fixtures, with no customer savings claim.

To use the browser, start `make dev`, `make dispatch-jobs`, and `make worker` in three
terminals with the same root/settings/workspace. Visit
[the local dashboard](http://127.0.0.1:5173). Follow the [user guide](../user-flow.md):
create a project, review retention, upload an assessment copy or review/import metadata,
provide the constrained workload and explicit prices/usage, submit, inspect measured
evidence, and prepare expiring exports. Metadata-only input produces guidance. No key is
needed; unknown prices stay unknown. Actual deployment/canary/reader rollback is deliberate
human work described in the exported report, never an automatic action.

Stop interactive processes before the release suite. Install Chrome, or set the existing
Playwright channel configuration to an installed compatible browser. The local verification
used Chrome; other browsers are unverified.

```sh
make release-check
make verify-clean
make infra-down
```

`release-check` runs checks/tests/build, all real service tests (including backup and upload
drills), Docker isolation tests, all browser stories, held-out evaluation, calibration and
packaged demo. Run it without `-j`: service/browser workers share demo-tenant advisory locks.
Service fixtures clean isolated schemas/buckets; browser runs also remove their owned queue
records/workspaces. Completed RQ test deliveries have the configured Redis result retention. Never run multiple
browser/service suites concurrently against these defaults. `verify-clean` creates fresh
Python/npm dependency directories in a temporary current-source copy, uses only shared
download caches/tool binaries, and repeats locked setup/check/test/build/demo, downloading missing cached packages as needed.
Unit tests read committed historical measurement fixtures. The fresh demo generates its
own measurements/reports and requires no application database.

GitHub CI runs locked setup/check/test/build, real Docker tests, held-out evaluation and the
packaged demo on an ephemeral Ubuntu 24.04 runner. The workflow file is supplied; a hosted
CI execution is not implied by passing the local clean-copy check. Local browser/service
release checks remain required. No deployment/publishing step is included.

## Release checklist

- All `release-check` commands pass; read raw logs, not only task status.
- Clean dependency install and packaged demo/reproduction pass.
- Each selection has passed semantic/workload checks, reconciled costs and raw observations.
- Inspect adaptive/exhaustive regret and exclusions; do not claim global optimality.
- Tenant/auth/grant/expiry, resource/isolation, cancellation and restart gates pass.
- Restore metadata into a fresh database and recheck owned result/history/downloads.
- Record measured hardware, upload/workload envelopes and all unverified limits.
- Keep pilot/live-provider/production prerequisites explicit in [release readiness](../release-readiness.md).
- Reconcile the [handoff](../../SPRINT_HANDOFF.md); stop at `COMPLETE_MVP`.
