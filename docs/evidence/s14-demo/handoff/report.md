# Data Optimizer engineering handoff

Schema: s12.1
Bundle: 1ad11c8167cd38b806ad7275a3306e71290207649c1f719e6ec03203fed924e9
Original report: e9e4e90b950fdb9b0ebd219daa7ef321d991340ffcd0fc877ddcefabf34edd2a

## Decision and requirements

Outcome: change
Selected candidate: 50d6131c3ee0e43c7047b8389b2fb05af0df494684b9cc6afb27bbd0ce845626
Reason: Best tested feasible cost including migration meets the materiality threshold.
Evidence: local\_assessment
Search stopped: trial\_budget

The JSON bundle contains the executable requirements, tested candidate configurations, workload, raw trials, integrity checks, environment and price snapshots. Nested fingerprints identify the original evidence; see export redactions.

## Profile coverage

Rows: 3; profiled: 3; fraction: 1.0; sampling: full\_scan; input physical bytes: 287.

## Reproducibility references

Input fingerprint: 01974a491f9de8f7d8790b4f999fef94b6219cd7c6246f971f1e6d6598ab1167
Workload fingerprint: 16fa40eb42d1cbcd624b66d310c6ee750558bcd76281787ef818b73c82de4a90
Environment fingerprint: eee1df845901db1a7e07982446133f28b9681a86995e3db6239b5d403c2c8a3e
Raw benchmark reference: 4f9babe2921b66e3884f55d200ed952c9128800174942509763d3ef28285676a
Timed repeats requested: 3; benchmark stopped: completed.

- boundary: docker\_cgroup\_v2\_network\_none\_readonly\_tmpfs
- cpu\_model: 12th Gen Intel\(R\) Core\(TM\) i7-12650H
- cpu\_scope: process\_cpu\_for\_timed\_load\_and\_queries
- disk\_scope: bounded\_tmpfs\_scratch\_plus\_1MiB\_shm\_and\_docker\_dev\_tmpfs
- docker\_version: 29.1.3
- host\_kernel: 7.0.0-28-generic
- host\_machine: x86\_64
- image\_id: sha256:5d00b2278a6c82a80df028b95643e6e63f8de2c4b4d14ef3133a7560b6a96e00
- measurement: typed\_full\_read\_load\_then\_in\_memory\_queries\_no\_native\_pushdown
- os\_cache: uncontrolled\_and\_pre\_read\_by\_integrity\_hashing
- rss\_scope: linux\_process\_high\_water\_includes\_imports\_validation\_warmups
- worker\_arrow\_cpp: 26.0.0
- worker\_arrow\_worker\_memory\_pool: system
- worker\_canonical: s04.1
- worker\_cpu.max: 100000 100000
- worker\_duckdb: 1.5.6
- worker\_kernel: 7.0.0-28-generic
- worker\_memory.max: 1073741824
- worker\_memory.swap.max: 0
- worker\_pids.max: 64
- worker\_pyarrow: 26.0.0
- worker\_python: 3.12.3
- worker\_zlib: 1.2.13

## Tested candidates and costs

All amounts below are copied from the stored calculations. Unknown is not zero.

### ndjson / original

Candidate: 32703e71e3d572a07a1eac2c3f606ce33d51c30abbf22a3a46b39612ae29fd7b; baseline: True; feasibility: feasible.
Observed local load + workload seconds: 0.014436797999223927.
Horizon total including migration: 344.400000.
Target file bytes: 67108864; row-group rows: 65536; partition columns: None; sort columns: None.

- semantics: passed; Exact content, multiplicity and declared semantics checks.
- reader\_compatibility: passed; Compared against explicitly allowed formats/codecs.
- workload: passed; Requires actual validated query results.
- concurrency: passed; Runner tests one process only; unknown/production scope is unvalidated.
- freshness: not\_required; No refresh pipeline is benchmarked.
- benchmark: passed; All requested repeats and query result hashes must pass.
- latency:scan: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:ids: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:filter: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:nulls: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:time: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:groups: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- retention: not\_required; Declared equivalent retained-copy lifetime, not operational retention validation.
- cost: passed; Complete horizon operating cost plus once-only migration; baseline migration is zero.
- migration\_budget: not\_required; Once-only modeled migration total compared to the supplied budget.

