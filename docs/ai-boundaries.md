# Structured assistance (S11)

The assessment works without an LLM. Local rules propose explicitly stated retention
in days (`retention 30 days`, `retain data for 30 days`) and freshness in seconds
(`freshness 60 seconds`). Conflicting mentions, unsupported units and other fields
require manual editing. This is a deliberately narrow extractor, not a complete natural
language requirements interpreter. Missing workload, retention, freshness and cost
questions are derived from the actual request. Known inputs are not asked again.

## Review, edit and confirm

Create/select a project, then use **Review requirement proposals**. This stores the
original description and shows source passages, proposed values and consequential
questions. Edit a value or clear it to keep it unknown. **Confirm and apply reviewed
requirements** creates an immutable version of the accepted executable request.
Nothing is applied to the draft before confirmation. Accepted policy and workload
are fingerprinted; changing either requires confirming again. Cost assumptions and
analysis budgets can still be edited. Confirmation IDs survive a local-demo refresh
in scoped sessionStorage, alongside the existing draft; verified sessions remain
memory-only. The browser still requires selecting a ready dataset after a refresh
before a new submission. Already-submitted assessments recover through history.

The stored assessment links its confirmation ID; the confirmation references the
original proposal, accepted request and monotonically increasing project version.
The engine's authoritative requirements snapshot and report remain unchanged by AI.
Manual assessment submission without using assistance remains supported.

## Optional provider setup

Only the FastAPI process needs these server environment variables; never prefix a
provider secret with `VITE_`. Run existing locked setup, `make infra-up`, `make migrate`,
`make seed-local`, `make storage-init`, then the usual API/frontend/worker commands.
Migration `0006_structured_assistance.sql` adds proposal/confirmation/usage records.

| Setting | Default / behavior |
| --- | --- |
| `LLM_PROVIDER` | `disabled`; set `openai` to enable explicit requests |
| `LLM_API_KEY` | Unset; Pydantic SecretStr, never sent to the browser or logs |
| `LLM_MODEL` | `gpt-5.4-mini-2026-03-17`, configurable server-side |
| `LLM_TIMEOUT_SECONDS` | 15 seconds for transport operations; elapsed response checks stop slow streaming, at most one further read timeout may elapse |
| `LLM_MAX_OUTPUT_TOKENS` | 800; schema validation still required |
| `LLM_MAX_INPUT_BYTES` | 32768 for the serialized provider request, including schema/instructions |
| `LLM_CALLS_PER_SCOPE` | 4 attempts per assessment for explanations; intake uses a shared project scope |
| `LLM_TOKEN_BUDGET_PER_SCOPE` | 100000 conservative reserved tokens per scope |

The fixed HTTPS OpenAI Responses destination uses `text.format` with strict JSON
Schema, `store: false`, no tools, no redirects, no automatic retry, a bounded 128 KiB
response and prompt/schema version `s11.1`. It uses the existing locked HTTPX package;
no JavaScript AI SDK or additional provider dependency is needed for the Python API.
The configured default model supports Responses/structured output and defaults to
no reasoning. Model availability for a particular account is not proven by docs.
`store: false` does not promise zero provider retention; account/provider policy applies.

The server reserves serialized UTF-8 request bytes plus maximum output tokens under
a PostgreSQL project lock *before* making a call. Reservations persist across process
restarts and concurrent requests and are not refunded after errors. This is conservative
admission accounting, not observed token billing or a currency spend estimate. No prompt
or completion body is stored in usage rows. Creating another proposal cannot reset its
project budget. Changing budgets is an administrator action; there is no browser reset.

## What crosses the boundary

No provider call happens on project creation, preview, polling, benchmarking or result
loading. A user must inspect the exact summary and approve it with its fingerprint:

- Intake sends only the deliberately reviewed description, source-cited allowed fields,
  question identifiers and prompt version. The description may itself be sensitive;
  the user can remove details before review. Full assessment requests are used locally
  to determine missing questions but are not provider inputs.
- Explanation sends only report/decision fingerprints, outcome and allowed
  candidate/evidence/reason references. It excludes profile statistics, field names,
  records, paths, query identifiers/literals, workload text, costs and credentials.

Uploaded files and query content are never available to the provider adapter. Text
that looks like instructions stays data; the provider has no execution tools, database
connection, filesystem access or ability to choose a configuration outside the report.

## Grounding and failure behavior

Provider intake output can prioritize/select only the validated source-cited proposals
and consequential missing question identifiers. Arbitrary fields, changed values,
fabricated quotes and execution keys fail validation. The provider cannot invent a
configuration, transform data or write a metric. A user may still explicitly edit a
proposed value before accepting it; that is recorded as user-confirmed input.

Explanations are constrained selections of evidence cards, not unrestricted prose.
Every card must exactly match a server-computed allowed candidate/evidence/reason
triple. Statement text comes from checked templates. A scope warning is mandatory.
Unsupported IDs, false selected/feasible claims, invented numbers and arbitrary text
are rejected. Authoritative numbers always come from existing Results components
and calculated API fields, never from model text. An explanation never mutates the
assessment, prices, decision, report or stored evidence.

Disabled/missing key, invalid output/schema, refusal/incomplete response, timeout,
provider outage/rate limit, oversized output, input limit and usage exhaustion return
explicit statuses plus deterministic proposals/cards. Error bodies and submitted text
are not echoed or logged. Preview/confirmation still works when AI is unavailable.

## APIs and verification

All endpoints require the existing verified local/JWT identity and tenant/project
ownership; deleted projects and unavailable/expired assessment copies are inaccessible.
Requests have a streamed 512 KiB body cap.

| Operation | Endpoint |
| --- | --- |
| Local proposal/review | `POST /v1/projects/{project}/intake` with description and request |
| Read original proposal | `GET /v1/projects/{project}/intake/{proposal}` |
| Optional AI selection | `POST .../intake/{proposal}/refine` with approved_summary_fingerprint |
| Confirm edited request | `POST .../intake/{proposal}/confirm` with request |
| Checked explanation preview | `GET /v1/assessments/{assessment}/explanation` |
| Optional AI card selection | `POST .../explanation` with approved_summary_fingerprint |

Assessment submission accepts optional `intake_confirmation_id`. A foreign confirmation
returns 404; a policy/workload mismatch returns 409. Proposals, confirmations and the
assessment's confirmation reference are protected against updates by database triggers.

Run `make check`, `make test`, `make test-integration`, and
`uv run --locked --project backend python scripts/verify-s11-browser.py` for the
isolated real-service browser flows. See [verification](evidence/s11-verification.md).
Provider transport and configured success/failure paths use deterministic mocked
responses. **No live provider quality, latency, billing or account-access result is
claimed.** There is no customer/pilot validation or production deployment.

Official documentation checked on 2026-11-02:
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[Responses request contract](https://developers.openai.com/api/reference/resources/responses/methods/create),
[configured model and snapshot](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
