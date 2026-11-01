# S03 dataset semantics and profile evidence

The profiler reads local copies and produces metadata. It does not transform records,
remove duplicates, benchmark queries, prove cross-format integrity or recommend savings.
S04 adds [semantic comparisons and workload checks](runbooks/workloads-integrity.md).
Source bytes are never changed by profiling or integrity checks.

## Readers and explicit interpretation

- CSV: UTF-8 (optional BOM), comma delimiter, standard CSV quoting and multiline fields,
  unique nonempty header, rectangular rows. Every field is text by default, including
  `0001`, empty strings, `NULL` and decimal-looking strings. `csv_null_tokens` explicitly
  selects exact strings interpreted as null; quoted and unquoted tokens have the same
  interpretation. No default null token exists. A warning requests explicit overrides
  before downstream numeric/time operations. No automatic delimiter/type guessing.
- NDJSON: UTF-8 object per nonblank line, optionally gzip (including concatenated members).
  Missing keys remain absent; explicit nulls remain null. Integers use Python integers;
  fractional JSON numbers use exact `Decimal`, never binary floats. Duplicate object keys,
  nonstandard numbers, malformed records and unsupported structures fail with sanitized
  errors. Objects and arrays are opaque typed values: their widths/cardinality can be
  profiled, but nested leaves are not flattened or inferred. Mixed types and schema drift
  are retained, with a warning to review the schema.
- Parquet: [PyArrow bounded batches](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetFile.html), schema preserved in the schema fingerprint, including
  physical logical types, decimal scale/precision and timestamp units/timezones. Original
  field metadata is hashed locally and never exported. Native scalars are interpreted
  without schema inference. Arrow extension deserialization is disabled. Unsupported
  scalar conversions fail; nanosecond timestamp values that cannot be represented exactly
  as Python microseconds are explicitly rejected. No pandas dependency or truncation.
- Explicit top-level `schema_overrides`: `string` (requires actual text), `integer`,
  `decimal` (rejects floats/booleans), `timestamp` (ISO datetime), `boolean` (actual booleans
  or lowercase `true`/`false`). Overrides are a user choice and can change meaning; choose
  them only after reviewing the source schema. Unknown fields and invalid casts fail.
  Timestamp parsing rejects fractional seconds longer than six digits. Aware timestamps
  compare on UTC instants, while naive timestamps stay naive; mixing the two never yields
  a combined temporal span. Strings stay strings unless explicitly overridden.

Readers stream text using the standard library to retain missing/null and decimal
semantics; PyArrow handles Parquet. This avoids first-block inference and adds no new
runtime dependency. Local files are required; URLs, directories, globs, archives other
than gzip NDJSON, automatic partition discovery, arbitrary SQL and external readers
are unsupported. Dataset multiplicity is preserved, including identical events.

## Statistics and coverage

`row_count`, physical bytes, one-file size distribution and discovered top-level schema
are exact for a completed full traversal. `decoded_bytes` counts decompressed text bytes
or decoded Arrow batch bytes per traversal; these two metrics have different encoding
boundaries and are not interchangeable logical dataset sizes. The two traversals each
have their own decoded-byte budget. Raw bytes are fingerprinted before and after processing.

Column distributions, null density, widths and cardinality apply to **profiled rows**.
Missing and present-null counts are separate. Null density is null/present, or null when
nothing is present. Cardinality excludes missing/null values, hashes typed canonical
values, and is exact until the configured KMV sketch capacity is exceeded. Above that
it is labeled `kmv_estimate`, bounded by the nonnull sample population; it is not a
population extrapolation. Decimal textual scale is retained in this statistical encoding.
The encoding is for statistics, not a cross-format integrity proof.

Widths use typed canonical-value bytes and bins `<=16`, `<=64`, `<=256`, `<=1024`, `>1024`.
Row widths sum top-level value widths and omit fields explicitly marked sensitive.
Temporal spread is elapsed seconds within one awareness scope, without exporting actual
minimum/maximum timestamps. File-size bins refer to physical bytes; S03 supports one file.

Full scan is the default. Optional bottom-k sampling chooses row positions using a SHA-256
priority of seed, input fingerprint and row index. It traverses the full input twice,
retains only bounded position heaps, and profiles at most k rows in each configured stratum.
This is reproducible sampling, not a reduction in scan I/O. Strata can combine UTC calendar
day (aware time) / wall-clock day (naive time) and typed source identifier. Time requires
an actual timestamp or an explicit override. Null/missing time has a separate bin; source
missing/null are distinct. Too many strata fail with a quota error: select a coarser source
or remove stratification; full scan also honors the configured stratum cap. Reports show
anonymous stratum IDs and counts, seed, profiled fraction and uncovered limitations.
Sampling a gzip stream or Parquet follows this same two-pass process; no row-group,
partition or time-range skipping is claimed.

## Privacy, reproducibility and resource boundary

Default exports contain no raw rows, examples, distinct values, source paths, override
names/tokens or timestamp endpoints. All field names are positional aliases, ordered by
original field name. `include_field_names` is explicit opt-in. `redacted_fields` always
hides those names, widths, cardinalities and temporal spread, even with names enabled.
Type/null/missing counts remain. Statistics, hashes and even field counts may be sensitive:
review the full JSON before upload. This is redaction, not differential privacy.

Profiles include input/schema/settings/report SHA-256 fingerprints and Python/PyArrow
versions. Report versions are immutable in PostgreSQL; a matching import is reused within
the owned project. Local cache keys cover input, all options, engine versions and profiler
version. Invalid caches fail closed; changed input/settings produce a new key. Hashes detect
mismatches and corruption; they do not authenticate a local user's evidence or prove that
the server inspected raw records. Imported evidence is always `local_profile` and
`raw_data_inspected_by_server=false`.

Parsing runs in a fresh Linux process with address-space, CPU, wall-time, core-dump and
output-file limits. Default policy: 256 MiB input, 1 GiB decoded per pass, 1 MiB record,
128 top-level columns, 32 strata, 1024-entry cardinality sketches per field, 1024 MiB
address space and 60 seconds CPU (+2 seconds parent wall grace). Exported JSON is bounded
to 2 MiB. These are policy bounds, not measured capacity guarantees. Memory failure,
timeout, oversize records/columns/strata and decoded-byte exhaustion return clear quota
codes; partial profiles are never published. Parent fingerprinting/library loading is
outside the worker memory quota. No input copy or spill file is created; only a bounded
report is written in a private temporary directory and removed after completion/failure.

This boundary is for local read-only parsing. It is not an OS network namespace, syscall
sandbox or independent security principal. There are no network calls in the local path;
server-side execution/admission and stricter benchmark isolation arrive in S06/S09.
