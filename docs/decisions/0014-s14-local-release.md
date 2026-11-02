# Decision 0014: measured local release gates and bounded-worker allocator

Date: 2026-11-02 (Asia/Kolkata)

S14 keeps the existing stack and freezes a separate generated whole-dataset holdout.
Evaluate four proposed configurations exhaustively and independently run a three-trial
adaptive search. Report nonzero regret, unsupported workload abstentions and malformed
rejections explicitly; do not tune the heuristic against the held-out results or infer
production savings from the amplified synthetic storage objective. The categorical
generator was corrected to contain pairs of identical events; the full final matrix was
rerun. No optimizer or tariff tuning was performed.

The first Parquet holdout crashed with signal 11 during a bounded candidate worker. A
separate reproduction failed under the same RLIMIT_AS and passed with
`ARROW_DEFAULT_MEMORY_POOL=system`. Set that policy explicitly in profiling, integrity,
conversion and validation child environments and the Docker image. Preserve the limits.
The observed allocator/address-space interaction is the evidence for this workaround;
the precise underlying native-library defect is not established. Arrow documents allocator
selection in its [memory pool contract](https://arrow.apache.org/docs/cpp/memory.html).

Add `arrow_worker_memory_pool=system` to conversion execution-context lineage, rebuild the
immutable image and reject strict reuse/reproduction of earlier contexts. Historical saved
measurements remain unchanged. An engineer may inspect/export them, but fresh execution
requires a separately labeled current assessment. Actual validation/profile/all-conversion
regression uses dictionary/Zstd Parquet under the original limits. Focused report tests
isolate unrelated gates by stubbing the historical context; a separate test proves that
the actual pre-S14 context is rejected.

Measure upload, profile and full-workload paths separately and publish their distinct
envelopes. Keep 256 MiB raw and 1 GiB decoded defaults labeled policy maxima; no universal
capacity claim. Metadata backup uses matching PostgreSQL tools and a new temporary database;
object-store disaster recovery and production rollback remain explicit external drills.

Provide one sequential release command, a packaged demo including portable reports/fresh
reproduction, fresh dependency-directory CI rehearsal and an ephemeral-host CI workflow.
The rehearsal shares only tool binaries/download caches and committed test fixtures; it
does not share dependency installations or saved demo results. An initial offline attempt
lacked cached packages; the passing locked installation downloaded them. Hosted workflow
execution is unverified. Browser screenshots use the active evidence prefix so release
runs preserve earlier sprint artifacts. Service/browser suites run sequentially because
demo tenant UUID advisory locks share the database cluster.

No public/paid deployment, production data mutation, external messages, commit/push,
live provider/bill/customer verification or automatic post-MVP work is authorized here.
