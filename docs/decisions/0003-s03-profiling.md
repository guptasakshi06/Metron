# Decision 0003: conservative local profiles and reviewed metadata import

Date: 2026-11-02 (Asia/Kolkata)

- Keep the selected Python/PyArrow stack. Use streaming standard-library CSV/JSON for
  conservative text, exact JSON decimals and missing/null semantics; Arrow for Parquet.
  Do not add DuckDB until workload execution needs it. Readers never infer numeric IDs
  or timestamps from strings. Ambiguous values stay text; explicit overrides are reviewed
  local configuration. Reject unsupported precision instead of truncating.
- Use bounded two-pass bottom-k row-position sampling across explicit day/source strata.
  This scans every record, records coverage, and has no hidden first-rows bias or claimed
  I/O savings. Cardinality uses a bounded KMV sketch with exact/estimated labels.
- Default exports anonymize all column names and contain no raw values/examples/source
  paths. Optional sensitive-field rules also suppress value-derived statistics and row
  widths for those fields. Metadata remains potentially sensitive; a matching reviewed
  report fingerprint is required for optional CLI/API transfer.
- Persist local cache entries and PostgreSQL imported versions now; S09 should extend the
  existing `profiles` table for server-generated evidence, not recreate it. Imported
  metadata can exist without an uploaded dataset. It always remains locally supplied,
  unverified raw-data evidence. The API assigns ownership and immutable version numbers.
- Profile parsing uses a fresh process with Linux resource limits; no network code is
  called. Full benchmark network/filesystem isolation and server-side job admission remain
  S06/S09. Defaults are policy bounds, with actual S03 resource evidence recorded separately.
- Correct `make check` to pass `--config-file backend/pyproject.toml` to mypy. Previously,
  running at repository root skipped the nested strict configuration. Enable it and fix
  the three existing missing/obsolete annotations without changing their runtime behavior.
