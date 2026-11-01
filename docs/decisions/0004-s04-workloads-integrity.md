# Decision 0004: constrained workloads and exact semantic comparison

Date: 2026-11-02 (Asia/Kolkata)

- Add DuckDB for S04 workload execution, as selected by the architecture. The lockfile
  resolves DuckDB 1.5.6 and pytz 2026.6. This client's TIMESTAMPTZ result conversion
  required pytz during real golden tests. No framework change.
- Keep S01 `domain.contracts.WorkloadSpecification` as a descriptive contract for
  compatibility. Executable `workloads.models.Workload` is version 1, DSL `s04.1`.
  S09 must validate this executable contract instead of executing descriptive column
  lists or user SQL. Unknown requirements stay null.
- Reuse S03 readers for explicit interpretation of each input. Compare full canonical
  row bytes in a disk-backed SQLite multiset with signed counts. This is exact equality
  with multiplicity, not a sketch or raw file hash. Typed length framing distinguishes
  missing/null, bool/integer, text/numeric IDs, decimal scale and binary floats. Aware
  timestamps represent UTC instants; naive timestamps retain wall-clock semantics.
  Array order matters; object key order does not. Row order and original bytes are
  separately selectable requirements.
- Both-Parquet comparisons also require identical declared Arrow schema fingerprints.
  Cross-format equality covers observed logical content under selected reader semantics;
  it does not preserve every physical schema annotation or original syntax. Require
  original-byte retention for signatures, lexical JSON/CSV, unmodeled annotations,
  original offset spelling, forensic provenance or contractual byte equivalence.
- Execute against one fresh in-memory `assessment_data` table. The DSL has no
  dataset/table/file/SQL fields. Validate identifiers and operation enums, bind values,
  disable external access, auto-install/load and community/unsigned extensions, disable
  spill, use one thread and lock configuration. Python supplies typed rows in batches;
  DuckDB never reads the source path. Unsupported schemas return not_checked with reasons.
- Stored-content equality never uses tolerances. Query output comparison is exact by
  default. Explicit absolute/relative tolerances apply only to binary floating point.
  Unordered tolerant results require a multiplicity-preserving perfect matching, bounded
  to 256 rows. See the runbook for operation and numeric policies.
- Persist atomic versioned JSON evidence, check/query statuses, capability exclusions,
  fingerprints, tolerance/order policies and engine versions now. PostgreSQL assessment
  ownership/persistence remains S09. Local files are not server-attested evidence.
  No performance pass follows from output equality or absent workloads.
- The public verifier runs in a resource-limited Linux subprocess. Canonical customer
  rows spill temporarily to a private directory owned by the parent, which removes it
  after success, failure or forced worker timeout. Use private/encrypted temporary storage.
  OS namespace isolation, cancellation orchestration, whole-process-crash cleanup and
  calibrated benchmarking remain S06/S09. Do not expose internal helpers directly as API
  handlers; their callers must already enforce resource bounds.

Official references checked for the selected DuckDB version:

- [Python DB API](https://duckdb.org/docs/1.5/clients/python/dbapi)
- [Python conversion semantics](https://duckdb.org/docs/1.5/clients/python/conversion)
- [Securing DuckDB](https://duckdb.org/docs/1.5/operations_manual/securing_duckdb/overview)
- [Extension restrictions](https://duckdb.org/docs/current/operations_manual/securing_duckdb/securing_extensions)
