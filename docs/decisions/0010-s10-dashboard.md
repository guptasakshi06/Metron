# Decision 0010: checked dashboard contracts and explicit evidence boundaries

Date: 2026-11-02 (Asia/Kolkata)

- Retain React/TypeScript/Vite and native form controls. The four anchored sections on `/`
  use existing owned project/dataset/profile/assessment APIs. Polling is sufficient for
  local worker stages; no new streaming infrastructure or router dependency is needed.
- Generate request, serialized result and local-profile TypeScript from executable Pydantic
  JSON Schemas, including references, unions, enums, arrays, tuples and nullable Decimal
  serialization. `make check` fails when generated contracts or the copied demo request drift.
  Runtime preflight validates the complete executable request on the server. Field paths and
  controlled error codes avoid echoing record values into error responses.
- Keep costs unknown by default. A deliberate synthetic-example action imports assumptions,
  not results. The UI renders exact returned decimal strings and separates measured sample
  bytes/timings, modeled costs, synthetic/user-supplied pricing and absent production actuals.
  Baseline migration is explicitly zero under the ranking contract. Coverage, failed/partial
  trials, exclusions, limitations and raw lineage remain inspectable for every outcome.
- Preserve scoped local demo drafts/IDs/pending idempotency keys in sessionStorage; file bytes
  and metadata reports stay in memory. Fixed local identities are discovered from server auth
  mode. JWT tokens/drafts are memory-only. Identity changes unmount/abort the previous workspace.
  Production login integration remains a separate requirement; no credentials are fabricated.
- Use XMLHttpRequest upload events for actual transfer progress; finalization remains a distinct
  server-validation stage. Retention and consent precede transfer; dataset deletion uses existing
  tombstones/cleanup and touches only stored assessment copies. Metadata requires review before
  its fingerprint-bound import. No inference of schema semantics is hidden in the UI.
- Add Playwright as a locked development dependency and use installed Chrome. Browser tests run
  against isolated real PostgreSQL/MinIO/RQ/Docker, with no mocked measurements. Unit tests
  cover failures/session gating; end-to-end tests compare displayed totals/line items with API
  evidence. No public deployment or cloud service is needed.

Official references checked at implementation: [React effects](https://react.dev/reference/react/useEffect),
[upload progress](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/upload),
[Playwright configuration](https://playwright.dev/docs/test-configuration).

User flow and limitations: [dashboard guide](../user-flow.md).
