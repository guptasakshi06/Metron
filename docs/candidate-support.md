# S05 candidates and local conversion

This offline path generates bounded alternatives, writes new copies and verifies exact
logical content and supplied workload outputs. It does not measure query performance,
choose a recommendation or calculate savings. API/MinIO assessment orchestration is S09.
The caller supplies tenant/assessment UUIDs for local organization; they are not proof of
identity or a replacement for server authorization.

## Run

After locked setup, from the repository root:

```bash
export PATH="$PWD/.tools/node24/bin:$PWD/.tools/uv-bin:$PATH"
uv run --locked --project backend data-optimizer candidate-list \
  examples/s04-events.ndjson --request examples/s05-conversion-request.json \
  > /tmp/s05-candidates.json
uv run --locked --project backend data-optimizer convert \
  examples/s04-events.ndjson --request examples/s05-conversion-request.json \
  --root /tmp/data-optimizer-s05-artifacts > /tmp/s05-conversions.json
```

Repeat the conversion to get `reused` for compatible published outputs. Excluded
candidates remain explicit and do not make an otherwise successful CLI run fail.
Exit 1 means a conversion failed/cancelled; 2 means invalid input, incompatible/corrupt
stored evidence or an operational error; Ctrl-C exits 130 after stopping the worker and
removing unpublished outputs. Review the JSON, including all statuses. Output JSON goes
to stdout; shell redirection is the user's responsibility and must not target sources.

For one candidate, save a `configuration` object from the candidate-list output into a
JSON file and pass `--configuration FILE.json` to `convert`. No SQL, shell command,
external reader or arbitrary output filename is accepted in that configuration.

## Configurations and bounds

Version 1 configurations contain format, codec/level, estimated file-size target,
row-group rows, partition/sort columns, baseline flag and fixed execution context.
`CandidateConfig.fingerprint` is SHA-256 of compact, key-sorted JSON of all these fields.
Context records converter `s05.1`, local filesystem, PyArrow, Arrow C++, Python, DuckDB,
canonical version and runtime zlib versions. Changed context is excluded rather than
reusing old-context outputs. Snappy/Zstandard are supplied by the locked Arrow build;
independent bundled codec library versions are not exposed by this implementation.
The manifest also stores S04 engine versions. No dependency/lockfile change was needed.

The bounded enumeration defaults to at most 8 configurations (configurable 4–12):

| Candidate | Defaults |
| --- | --- |
| Current representation | Exact byte copy, `codec=original`; no source rewriting |
| Compressed NDJSON | gzip level 6, deterministic gzip header |
| Parquet Snappy | 65,536-row groups |
| Parquet Zstandard | level 3, 65,536-row groups |
| Row-group alternative | Zstandard, 16,384-row groups |
| Sort alternative | First workload time-range column, otherwise first predicate column |
| Partition alternative | First workload group-by column; all columns retained in files |

Unpartitioned candidates are always included. This is a bounded search space, not an
exhaustive search. `eligible` means provisionally supported; output integrity and runtime
layout quotas must still pass. All supplied queries must pass before publication. With
no workload, exact content can pass while workload remains `not_checked/missing_workload`;
performance always remains `not_measured`.

File targets default to 64 MiB and use decoded-size estimates. They are not hard physical
file sizes: codec ratios, footer overhead and individual rows affect actual sizes. Request
policy defaults: at most 16 partitions, 32 data files and 512 MiB output/scratch data;
each partition needs at least 128 rows. Bounds are configurable. Excess partition count,
small partitions or excessive file count yield explicit exclusions. Layouts conflicting
with required record order are excluded. Baseline copying preserves order and bytes.

## Semantics and exclusions

Reuse [S03 reader semantics](dataset-semantics.md) and [S04 exact checks](runbooks/workloads-integrity.md).
CSV uses explicit overrides; otherwise numeric-looking strings and identifiers remain
strings. NDJSON decimals are serialized without binary float conversion and preserve
scale; timestamps use the reviewed timestamp override. Missing keys, nulls, nested objects,
arrays and duplicates can survive NDJSON gzip conversion. Binary/float/date cross-format
NDJSON needs an encoding contract and is excluded. gzip outputs may be split; their
ordered concatenation uses standard concatenated gzip members.

Parquet alternatives exclude missing fields, mixed types, nested semantics without an
explicit encoding, int64/decimal128 range violations and varying per-value decimal scale.
Native Parquet schemas/metadata are reused when no overrides are selected. Both-Parquet
integrity also checks the complete declared Arrow schema. Unsupported reader/schema
behavior becomes a failed outcome, never a silent cast/drop. For example, Arrow decimal
negative zero loses its sign: exact canonical comparison rejects publication and returns
failed integrity evidence. Original-byte requirements exclude every byte-changing option.
Unsupported codecs/levels, unavailable codecs, unknown layout columns and changed execution
contexts have explicit reasons. Supported gzip levels are default/1/6/9; Snappy has no
level; Zstandard accepts the typed -5 through 22 range supported by this writer.

## Artifacts, validation and recovery

```text
ROOT/TENANT_UUID/assessments/ASSESSMENT_UUID/
  .locks/KEY
  .partial-KEY/                 # unpublished; removed on handled failure/cancellation
  KEY/
    manifest.json
    part-0000.parquet           # or .ndjson.gz / .original
    p0000/part-0000.parquet     # partition variants use opaque numbered folders
```

KEY hashes input SHA-256, complete request (including interpretation, workload, limits and
ownership IDs), and complete configuration/context. Partition values are retained in data
columns, not exposed as directory names. Originals remain unchanged.

The worker closes all outputs and reads the actual files back. For multiple files, it
builds a temporary ordered concatenation, verifies it against the original with S04,
then removes it. The manifest binds the ordered data-file list, sizes and hashes to this
verification request/report and declared concatenation policy. It includes exact physical
data bytes and file count, partition count, conversion wall time, validation wall time,
whole-worker CPU seconds and process peak RSS (Linux KiB). Manifest/lock/directory filesystem
overhead is not included in physical data bytes; later economic modeling must define its
storage boundary. These observations are local conversion evidence, not query benchmarks.

A passed manifest is required before same-filesystem atomic directory rename publishes
KEY. No fsync/power-loss durability guarantee is claimed. Reuse verifies manifest/report
fingerprints, original/request/configuration identity, every data file's size/hash and the
absence of unexpected data files. Corrupt published outputs fail closed and are preserved
for inspection; a caller must deliberately choose a new assessment prefix or remove their
own corrupt copies. Matching concurrent calls lock one key and publish only once.
The worker inherits the lock descriptor, so parent death does not let a retry delete
scratch still owned by a running worker. Once the lock is released, retry removes that
key's orphaned `.partial-KEY` and rebuilds it; unrelated partials are preserved.

## Resource and deployment boundary

Conversion runs in a fresh Linux subprocess with request CPU/address-space limits,
parent-enforced wall time, no core dumps and a per-file size limit. S04 row/SQLite/query
limits and S03 input/decompressed/record bounds apply. Input interpretation is full scan.
Conversion/layout tables are memory-resident under the process limit: excessive inputs
fail explicitly, with no promise of larger-than-memory conversion. All data files are
counted after each write; one active file, the validation concatenation and bounded SQLite
scratch can temporarily add overhead. This is not a filesystem-wide disk quota.

Use a private local filesystem and trusted root. There is no network namespace, syscall
sandbox, authenticated tenant enforcement or MinIO publication in this local CLI. S06
implements benchmark isolation; S09 connects authenticated assessment orchestration and
object storage. No cloud performance, price, customer, production or paid-service claim
follows from these runs.
