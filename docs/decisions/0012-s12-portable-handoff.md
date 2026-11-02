# Decision 0012: portable calculated reports and deliberate local reproduction

Date: 2026-11-02 (Asia/Kolkata)

Reuse S08/S09 immutable evidence and calculated values for a versioned `s12.1` bundle,
Markdown, escaped dependency-free HTML and ZIP. Do not introduce PDF tooling or an LLM
report generator. Include original references and immutable S11 confirmation lineage, while
omitting business descriptions, AI summaries and unnecessary free-text provenance notes.
Preserve needed schema/workload literals with a clear privacy notice. Retain original
nested evidence digests as references before narrative redaction; independently hash all
exported content. A digest is not an authenticity signature.

Generate only a static positional-argument shell template that delegates to typed Python.
Local reproduction rejects different input/workload/conversion versions; full assessment
reproduction also requires the recorded immutable image and benchmark hardware/kernel/Docker
version. It runs fresh real measurements and compares outcome/configuration, without claiming
identical timings. Changed decisions are saved and surfaced with exit 1. Only a verified
feasible `change` can generate a local candidate copy; every new copy passes existing exact
integrity and canary workload checks. Keep-current/guidance cannot masquerade as a migration.
Real reader compatibility, capacity planning, canary switching and rollback remain deliberate
human actions with source and prior reader configuration retained. No automatic production
mutation, source deletion or cloud transfer.

Keep downloads behind verified owner authentication, with a tenant/assessment/bundle-bound
expiring grant in PostgreSQL. Generate from stored hash-checked evidence on demand instead
of duplicating large export objects in MinIO. Recheck ownership, retention/deletion, grant
expiry and export fingerprint for every transfer. Rotate grant identifiers when refreshed;
no bearer credential or signing secret is needed. This local implementation fits the existing
streaming/API ownership model; distributed/static object delivery remains a future decision.

No dependency/stack change. Reuse the isolated S11 browser runner with configurable evidence
prefix/test spec so export flows run against real local services without duplicating cleanup.
See [runbook](../runbooks/reports.md) for interfaces and [evidence](../evidence/s12-verification.md).