Scenario: synthetic\_storage\_demo; currency: USD; price snapshot: 8949b0f5e02f00655e4530a4c87321db490bc39d940d7c9c1d3454a3d8678557.
Baseline monthly: 28.700000; one-time migration: 0 (retain baseline). Savings, payback and migration peak are not applicable to keeping current.

| Scope | Component | Quantity | Unit | Rate | Amount | Missing |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | storage | 2.87E-7 | GB\_month | 100000000 | 28.700000 | None |
| baseline | query\_compute | 0.004010221666 | compute\_hour | 0 | 0.000000 | None |
| baseline | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| baseline | read\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | write\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | retrieval | 0 | GB | 0 | 0.000000 | None |
| baseline | network | 0 | GB | 0 | 0.000000 | None |
| baseline | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | maintenance | 0 | hour | 0 | 0.000000 | None |
| baseline | service | 0 | month | 0 | 0.000000 | None |

### ndjson / gzip

Candidate: 50d6131c3ee0e43c7047b8389b2fb05af0df494684b9cc6afb27bbd0ce845626; baseline: False; feasibility: feasible.
Observed local load + workload seconds: 0.015220528999634553.
Horizon total including migration: 165.600000.
Target file bytes: 67108864; row-group rows: 65536; partition columns: None; sort columns: None.

- semantics: passed; Exact content, multiplicity and declared semantics checks.
- reader\_compatibility: passed; Compared against explicitly allowed formats/codecs.
- workload: passed; Requires actual validated query results.
- concurrency: passed; Runner tests one process only; unknown/production scope is unvalidated.
- freshness: not\_required; No refresh pipeline is benchmarked.
- benchmark: passed; All requested repeats and query result hashes must pass.
- latency:scan: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:ids: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:filter: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:nulls: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:time: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:groups: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- retention: not\_required; Declared equivalent retained-copy lifetime, not operational retention validation.
- cost: passed; Complete horizon operating cost plus once-only migration; baseline migration is zero.
- migration\_budget: not\_required; Once-only modeled migration total compared to the supplied budget.

Scenario: synthetic\_storage\_demo; currency: USD; price snapshot: 8949b0f5e02f00655e4530a4c87321db490bc39d940d7c9c1d3454a3d8678557.
Baseline monthly: 28.700000; candidate monthly: 13.800000; One-time migration forecast: 0.000000.
Monthly savings: 14.900000; horizon net savings: 178.800000; payback months: 0E-12.
Peak migration bytes (baseline + candidate + extra scratch): 425.

| Scope | Component | Quantity | Unit | Rate | Amount | Missing |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | storage | 2.87E-7 | GB\_month | 100000000 | 28.700000 | None |
| baseline | query\_compute | 0.004010221666 | compute\_hour | 0 | 0.000000 | None |
| baseline | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| baseline | read\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | write\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | retrieval | 0 | GB | 0 | 0.000000 | None |
| baseline | network | 0 | GB | 0 | 0.000000 | None |
| baseline | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | maintenance | 0 | hour | 0 | 0.000000 | None |
| baseline | service | 0 | month | 0 | 0.000000 | None |
| candidate | storage | 1.38E-7 | GB\_month | 100000000 | 13.800000 | None |
| candidate | query\_compute | 0.004227924722 | compute\_hour | 0 | 0.000000 | None |
| candidate | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| candidate | read\_requests | 0 | request | 0 | 0.000000 | None |
| candidate | write\_requests | 0 | request | 0 | 0.000000 | None |
| candidate | retrieval | 0 | GB | 0 | 0.000000 | None |
| candidate | network | 0 | GB | 0 | 0.000000 | None |
| candidate | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| candidate | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| candidate | maintenance | 0 | hour | 0 | 0.000000 | None |
| candidate | service | 0 | month | 0 | 0.000000 | None |
| migration\_forecast | conversion | 0.000071971389 | compute\_hour | 0 | 0.000000 | None |
| migration\_forecast | temporary\_storage | 0 | GB\_month | 100000000 | 0.000000 | None |
| migration\_forecast | transfer | 0 | GB | 0 | 0.000000 | None |
| migration\_forecast | labor | 0 | hour | 0 | 0.000000 | None |
| migration\_forecast | rollback | 0 | hour | 0 | 0.000000 | None |

