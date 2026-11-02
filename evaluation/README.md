# S14 held-out evaluation

Run `make benchmark-image`, then `make evaluate`. `heldout.py` generates whole datasets
in private temporary storage. None are imported by production code, optimizer logic or
earlier tuning fixtures. The generator and synthetic objective were fixed before the first
run; results do not tune the heuristic. No learned model is trained.

Cases: repeated categorical events, unique SHA-256 strings, nested records, missing/null
schema drift, one-record input, dictionary/Zstandard Parquet, and duplicate-key malformed
NDJSON. Every valid case gets independent exhaustive (four proposed configurations) and
adaptive (three-trial budget) real assessments. Unsupported candidates retain explicit
exclusions. Nested/drift inputs must abstain on unsupported workload evidence. The malformed
input must fail with a stable parser reason. Both source fingerprints and all raw reports
are recorded under `docs/evidence/s14-evaluation/`; raw files/workspaces are deleted.

Gates: report hashes, every selected candidate's integrity and complete constraint coverage,
row multiplicity, all timed repeats, independent Decimal line reconciliation, bounded search
coverage, source preservation and fail-closed incompatible reader requirements. Record
actual cost regret versus the best feasible exhaustive candidate, including nonzero regret;
there is no zero-regret gate or global-optimality claim. The objective deliberately uses
amplified invented storage prices and zero non-storage rates to isolate representation
effects; regret is **synthetic currency**, not production opportunity cost.

`make calibrate` separately measures a 4096-row, 32-query, five-repeat, four-configuration
workload; verifies query/repeat caps and actual impossible-latency abstention. Upload and
backup drills live in `backend/tests/integration/test_release_readiness.py`. These establish
specific envelopes, not worst-case capacity. Tail latency, cold OS cache, native Parquet
scans, cloud performance and concurrent production workloads remain unverified.
