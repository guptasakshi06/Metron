# Reports and deliberate migration handoff (S12)

The dashboard's **Engineering handoff** appears after an owned result loads, including
keep-current and insufficient-evidence cases. Prepare expiring links, then download ZIP,
JSON, Markdown or HTML. The ZIP contains `bundle.json`, `report.md`, `report.html` and
`migrate.sh`. Save/extract together in a private directory. Review before sharing: field
names, workload literals, schema settings, price quantities and hashes may be sensitive.
The report contains no raw dataset, business description, AI summary, runtime credentials,
object-store path or provider prompt. Free-text source notes/references and price narrative
are omitted; consult the original owned assessment for those details.

## Schema and evidence

`AssessmentBundle` version `s12.1` contains the executable request, requirements,
confirmation/proposal/version/fingerprint provenance when available, profile coverage,
candidate configurations, complete benchmark manifests/raw trials/query hashes/environment,
all itemized cost reports with price snapshots and the authoritative decision. All displayed
amounts come from these stored calculated fields. Unknown remains Unknown; baseline rows
have no migration, savings or payback. Scenario-only guidance has no measured migration.

`original_report_fingerprint`, `original_request_fingerprint` and nested evidence hashes
refer to the original records. Narrative redaction deliberately changes some nested
serialized content; do not use those original hashes to validate redacted nested records.
`bundle_fingerprint` independently hashes the full exported content, excluding itself.
It detects accidental changes, **not authenticity**; an attacker could rewrite content and
recompute it. Obtain the original export through the authenticated endpoint and retain
its digest from that session. The bundle contains evidence, not arbitrary executable code.
Reproduction also revalidates the input, typed workload and current conversion integrity.

## Setup and offline commands

Use this project's locked Python 3.12 environment (`make setup`) and matching engine
versions. Full assessment reproduction needs Linux Docker/cgroup v2 and the same immutable
benchmark image. Build with `make benchmark-image` from the matching checkout; a rebuilt
image with a different ID is rejected rather than silently treated as equivalent evidence.
Hardware/kernel/Docker version must match the recorded benchmark environment. If they differ,
run a separate new assessment under that environment and label it as new evidence.
Local-copy migration requires matching conversion engines, without a Docker timing rerun.

```sh
uv run --locked --project backend data-optimizer export \
  --report /tmp/saved-result.json --output-dir /tmp/new-handoff
uv run --locked --project backend data-optimizer reproduce \
  /tmp/new-handoff/bundle.json --source '/private/path with spaces/events.ndjson' \
  --root /tmp/new-reproduction --output /tmp/new-reproduction.json
```

`export` accepts only a valid saved `AssessmentReport` fingerprint and creates a new private
directory. `reproduce` verifies the bundle digest, source SHA-256, conversion versions,
workload lineage and benchmark environment before assessment work. It needs a new workspace
and output file outside it; existing paths are not overwritten. It reruns real profiling,
conversion, semantic integrity, sandbox trials, costs and ranking, then compares outcome and
selected configuration. Timings, resource use and timing-derived costs can vary even on the
same machine. A different decision is recorded with a saved fresh report and exit 1; inspect
it. There is no guarantee of identical performance values or universal savings.

Exit codes: 0 successful export/reproduction, 1 saved decision disagreement, 2 invalid input,
fingerprint/context mismatch, unsupported guidance migration or invalid destination. Errors
include safe reason codes (for example `source_fingerprint_mismatch`), without echoing input.
A wrong source is rejected before creating a workspace. Partial work can remain after later
runtime failure for owner inspection; there is no automatic removal of source/workspace data.

## Deliberate migration, validation and rollback

Only a selected feasible `change` with a verified matching manifest can create a candidate
through the script. `keep_current` and `insufficient_evidence` reject migration. Script content
is fixed; source/workspace/result paths are quoted positional arguments. Dataset contents,
LLM output and arbitrary user text never become shell programs.

```sh
# Run inside the locked environment, where data-optimizer is on PATH:
sh /tmp/new-handoff/migrate.sh '/private/source.ndjson' \
  /tmp/new-migration-copy /tmp/new-migration-result.json
```

The command verifies the source digest and engine versions and runs the existing bounded
conversion plus exact semantic/multiplicity and constrained-workload result checks. The JSON
result includes the new manifest, ordered parts, output bytes, reader/schema, configuration,
canary query hashes and per-check integrity. A baseline copy is retained in full-assessment
reproduction; migration-only conversion retains the user's source and creates the selected
copy. It never transfers to cloud storage, switches readers or deletes originals.

Before a real reader change, a human must:

1. Preserve the original, its SHA-256, required retained copies and prior reader configuration.
   Check forecast one-time/recurring costs and peak space; estimate missing scratch/copy costs.
2. Verify target-reader codec, schema, decimal, timestamp and null/missing support. Honor the
   exact ordered manifest parts and partition/sort configuration.
3. Require passed content/multiplicity and workload-result checks. Replay the supplied workload
   in the actual target reader, then validate representative canary latency/concurrency there.
4. Deliberately direct limited canary reads to the new copy while retaining the prior reader.
5. Roll back on missing parts, integrity/schema/result mismatch, latency/cost/retention violation
   or unsupported reader behavior: stop directing new canary reads to the copy, restore the
   saved reader configuration pointing at the original, verify its SHA-256, rerun the workload
   and confirm normal reads. Retain both copies for investigation and existing retention policy.

Each report embeds these instructions with its costs and limitations. It cannot prove target
reader compatibility, production concurrency, cloud latency, true cold cache, tail latency or
customer savings. Costs support flat linear tariffs and recorded minimums; unsupported tariff
components and missing assumptions are explicit. No public deployment is part of this sprint.

## Authenticated download API

`POST /v1/assessments/{id}/handoff` returns `download_id`, `expires_at`, `bundle_fingerprint`
and relative authenticated links keyed by `zip`, `json`, `markdown`, `html`.
`GET /v1/assessments/{id}/handoff/{download_id}/{format}` returns an attachment.
Use the same verified Authorization/local demo identity as the assessment. No credentials
are embedded in links. Default `REPORT_DOWNLOAD_TTL_SECONDS=600` (30–3600 configurable)
is capped by assessment expiry; dataset/project/profile deletion and raw retention are
rechecked on each download, and expiry is rechecked after rendering. Responses use
`Cache-Control: no-store`, attachment disposition, nosniff and a restrictive HTML CSP.

Migration `0007_report_downloads.sql` stores tenant/assessment/bundle-bound grant IDs and
expiry. Preparing new links rotates the ID and invalidates prior links for the same bundle.
A grant is not a bearer credential. Expired/foreign/deleted resources return 404; no result
yet returns 409; stored integrity failure returns 503. Files already downloaded remain the
recipient's local copies; server expiry cannot revoke those files.

## Verification

`make check`, `make test`, `make build`; targeted service tests:

```sh
uv run --locked --project backend pytest -q -m integration backend/tests/integration/test_report_downloads.py
make test-reports-browser
uv run --locked --project backend python scripts/verify-s12-package.py
```

Services and the benchmark image are needed for the latter flows. The package script uses
an extracted wheel outside the repository, actual supplied fixture and actual Docker trials.
See [verification evidence](../evidence/s12-verification.md). No live provider or production
migration is required or claimed. Deployment observations remain S13.