### parquet / zstd

Candidate: 5ef4384e0f306a1d72b78143ce94ca0a01cb038b46c102395197244ec06f88a6; baseline: False; feasibility: feasible.
Observed local load + workload seconds: 0.03523815199514502.
Horizon total including migration: 1911.600000.
Target file bytes: 67108864; row-group rows: 16384; partition columns: None; sort columns: None.

- semantics: passed; Exact content, multiplicity and declared semantics checks.
- reader\_compatibility: passed; Compared against explicitly allowed formats/codecs.
- workload: passed; Requires actual validated query results.
- concurrency: passed; Runner tests one process only; unknown/production scope is unvalidated.
- freshness: not\_required; No refresh pipeline is benchmarked.
- benchmark: passed; All requested repeats and query result hashes must pass.
- latency:scan: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:ids: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:filter: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:nulls: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:time: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:groups: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- retention: not\_required; Declared equivalent retained-copy lifetime, not operational retention validation.
- cost: passed; Complete horizon operating cost plus once-only migration; baseline migration is zero.
- migration\_budget: not\_required; Once-only modeled migration total compared to the supplied budget.

Scenario: synthetic\_storage\_demo; currency: USD; price snapshot: 8949b0f5e02f00655e4530a4c87321db490bc39d940d7c9c1d3454a3d8678557.
Baseline monthly: 28.700000; candidate monthly: 159.300000; One-time migration forecast: 0.000000.
Monthly savings: -130.600000; horizon net savings: -1567.200000; payback months: Unknown.
Peak migration bytes (baseline + candidate + extra scratch): 1880.

| Scope | Component | Quantity | Unit | Rate | Amount | Missing |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | storage | 2.87E-7 | GB\_month | 100000000 | 28.700000 | None |
| baseline | query\_compute | 0.004010221666 | compute\_hour | 0 | 0.000000 | None |
| baseline | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| baseline | read\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | write\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | retrieval | 0 | GB | 0 | 0.000000 | None |
| baseline | network | 0 | GB | 0 | 0.000000 | None |
| baseline | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | maintenance | 0 | hour | 0 | 0.000000 | None |
| baseline | service | 0 | month | 0 | 0.000000 | None |
| candidate | storage | 0.000001593 | GB\_month | 100000000 | 159.300000 | None |
| candidate | query\_compute | 0.009788375554 | compute\_hour | 0 | 0.000000 | None |
| candidate | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| candidate | read\_requests | 0 | request | 0 | 0.000000 | None |
| candidate | write\_requests | 0 | request | 0 | 0.000000 | None |
| candidate | retrieval | 0 | GB | 0 | 0.000000 | None |
| candidate | network | 0 | GB | 0 | 0.000000 | None |
| candidate | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| candidate | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| candidate | maintenance | 0 | hour | 0 | 0.000000 | None |
| candidate | service | 0 | month | 0 | 0.000000 | None |
| migration\_forecast | conversion | 0.000078645556 | compute\_hour | 0 | 0.000000 | None |
| migration\_forecast | temporary\_storage | 0 | GB\_month | 100000000 | 0.000000 | None |
| migration\_forecast | transfer | 0 | GB | 0 | 0.000000 | None |
| migration\_forecast | labor | 0 | hour | 0 | 0.000000 | None |
| migration\_forecast | rollback | 0 | hour | 0 | 0.000000 | None |

