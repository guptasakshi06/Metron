# Local profiling and optional metadata import

Use project-local tooling from the repository root. No API key, running service or
network connection is required for profile/export/review/local import.

```bash
export PATH="$PWD/.tools/node24/bin:$PWD/.tools/uv-bin:$PATH"
uv run --locked --project backend python backend/tests/fixtures/profiling.py /tmp/s03-fixtures
uv run --locked --project backend data-optimizer profile /tmp/s03-fixtures/synthetic-events.csv \
  --format csv --options examples/s03-profile-options.json --output /tmp/s03-profile.json \
  --cache /tmp/s03-profile-cache
uv run --locked --project backend data-optimizer profile-review /tmp/s03-profile.json
uv run --locked --project backend data-optimizer profile-import /tmp/s03-profile.json \
  --store /tmp/s03-metadata-store
```

Inspect `/tmp/s03-profile.json` yourself before optionally transferring it. `profile-review`
validates and prints counts and a fingerprint; it cannot decide whether your metadata
is safe to disclose. It does not transmit anything. Files/cache entries are written
atomically with mode 0600. Keep local reports/caches out of Git and secure their directory.
See [dataset semantics](../dataset-semantics.md) for limitations and redaction settings.

For a real local API import, start infrastructure, migrate and seed local identities:

```bash
make infra-up
make migrate
make seed-local
make dev
```

Create a project via `POST /v1/projects` using `X-Local-Identity: alice` as described in
the ingestion runbook. Copy the reviewed report fingerprint from `profile-review`, then:

```bash
uv run --locked --project backend data-optimizer profile-import /tmp/s03-profile.json \
  --api-url http://127.0.0.1:8000 --project-id PROJECT_UUID \
  --reviewed-fingerprint REVIEWED_REPORT_SHA256
```

The CLI requires an explicit loopback HTTP URL, project and matching review fingerprint
before its only network action. It does not follow redirects, use proxy env vars, accept
remote local-identity transfer or upload raw files. External clients may call the API using
the existing verified JWT integration; production identity/deployment setup remains
unverified. No live provider credentials are needed for local use.

API contract:

- `POST /v1/projects/{project_id}/profiles`: JSON `{report, reviewed_fingerprint}`; max 2 MiB,
  validated report/fingerprint, returns 201 with profile ID/version/provenance/reuse flag.
- `GET /v1/projects/{project_id}/profiles`: owned active metadata versions.
- `GET /v1/projects/{project_id}/profiles/{profile_id}`: version and original reviewed report.
- `DELETE /v1/projects/{project_id}/profiles/{profile_id}`: removes payload, retains a tombstone
  and audit entry. Reimporting the deleted fingerprint returns 409; generate a new profile.
- Project deletion removes all profile payloads and hides them. Nothing touches source data.

All operations enforce project/tenant ownership. Default `MAX_PROFILES_PER_PROJECT=100`
counts version tombstones too, preventing unbounded churn. Import is metadata evidence,
not a server-measured dataset or benchmark. A digest is an acknowledgement, not a proof of
human review. Future UI must show the report and capture the same explicit review step.

Reproduce the resource exercise without retaining generated input files:

```bash
uv run --locked --project backend python scripts/profile-resource-check.py \
  --output /tmp/s03-resource-results.json
```

Recorded local observations are in [S03 resource evidence](../evidence/s03-resource-results.json).
They are synthetic local measurements, not production throughput or memory guarantees.
