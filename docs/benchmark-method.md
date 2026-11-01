# S06 local benchmark method

The `s06.1` runner measures the existing typed read/load and constrained DuckDB workload
path against verified S05 artifacts. It produces local evidence, not recommendations,
cloud predictions or savings. Linux Docker with cgroup v2 is required; unavailable controls
fail closed. No cloud service or API key is needed.

## Run and reproduce

From the repository root after locked setup:

```bash
export PATH="$PWD/.tools/node24/bin:$PWD/.tools/uv-bin:$PATH"
make benchmark-image
uv run --locked --project backend data-optimizer convert \
  examples/s04-events.ndjson --request examples/s05-conversion-request.json \
  --root /tmp/data-optimizer-s06-artifacts > /tmp/s06-conversions.json
```

Choose the `artifact_prefix` directories from validated/reused outcomes in that JSON,
including exactly one baseline. Pass those directories explicitly:

```bash
uv run --locked --project backend data-optimizer benchmark \
  /tmp/data-optimizer-s06-artifacts/TENANT/assessments/ASSESSMENT/BASELINE_KEY \
  /tmp/data-optimizer-s06-artifacts/TENANT/assessments/ASSESSMENT/CANDIDATE_KEY \
  --request examples/s06-benchmark-request.json --output /tmp/s06-report.json
```

Use actual returned paths in place of the uppercase placeholders. Existing output paths
are never overwritten. Reports cannot be written inside an input artifact directory.
Exit 0 means all requested trials passed; 1 means the saved report contains failed/stopped
trials; 2 means invalid setup/input/output or unavailable Docker; Ctrl-C exits 130 after
handled cleanup. The Python service also accepts a cancellation callback and preserves
partial observations with remaining trials marked cancelled or budget_exhausted.

The complete reproducible CLI exercise selects baseline/gzip/Snappy/Zstandard automatically:

```bash
make build
uv run --locked --project backend python scripts/verify-s06.py --output-dir /tmp/s06-evidence
make test-benchmark
```

This runs the extracted wheel from a separate working directory, executes fresh and warm
matrices and records actual wall/CPU/memory/output/cancellation probes. Raw fixture records
are excluded from reports, although schemas, query parameters, counts and hashes can still
be sensitive. UUID prefixes organize local artifacts; they do not authenticate a tenant.

## Comparable execution and cache conditions

All candidates must have the same input fingerprint, complete conversion request and
workload fingerprint. Duplicate candidates or a missing baseline are rejected. Invalid
manifests, missing workloads and corrupt artifacts produce explicit integrity failures.
The runner checks manifest/report fingerprints and file hashes, then copies only named
parts into a private, size-bounded snapshot. Snapshot hashes are checked again by the
worker. No original dataset root or other assessment is mounted.

Each trial uses a new container and the same immutable image ID and resource settings.
The seeded schedule shuffles candidates within each repeat round. Defaults are 3 repeats
(maximum 5), seed 0 (example uses 42), up to 12 candidates, 60 trials and 600 assessment
seconds. Unexecuted trials have explicit stop reasons; failed trials have no observations.
Summaries include successful observations only and never replace missing measurements
with zero. Consumers must inspect failures/coverage before assessing feasibility.

`warmups=0` reports `fresh_process_os_cache_uncontrolled`. Imports, file hash verification
and container startup precede the measured load/query interval. Hash verification itself
reads the files, so fresh-process does **not** mean cold filesystem cache.
With `warmups=1` or `2`, complete untimed load/query replays run in the same process before
the measured replay; reports say `warm_process_os_cache_uncontrolled`. Each replay creates
a new in-memory database. No host cache dropping, eviction or genuine cold-cache procedure
is implemented. Warm-ups count toward CPU, memory, wall time and peak RSS.

The worker reads every manifest part in order using the existing bounded S03 readers,
then inserts typed rows into S04's fixed relation in batches of 128. One decoded-byte and
row budget covers all parts. The shared loader preserves the same integrity semantics;
multi-part outputs are not concatenated or rewritten for timing. The existing DSL alone
compiles queries, and each replay must reproduce this candidate's stored query-result
fingerprints (including candidate results previously compared with tolerance).