### parquet / snappy

Candidate: 72713fa4dde4227c6446c8d6710b234a9efbe574ed65052926781672c0fc2ad9; baseline: False; feasibility: feasible.
Observed local load + workload seconds: 0.031737396002426976.
Horizon total including migration: 1827.600000.
Target file bytes: 67108864; row-group rows: 65536; partition columns: None; sort columns: None.

- semantics: passed; Exact content, multiplicity and declared semantics checks.
- reader\_compatibility: passed; Compared against explicitly allowed formats/codecs.
- workload: passed; Requires actual validated query results.
- concurrency: passed; Runner tests one process only; unknown/production scope is unvalidated.
- freshness: not\_required; No refresh pipeline is benchmarked.
- benchmark: passed; All requested repeats and query result hashes must pass.
- latency:scan: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:ids: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:filter: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:nulls: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:time: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:groups: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- retention: not\_required; Declared equivalent retained-copy lifetime, not operational retention validation.
- cost: passed; Complete horizon operating cost plus once-only migration; baseline migration is zero.
- migration\_budget: not\_required; Once-only modeled migration total compared to the supplied budget.

Scenario: synthetic\_storage\_demo; currency: USD; price snapshot: 8949b0f5e02f00655e4530a4c87321db490bc39d940d7c9c1d3454a3d8678557.
Baseline monthly: 28.700000; candidate monthly: 152.300000; One-time migration forecast: 0.000000.
Monthly savings: -123.600000; horizon net savings: -1483.200000; payback months: Unknown.
Peak migration bytes (baseline + candidate + extra scratch): 1810.

| Scope | Component | Quantity | Unit | Rate | Amount | Missing |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | storage | 2.87E-7 | GB\_month | 100000000 | 28.700000 | None |
| baseline | query\_compute | 0.004010221666 | compute\_hour | 0 | 0.000000 | None |
| baseline | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| baseline | read\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | write\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | retrieval | 0 | GB | 0 | 0.000000 | None |
| baseline | network | 0 | GB | 0 | 0.000000 | None |
| baseline | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | maintenance | 0 | hour | 0 | 0.000000 | None |
| baseline | service | 0 | month | 0 | 0.000000 | None |
| candidate | storage | 0.000001523 | GB\_month | 100000000 | 152.300000 | None |
| candidate | query\_compute | 0.008815943334 | compute\_hour | 0 | 0.000000 | None |
| candidate | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| candidate | read\_requests | 0 | request | 0 | 0.000000 | None |
| candidate | write\_requests | 0 | request | 0 | 0.000000 | None |
| candidate | retrieval | 0 | GB | 0 | 0.000000 | None |
| candidate | network | 0 | GB | 0 | 0.000000 | None |
| candidate | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| candidate | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| candidate | maintenance | 0 | hour | 0 | 0.000000 | None |
| candidate | service | 0 | month | 0 | 0.000000 | None |
| migration\_forecast | conversion | 0.000068399722 | compute\_hour | 0 | 0.000000 | None |
| migration\_forecast | temporary\_storage | 0 | GB\_month | 100000000 | 0.000000 | None |
| migration\_forecast | transfer | 0 | GB | 0 | 0.000000 | None |
| migration\_forecast | labor | 0 | hour | 0 | 0.000000 | None |
| migration\_forecast | rollback | 0 | hour | 0 | 0.000000 | None |

### parquet / zstd

Candidate: c1de41ba993f1ad3d482a577e36538d0e9ab99704e51470380eecbe83ebcc7c2; baseline: False; feasibility: feasible.
Observed local load + workload seconds: 0.028414942000381416.
Horizon total including migration: 1911.600000.
Target file bytes: 67108864; row-group rows: 65536; partition columns: None; sort columns: timestamp.

