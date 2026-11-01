# Decision 0005: bounded local candidates and verified atomic publication

Date: 2026-11-02 (Asia/Kolkata)

- Keep the selected PyArrow/DuckDB stack and lockfiles. Versioned configuration hashes
  cover format, codec/level, file target, row groups, partitions/sorts and fixed runtime
  context. Retain an exact baseline copy plus gzip NDJSON, Snappy and Zstandard Parquet.
- Reuse S04 capabilities as preliminary eligibility; require complete exact candidate
  integrity and every supplied query before publication. Missing workloads remain unknown,
  never performance passes. Exclude varying decimal scales for Parquet and reject any
  further semantic loss through actual integrity checks, including decimal negative zero.
- Generate a small enumeration, with workload-guided sort/group partition alternatives.
  Retain partition columns and use opaque directory names. Bound partition/file counts
  and minimum rows to control small-file amplification. File targets are estimates.
- Materialize local tenant/assessment prefixes for this offline sprint; S09 owns database,
  authenticated identity and MinIO integration. Local UUIDs are organization, not access control.
- Atomic directory rename publishes only closed, verified outputs and a versioned manifest.
  Reuse checks complete request/input/configuration/runtime identity and all data files.
  Per-key flock is inherited by the worker; same-key retries clean orphaned private scratch
  only after acquiring the lock. Failed/cancelled work never has a published complete prefix.
- Multi-file validation concatenates actual files in manifest order into private bounded
  scratch for the existing single-file S04 verifier. Remove the temporary concatenation
  after validation. Store hashes/sizes of all actual output parts and the full validation
  request/report. No inference of performance or network/cloud behavior.
- Record Linux process RSS/CPU and conversion/verification wall times honestly. Layouts
  use memory-resident tables under process limits; no larger-than-memory guarantee. OS
  network/disk isolation and benchmark methodology remain S06. No durable-power-loss or
  production multi-host publication claim.

Official writer and codec API references checked during implementation:

- [PyArrow ParquetWriter](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetWriter.html)
- [PyArrow Codec](https://arrow.apache.org/docs/python/generated/pyarrow.Codec.html)

See [candidate support](../candidate-support.md) for commands, bounds, compatibility and
artifact conventions. No new dependencies or paid services.