This is a **full typed load followed by in-memory queries**. It does not use DuckDB native
file scanning, Parquet projection/partition pruning or a persistent warm query server.
Query-only latency cannot justify a claim that a file representation has faster native
scans. Later ranking must use these measurements only for this import-and-query execution
model, or request further evidence for another model. No format-wide or production
performance winner follows from these tiny fixtures.

## Enforced boundary

| Control | Actual setting |
| --- | --- |
| CPU | cgroup quota, default 1 CPU; RLIMIT_CPU 30/31 soft/hard seconds |
| Memory | cgroup 1024 MiB, memory+swap equal memory (swap disabled) |
| Wall | parent deadline 45 seconds after create; worker kernel alarm as fallback |
| Processes/files | pids 64, nofile 128, core 0; no new privileges, all capabilities dropped |
| Filesystem | read-only image and one read-only snapshot; unprivileged UID/GID 65534 |
| Writable scratch | `/tmp` tmpfs, 64 MiB, noexec/nosuid/nodev; matching per-file limit |
| Other runtime mounts | 1 MiB `/dev/shm`; Docker's ordinary device tmpfs/proc/sys mounts |
| Output | continuously drained combined stdout/stderr cap 1 MiB; Docker log driver none |
| Network | separate network namespace, `--network none`; no Docker socket |
| Engine | external access/extensions disabled, one thread, no spill, configuration locked |

The worker checks effective cgroup v2 memory, swap, CPU and pids limits and the loopback-only
network before measuring. Parent orchestration never executes dataset text, SQL or shell
commands. Kernel/engine controls are layered: see [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/),
[tmpfs limits](https://docs.docker.com/engine/storage/tmpfs/) and
[DuckDB configuration](https://duckdb.org/docs/1.5/configuration/overview).

Default input staging is at most 512 MiB total data plus at most twelve 4 MiB manifests;
it occurs in parent-owned temporary storage, outside container scratch. The source limits
and integrity row/result limits stored in the manifests also apply. Docker control calls
have a separate 15-second timeout; startup/removal can add bounded orchestration overhead
to trial or assessment deadlines. There is no claim of exclusive CPUs, controlled CPU
frequency, host disk I/O bandwidth, hypervisor isolation or stable latency under host load.

Normal completion, failure, timeout, callback cancellation and Ctrl-C remove the uniquely
named container and private snapshots. If the parent is killed or Docker is unavailable,
cleanup is not guaranteed. The worker's alarm/CPU bound limits continued execution, but a
stopped container or parent snapshot can remain. Inspect only containers bearing
`data-optimizer.benchmark=true` and the matching `data-optimizer-benchmark-*` name before
deliberate cleanup. Crash recovery and worker admission belong to S09. Do not expose the
Docker socket to the web API; this local orchestrator requires a trusted worker host.

## Metrics and uncertainty

Every raw trial stores candidate key, repeat/ordinal, status/reason, exit/OOM evidence and
elapsed sandbox time. A passed observation contains load time (including DB setup), each
query's execute/fetch time and result hash/count, process CPU for the final replay including
result validation/DB close, and Linux process peak RSS including imports/verification/warmups.
The sum of query times is workload_seconds; load time is separate, and their sum is not
total container/orchestration time. Scanned physical bytes remain null with a reason because
the typed reader does not expose physical I/O. No fabricated I/O or energy metrics.

Full manifests preserve configuration/context, original/request/workload fingerprints,
passed integrity evidence, ordered part references/hashes, physical data bytes and the
earlier measured conversion/verification time and whole-conversion-worker CPU/RSS. Data
bytes exclude manifest/directory/filesystem overhead. Conversion was measured under S05's
process limits, not retrospectively under the benchmark container's cgroups.

Reports hash the complete request, environment and report. Environment records immutable
image ID, Docker/kernel/CPU model, engine versions and effective cgroups. Store the report
with the matching S05 artifacts and locked source/image to reproduce it. Timing values
vary: summaries show count, median, min/max and sample standard deviation. p95 stays null
with `unvalidated_requires_100_observations`; 3–5 measurements cannot validate tail latency.
Timeout, memory, CPU, disk/output, integrity, cancellation and budget failures are separate
outcomes. An ambiguous exit 137 without OOM evidence remains a failure with unknown cause.

See [S06 verification](evidence/s06-verification.md) and the raw JSON evidence for observed
values and limits. These are local synthetic fixture observations, not supported-capacity,
customer, cloud concurrency or production claims.