- semantics: passed; Exact content, multiplicity and declared semantics checks.
- reader\_compatibility: passed; Compared against explicitly allowed formats/codecs.
- workload: passed; Requires actual validated query results.
- concurrency: passed; Runner tests one process only; unknown/production scope is unvalidated.
- freshness: not\_required; No refresh pipeline is benchmarked.
- benchmark: passed; All requested repeats and query result hashes must pass.
- latency:scan: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:ids: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:filter: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:nulls: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:time: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- latency:groups: not\_required; Observed maximum of query-only seconds; excludes load/startup, no tail guarantee.
- retention: not\_required; Declared equivalent retained-copy lifetime, not operational retention validation.
- cost: passed; Complete horizon operating cost plus once-only migration; baseline migration is zero.
- migration\_budget: not\_required; Once-only modeled migration total compared to the supplied budget.

Scenario: synthetic\_storage\_demo; currency: USD; price snapshot: 8949b0f5e02f00655e4530a4c87321db490bc39d940d7c9c1d3454a3d8678557.
Baseline monthly: 28.700000; candidate monthly: 159.300000; One-time migration forecast: 0.000000.
Monthly savings: -130.600000; horizon net savings: -1567.200000; payback months: Unknown.
Peak migration bytes (baseline + candidate + extra scratch): 1880.

| Scope | Component | Quantity | Unit | Rate | Amount | Missing |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | storage | 2.87E-7 | GB\_month | 100000000 | 28.700000 | None |
| baseline | query\_compute | 0.004010221666 | compute\_hour | 0 | 0.000000 | None |
| baseline | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| baseline | read\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | write\_requests | 0 | request | 0 | 0.000000 | None |
| baseline | retrieval | 0 | GB | 0 | 0.000000 | None |
| baseline | network | 0 | GB | 0 | 0.000000 | None |
| baseline | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| baseline | maintenance | 0 | hour | 0 | 0.000000 | None |
| baseline | service | 0 | month | 0 | 0.000000 | None |
| candidate | storage | 0.000001593 | GB\_month | 100000000 | 159.300000 | None |
| candidate | query\_compute | 0.007893039445 | compute\_hour | 0 | 0.000000 | None |
| candidate | transform\_compute | 0 | compute\_hour | 0 | 0.000000 | None |
| candidate | read\_requests | 0 | request | 0 | 0.000000 | None |
| candidate | write\_requests | 0 | request | 0 | 0.000000 | None |
| candidate | retrieval | 0 | GB | 0 | 0.000000 | None |
| candidate | network | 0 | GB | 0 | 0.000000 | None |
| candidate | backups | 0 | GB\_month | 100000000 | 0.000000 | None |
| candidate | replicas | 0 | GB\_month | 100000000 | 0.000000 | None |
| candidate | maintenance | 0 | hour | 0 | 0.000000 | None |
| candidate | service | 0 | month | 0 | 0.000000 | None |
| migration\_forecast | conversion | 0.000090071944 | compute\_hour | 0 | 0.000000 | None |
| migration\_forecast | temporary\_storage | 0 | GB\_month | 100000000 | 0.000000 | None |
| migration\_forecast | transfer | 0 | GB | 0 | 0.000000 | None |
| migration\_forecast | labor | 0 | hour | 0 | 0.000000 | None |
| migration\_forecast | rollback | 0 | hour | 0 | 0.000000 | None |

## Price provenance

- synthetic\_storage\_demo: synthetic prices; synthetic-offline-example / synthetic-local / USD; effective 2026-11-02T00:00:00+00:00; retrieved 2026-11-02T00:00:00+00:00. Rates, units, minimums and discounts are in bundle.json. Synthetic means invented, never a provider quote.

## Prerequisites and deliberate migration

Use Python 3.12, this project's locked package and matching PyArrow/DuckDB versions.
Full assessment reproduction additionally requires Linux Docker/cgroup v2 and the recorded
immutable benchmark image (build locally with `make benchmark-image` in the matching checkout).
Use a private local source copy and a new empty workspace. Preserve the original source,
its fingerprint, all retained copies and a backup of the prior reader configuration.
Required reader support: Use the selected configuration and manifest reader in bundle.json, including codec, exact schema, ordered parts, partition and sort settings. Never switch a transactional database on this evidence.
Check target reader support for decimals, null/missing fields, timestamps and codecs.
Budget peak space using the cost section; Unknown requires a separate estimate before migration.
Local output needs room for baseline plus all tested alternatives during assessment reproduction.

