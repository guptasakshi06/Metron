# S11 verification — 2026-11-02, Asia/Kolkata

Implemented structured optional intake and grounded explanations. Local rules, manual
requirements and the full measured assessment need no provider key. Original descriptions,
source-cited proposals and edited/accepted requirement versions are persisted. The
assessment carries the immutable confirmation reference. Provider output cannot set
metrics, prices, execution instructions or unsupported candidate/requirement references.

## Commands and observed results

| Command from repository root | Result |
| --- | --- |
| `UV_OFFLINE=1 make check` | Passed generated contract drift, Ruff, strict mypy on 88 source files, ESLint and TypeScript |
| `UV_OFFLINE=1 make test` | Passed 337 backend + 7 frontend; backend 52 service/Docker tests deselected by default |
| `UV_OFFLINE=1 make test-integration` | Passed all 42 real service tests in 47.62 seconds, including 10 S11 tests |
| `UV_OFFLINE=1 make build` | Passed Python sdist/wheel and Vite; final JS 269.98 kB / gzip 82.01 kB |
| `UV_OFFLINE=1 make test-assistance-browser` | Passed both actual Chrome/API/PostgreSQL/MinIO/Redis/worker/Docker flows in 12.2 seconds; exit 0 and explicit cleanup record |
| `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend python scripts/verify-s11-package.py` | Passed import/OpenAPI/schema and six packaged migrations from extracted wheel outside source checkout |
| script Ruff and `git diff --check` | Passed after fixing new Markdown trailing whitespace |

Logs: `s11-check.log`, `s11-test.log`, `s11-integration.log`, `s11-build.log`,
`s11-browser.log` and private-fixture dev/dispatch/worker logs. Machine summary, source
hashes and limits: [verification results](s11-verification-results.json).
Package hash: [wheel smoke results](s11-package-results.json).

## What was tested

The 32 deterministic S11 unit cases exercise explicit unit extraction, conflicting and
unknown inputs, consequential questions, fabricated values/quotes/fields, unsupported
configurations/execution keys, instruction-like text, exact candidate/evidence matching,
three prior saved report outcomes, strict provider schemas, fixed destination/no secret
in request body, malformed response envelopes, refusal/incomplete output, non-object
JSON, timeout, rate-limit/outage, oversized output and error sanitization. Transport uses
HTTPX MockTransport; these are **not live provider calls**.

Ten S11 integration cases use real isolated PostgreSQL/MinIO and authentication. They
verify proposal ownership, original input preservation, edited version history,
DB immutability triggers, linked assessment creation, stale-requirement rejection,
optional provider success/failure/missing-key/input/token/call budgets, and concurrent
admission. A newly-created proposal cannot reset project usage. Configured-provider
success deterministically selects relevant missing questions; failures preserve the
local workflow. Real raw-data conversion/benchmark produces a report whose bytes
remain identical before/after optional explanation selection. Prompts exclude raw
records, private query identifiers, schema, price amounts and provider secrets. Expired
assessment and cross-tenant explanation/proposal reads are rejected.

Two browser flows verify the actual application with the provider disabled:

1. Upload synthetic NDJSON, load explicit synthetic cost assumptions, review/edit
   retention, approve optional AI and receive a usable fallback, confirm the accepted
   request, refresh, select the existing dataset and run a real measured change. The
   confirmation ID survives refresh, accepted retention appears in the immutable report,
   explanation fallback renders, and displayed candidate horizon totals equal API strings.
   The stored report is unchanged by explanation requests. No browser JavaScript errors.
2. Confirm startup retention/freshness, edit requirements and see an actionable request
   to reconfirm; accept the second version and receive insufficient-evidence guidance
   with explicit coverage limits.

Three frontend unit tests cover approval/confirmation gating, cleared-to-unknown values,
missing-key fallback and late confirmations after switching projects. Desktop 1440x1000
and narrow 390x844 explanation screenshots were inspected; labels are readable, IDs wrap
and there is no page-wide overflow. Screenshots: `s11-explanation-desktop.png` and
`s11-explanation-narrow.png`. These are local Chrome checks, not a comprehensive
screen-reader or cross-browser audit.

Actual browser-produced synthetic reports: [measured change](s11-measured-change-report.json)
and [startup guidance](s11-startup-report.json). These use invented amplified offline rates;
there is no customer savings claim. The browser runner removed its isolated schema,
bucket, queue keys, scratch workspace and child processes. Local Compose services are
stopped at session end with named volumes preserved; no benchmark containers remain.

## Limits and intermediate fixes

No provider key is configured and `LLM_PROVIDER=disabled`: live smoke is **not_run**.
Current official structured-output/Responses/model docs were checked; configured default
is `gpt-5.4-mini-2026-03-17`. Actual account access, provider schema acceptance, model
quality, latency, usage/cost and retention policy remain unverified. Source-scope selection
and template rendering deliberately replace unconstrained generated prose. Extraction
supports explicit retention/day and freshness/second syntax only. Other requirements
remain manual. No custom training, public deployment, paid service provisioning or
production mutation. Separate ten-test sandbox suite was not rerun; sandbox code is
unchanged and real Docker paths ran in service and browser verification.

Intermediate failures were resolved: React's export-only refresh rule moved a helper into
`api.ts`; duplicate unit/service test basenames were renamed; package smoke uses generated
OpenAPI paths because this FastAPI version exposes included routers; malformed provider
response shapes were given explicit fallback coverage. Final checks, full unit/frontend
suite, service suite, package smoke and browser flows pass. Existing TestClient/httpx
deprecation and Node color-environment warnings remain.
