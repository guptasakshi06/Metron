# Data Optimizer local MVP release

S01–S14 implement the local analytical-file product. The release decision is **ready for
the documented local demonstration and bounded local evaluation**. Production deployment,
external identity/provider integration and customer/pilot validation require separate work.
Use the [clean-start instructions and release checklist](runbooks/local-release.md),
[user guide](user-flow.md) and [administrator/backup guide](runbooks/administration.md).

## Delivered capability

CSV, NDJSON/gzip and Parquet assessment copies; conservative typed privacy profiles;
reviewed metadata-only import; constrained analytical workloads; exact semantic and
multiplicity integrity; baseline plus eligible lossless alternatives; bounded local Docker
measurements; immutable synthetic/user-supplied price snapshots and reconciled economics;
best-tested-feasible change/keep/insufficient decisions; durable owned async assessments,
retry/cancellation/expiry cleanup; actual dashboard; optional no-key structured assistance;
owned expiring JSON/Markdown/HTML/ZIP exports, safe local-copy migration and reproducibility;
manual adoption/observation revisions and deliberately separate modeled attribution.

Unknowns stay unknown. No transactional replacement, source deletion or reader switch runs.
The optional LLM cannot change authoritative metrics or execute proposed commands. Manual
observations remain user supplied, and adjusted savings remain modeled counterfactuals.
History/comparison access currently expires with the original assessment/input retention.

## Held-out release evaluation

Seven generated whole datasets are separate from earlier tuning/test datasets. The final
categorical fixture includes 384 distinct events, each occurring twice. No model training
or optimizer tuning used these results. Actual raw reports, dataset fingerprints, runtime,
CPU/RSS, exclusions and search coverage are under
[S14 evaluation evidence](evidence/s14-evaluation/results.json).

| Case | Exhaustive decision | Coverage |
| --- | --- | --- |
| Categorical events with legitimate duplicates | change | Four proposed/tested configurations, two repeats |
| High-cardinality unique strings | change | Four proposed/tested configurations, two repeats |
| Nested records | insufficient_evidence | Two eligible proposals attempted; workload unsupported, no timed pass |
| Missing/null schema drift | insufficient_evidence | Parquet excluded for presence semantics; no timed pass |
| One-record file | keep_current | Four proposed/tested configurations, two repeats |
| Dictionary/Zstd Parquet | keep_current | Four proposed/tested configurations, two repeats |
| Duplicate-key malformed JSON | rejected | Stable `duplicate_json_key` reason |

Every selected option passes integrity, full requested repeats and required coverage, with
zero selected constraint violations. Costs reconcile independently to Decimal line items.
An incompatible reader policy abstains. Independent three-trial adaptive search has
3400.800000 **synthetic currency units** of horizon-cost regret on the high-cardinality
fixture and zero on other comparable cases. Unknown/unsupported cases have null regret.
There is no universal zero-regret guarantee or global optimum claim. The deliberately
amplified invented storage tariff and zero non-storage rates isolate representation effects;
these are not provider rates, real savings or quality estimates for production workloads.

## Measured operational envelope

Recorded hardware: Intel i7-12650H, 16 logical CPUs, about 23.1 GiB RAM, Linux
7.0.0-28-generic x86_64; Python 3.12.3, Node 24.22.2/npm 11.19.1, uv 0.13.6,
Arrow 26.0.0, DuckDB 1.5.6, Docker 29.1.3, PostgreSQL 17.11 and local source-built MinIO.
Other local workloads were present; these observations are not isolated hardware SLAs.

| Path | Verified local envelope | Meaning and limit |
| --- | --- | --- |
| Upload/validate/download | 1 and 16 MiB NDJSON, 4096/65536 fixed-width records | Actual ASGI API + PostgreSQL/MinIO + bounded validator; hashes match. 16 MiB + 1 rejected with HTTP 413 at that configured cap. No network throughput/full-assessment claim. |
| Profile | 12,360,000 bytes / 60,000 rows, 256 sampled rows | Completed in 1.599 s with 1024 MiB address-space policy; two scans. Not full workload measurement. |
| Low-memory profile | 168,414,208-byte valid input, 128 MiB policy | Clear `profile_memory_quota` in 0.253 s; no supported-above-memory execution claim. |
| Complete assessment | 1,043,370 bytes / 4096 rows; 32 grouped queries; four configurations × five repeats | 20 passing trials; 105.302 s through full assessment, peak trial RSS 118304 KiB. Typed materialization/in-memory queries. |
| Workload boundaries | 33 queries or six repeats rejected; measured impossible 1e-12 s query bound abstains | No violated configuration selected. This is not an observed production tail guarantee. |
| Sandbox | 1 CPU, 1024 MiB/no swap, 64 MiB tmpfs, CPU/wall/output bounds | Real network/file/engine restrictions, cancellation and resource-failure tests pass. |

See [upload observations](evidence/s14-upload-capacity.json),
[profile observations](evidence/s14-profile-resources.json) and
[workload observations](evidence/s14-capacity/workload-results.json).
For a conservative local full-assessment demo, begin within the measured 4096-row/~1 MiB
categorical envelope with bounded outputs and one assessment per tenant. The 16 MiB upload
envelope does not establish assessment capacity. The configured 256 MiB raw/1 GiB decoded
caps, wider records, maximum candidate spaces and worst-case workloads are uncalibrated.
No production concurrency, native Parquet pushdown, cold OS-cache, p95/p99, cloud latency,
object-store throughput or universal CPU/memory capacity is asserted. Workspace quotas are
monitored, not filesystem-enforced.

## Recovery and release gates

The [verification record](evidence/s14-verification.md) records exact commands and results.
Release checks cover unit/type/lint/build, real service ownership/grants/expiration,
worker SIGKILL recovery with published trial reuse, active cancellation, Docker isolation,
browser totals/refresh/metadata/export/observation/reassessment, log redaction, local
backup restore and clean dependency-directory install/demo/reproduction.

Metadata backup restores to a fresh temporary database and preserves all eight migration
checksums, exact result/bundle/history bytes, ownership and immutable triggers. A missing
test result object returns a sanitized 503 and recovers when the object is restored.
The drill retains the original object bucket; independent object-store disaster restore,
power loss, multi-host failover and exactly-once execution before durable publication are
unverified. See [backup evidence](evidence/s14-backup-restore.json).

## Remaining external validation

- Real customer interviews, representative private datasets and observed migration outcomes.
- Actual bills, prices, contract discounts and willingness to pay; no claimed customer savings.
- External IdP/login/refresh/key rotation, production TLS/secrets/network/socket isolation.
- Live optional AI model/schema/account/billing/retention behavior; current live smoke is `not_run`.
- Production object-store lifecycle, encrypted coordinated backups and actual target-reader
  canary/rollback; broader capacity, cloud/native scans and concurrent/tail performance.
- Hosted GitHub Actions execution; only the local fresh-dependency rehearsal is verified.
- Long-term metadata-only observation history after raw-copy expiry; current retention gate remains.

Known local warnings: Starlette/httpx TestClient deprecation, Node color warning and favicon
404 in browser requests. Keyboard and desktop/narrow checks cover Chrome only; no complete
screen-reader/cross-browser audit. None imply provider/customer/production validation.
The [final handoff](../SPRINT_HANDOFF.md) is canonical. Stop before post-MVP work.