After extracting all files together, reproduce the full assessment:

```sh
data-optimizer reproduce ./bundle.json --source '/path/to/local source' \
  --root /tmp/new-assessment --output /tmp/new-reproduction.json
```

Paths above are placeholders: supply your private source and new destinations as quoted arguments.
The command checks the input digest and engine versions before running, compares the outcome and
selected configuration, and records disagreement explicitly. Timing variation is expected.
For metadata-only/startup guidance no raw-data reproduction or migration is authorized by evidence.
For keep_current retain the current reader; for insufficient_evidence answer the missing questions.

Only for a tested change, create and validate a local candidate copy:

```sh
sh ./migrate.sh '/path/to/local source' /tmp/new-migration /tmp/new-migration-result.json
```

The script uses fixed package commands and positional arguments, never dataset/AI shell content.
Read the resulting manifest: it records the exact configuration, schema/reader, output files,
physical bytes and full semantic integrity evidence. Every canonical-content/multiplicity and
workload-result check must pass. The source remains unchanged. No reader is switched automatically.

## Canary and rollback

1. Save the prior reader configuration and original SHA-256; keep source and backup accessible.
2. Run the bundle's complete constrained workload against the new manifest parts. Local conversion
   already checks these results against the source, including declared tolerances and duplicates.
3. Before any real switch, replay representative queries in the actual target reader/environment;
   compare counts, null/missing semantics, decimals, timestamps and results. Measure that reader's
   latency/concurrency against your requirements; local worker timings cannot substitute for this.
4. A human may then direct a limited canary to the copy, retaining the previous reader configuration
   and source. Stop on any result/schema mismatch, missing part, integrity failure, unacceptable
   latency, higher cost, retention violation or unsupported reader behavior.
5. On a trigger, stop directing new canary reads to the copy. Restore the saved prior reader
   configuration pointing at the retained original; verify the original SHA-256 and rerun the same
   workload on it. Confirm normal reads and record the failed candidate/evidence IDs for review.
   Keep both copies for investigation and meet existing retention rules. These instructions perform
   no automatic deletion, production mutation, external transfer or source cleanup.


## Coverage and limitations

- Measurements cover only the supplied input on the recorded local worker. Profile sampling does not establish full-dataset performance; metadata-only/startup guidance has no measured migration recommendation or historical savings.
- Typed load plus in-memory queries; OS cache uncontrolled. Native scans, cloud latency, concurrency, throughput and production tail latency remain unvalidated.
- Costs are forecasts, not invoices or realized savings. Synthetic prices are invented; user-supplied prices are unverified. Missing amounts remain Unknown. Fixed capacity must actually change to yield cash savings.
- Supported tariffs are flat linear rates with recorded minimums. Tier/free allowances, tax, FX, calendar proration, nonlinear growth and mixed-region allocation are unsupported.
- Search is bounded and may stop early; best tested feasible does not imply global optimality. Rerun timings and timing-based costs or decisions can differ; inspect any disagreement.
- Best tested feasible option within bounded coverage; no global optimality claim.
- Local typed load and in-memory queries; no native scans, cloud, concurrency or tail SLA proof.
- Costs are forecasts from explicit assumptions and price snapshots; synthetic rates stay synthetic.
- Retention/copies are declared cost assumptions, not a deployed durability guarantee.
- Observed maxima and ranges describe these repeats, not population confidence intervals.

## Privacy and evidence references

- Business descriptions, AI summaries, source notes/references, price narrative and paths are omitted. Schema/workload parameters remain necessary and may be sensitive.
- Nested evidence fingerprints reference the original records before narrative redaction. The bundle fingerprint covers the exported content; it is not a signature.
