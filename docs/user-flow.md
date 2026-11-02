# Assessment dashboard (S10)

The dashboard at `/` runs the same immutable assessment pipeline as the CLI. Its four
anchored sections are Project, Evidence, Workload, and Results. No fixture result is
rendered as an executed assessment. A new project/input starts with unknown prices.

## Run locally

Use the locked setup in the README, then:

```bash
make infra-up
make migrate
make seed-local
make storage-init
make benchmark-image
make dev
```

Run `make dispatch-jobs` and `make worker` in separate terminals at the same root and
configuration. Open [the local dashboard](http://127.0.0.1:5173). `make dev` starts only
the API/frontend. Queued work explains the worker requirement in the interface.

1. Select a project or create one with an optional business description. Context is saved
   on the owned project; this sprint does not infer requirements with a language model.
2. Choose Upload data, Metadata only, or No dataset yet. Uploads require reviewing the
   retention days and transfer consent before sending a copy. CSV, NDJSON, Parquet and
   gzip text inputs use the authenticated bounded streaming/finalization API. Progress
   describes network transfer; structural validation is a separate stage. Ready copies
   show expiry and can be deleted. External source files are never touched.
3. In metadata mode, generate a local profile using the CLI, choose its JSON report,
   inspect the displayed contents and explicitly approve import. Metadata can be sensitive.
   The server checks its fingerprint and provenance. No raw records are uploaded by this
   path. Existing imported profiles can be selected. Metadata and no-input assessments
   return useful next questions, without claiming sample performance or historical savings.
4. Choose a full scan, projection, grouped count, or unknown workload template. Templates
   require adapting column names to the dataset. Edit the JSON for predicates, time ranges,
   aggregates, latency targets, frequencies, concurrency, schema overrides, CSV null tokens,
   allowed formats/codecs, budgets and complete cost scenarios. CSV stays text by default;
   use explicit overrides when a numeric/time query needs typed columns. Blank progressive
   fields serialize to null. Freshness/production concurrency stay untested in this engine.
5. Prices are unknown by default. The deliberate **Use synthetic cost example** action
   loads the versioned S08 demonstration assumptions, including amplified invented storage
   prices and explicitly zero other usage. These are editable, clearly synthetic forecasts,
   never a live quote or customer saving. Replace the complete cost scenario with supported
   user-supplied prices/quantities when available. Validation errors show contract field paths
   and retain the edited request. Dataset-dependent compatibility runs in the worker.
6. Run the assessment. The dashboard validates the executable contract, submits with an
   idempotency key, then polls actual worker stages/counts. Refresh recovers the selected
   assessment. Transport-error retries preserve the same key for identical inputs. Cancel
   requests stop outstanding worker work and show cancellation/stopped/partial evidence.
7. Inspect change, keep_current or insufficient_evidence. The table includes the baseline,
   feasibility, physical data bytes, median observed local load-plus-query time, range and
   exact API horizon totals. Expand a representation for requirement coverage/evidence IDs,
   baseline/candidate/migration line items, missing quantities, net savings, payback and
   migration peak space. Baseline has no migration; no candidate's migration is attributed
   to it. All currency values retain the API's decimal strings.
8. Expand raw evidence to inspect environment, workload/input fingerprints, cache labels,
   price snapshots, search stops, raw trials and complete calculation provenance. Costs are
   projections, local sample measurements are distinct, and production observations are
   explicitly unavailable. Packaged exports and migration instructions remain S12.

## Sessions, privacy and recovery

Local mode exposes only the fixed Alice/Bob development identities. Switching identity
unmounts the workspace, aborts in-flight requests, and clears displayed evidence before
loading the other tenant. Every request still relies on backend authorization. In JWT mode,
the local selector is absent: a verified token is entered and retained only in memory;
sign-out removes it. An external IdP/login redirect is not implemented or verified here.

Local sessionStorage holds versioned-prefix project/assessment IDs, the request editor draft,
and pending submission key/payload, separately per demo identity. This supports refresh and
ambiguous transport failures. User-authored query literals/context within request assumptions
may be sensitive. Raw files and loaded profile reports are not stored there. Close the tab to
clear its session; disable browser session restore when stronger local privacy is required.
JWT sessions keep drafts and tokens in memory only. Backend ownership/expiry checks remain
authoritative. Status is polled every 1.5 seconds while active, every 10 seconds after a
successful result, and after transient errors. Expired/deleted/inaccessible status clears
previously displayed evidence and reports an actionable access/service error.

Controls have readable labels and visible keyboard focus; a skip link and section navigation
support keyboard use. Tables scroll within labeled focusable regions on narrow screens.
Worker progress uses live text/counts, never an invented completion percentage. Inputs remain
available after failed requests. Files must be reselected after page refresh; browsers cannot
restore file grants silently. Unknowns render as Unknown, never as numerical zero.

## Verification

`make check` checks generated contract drift, backend/frontend lint and types. `make contracts`
regenerates TypeScript directly from executable Pydantic input/result/profile models and copies
the synthetic input fixture. Preflight uses `POST /v1/dashboard/validate` with a 512 KiB cap,
requires verified identity, and returns field paths/error codes without echoing input values.
`GET /v1/dashboard/config` supplies only auth mode and public transfer/retention limits.

`make test-browser` requires project-local services, Docker and the benchmark image, plus
installed Google Chrome (`channel: chrome`). It starts isolated development ports 8010/5174,
an ephemeral PostgreSQL schema, bucket, queue and workspace, then runs Playwright against real
services/workers. It removes its resources and stops its processes, preserving local volumes.
It does not start or stop infrastructure automatically. See
[S10 verification](evidence/s10-verification.md) for actual results and limitations.

## Optional requirement and explanation assistance (S11)

After selecting a project, **Review requirement proposals** extracts explicitly stated
retention/freshness and asks consequential missing questions. Review source passages,
edit values or clear them to unknown, then **Confirm and apply reviewed requirements**.
The original description and accepted version are preserved. Policy/workload changes
require another confirmation. Manual editing and assessment submission remain usable
without assistance. Optional AI requires approving the displayed summary first; it
never receives raw files or query text. Missing keys or provider failures retain the
local workflow.

Results include evidence-linked guidance. Optional AI can prioritize verified evidence
cards; financial values still come exclusively from calculated result fields. Coverage
limitations remain visible for every outcome. See [AI boundaries](ai-boundaries.md)
for the exact provider setup, supported extraction syntax, budgets and API paths.
