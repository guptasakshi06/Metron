# S08 verification — 2026-11-02

S08's three acceptance gates passed locally. The CLI profiles actual input, generates
and verifies copies, executes Docker queries, computes explicit itemized forecasts and
returns an evidence-linked decision. Monetary examples use visibly synthetic amplified
prices; no live provider, customer, cloud/native-scan or production savings are claimed.

## Commands and results

From the repository root, using its installed Python 3.12.3 and project-local tools:

- `UV_OFFLINE=1 make check` — passed Ruff, strict mypy on 72 source files,
  ESLint and TypeScript. An intermediate mypy local-variable typing error was fixed;
  the final command passed.
- `UV_OFFLINE=1 make test` — 298 backend tests passed, 28 service/Docker tests deselected;
  3 frontend tests passed. Includes 37 S08 tests: 21 ranking, 10 optimizer, 6 orchestration.
  One existing Starlette/httpx TestClient deprecation warning remains.
- `UV_OFFLINE=1 make test-benchmark` — all 10 actual Docker tests passed in 26.68s.
  Includes existing limits/isolation/fresh/warm/cancellation tests plus sequential reuse.
- After adding stricter cached-request/query validation,
  `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend pytest -q -m benchmark_sandbox backend/tests/test_benchmark_sandbox.py::test_sequential_matrix_reuses_successful_identical_trials`
  — passed in 3.88s. It measured baseline twice, added only two candidate repeats, then
  reused the full matrix with zero further Docker calls; mismatched seed was rejected.
- `UV_OFFLINE=1 make build` — Python wheel/sdist and Vite production build passed.
- `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend python scripts/verify-s08.py --output-dir docs/evidence`
  — initial actual extracted-wheel CLI verification passed five cases.
- Final `UV_OFFLINE=1 make demo` — rebuilt final wheel/sdist/frontend, then ran the same
  five-case extracted-wheel verification outside the repository into
  `/tmp/data-optimizer-s08-demo.GCQck0`. Final JSON evidence was copied from that run into
  this directory. Resume reused identical reports and unchanged measurement files;
  the source SHA-256 stayed unchanged.
- `UV_OFFLINE=1 .tools/uv-bin/uv run --locked --project backend ruff check scripts/verify-s08.py`
  and `git diff --check` — passed. Final `docker ps -a --filter label=data-optimizer.benchmark=true --format '{{.Names}}'`
  returned no remaining labeled benchmark containers.

Environment: Python 3.12.3, uv 0.13.6, Node 24.22.2, Vite 7.3.7, Linux x86_64 Intel
Core i7-12650H, Docker 29.1.3, PyArrow/Arrow 26.0.0 and DuckDB 1.5.6. Reused immutable
S06 image `sha256:2408f9bd11b4153494e1dc1bb4fe960f2151a00e971b98b1334f763ffa011ed6`.
No dependency/lockfile or benchmark-worker execution change required a new image.

## Gate evidence

| Gate | Evidence |
| --- | --- |
| Beneficial tested change, efficient baseline and abstention | `s08-change.json` selects validated gzip; `s08-keep-current.json` retains compressed baseline; `s08-metadata.json`, `s08-startup.json` and `s08-unknown-usage-decision.json` abstain without invented savings |
| Adaptive response and bounded search | Deterministic objective inversion changes next selection; tiny enumeration ignores noisy objective values; injected elapsed values stop time/trial budgets; pending-state round trips, crash-after-measurement recovery and corrupt-artifact rejection pass |
| Best tested feasible option, honest scope | Raw repeats, exact integrity/workload checks, common baseline/scenario costs, requirement coverage, exclusions, materiality and Pareto evidence embedded in reports; tests reject failed/partial/tampered/mismatched evidence |

Each actual raw/compressed case made six configuration proposals, with five validated
benchmark manifests × three repeats = **15 actual Docker trials**. The small partition
layout was excluded during conversion; it is not a successful trial. Search stopped at its
six-configuration trial budget. Baseline NDJSON data was 287 bytes; selected gzip was
138 bytes. Compressed-input baseline and equivalent gzip alternative were both 138 bytes,
so materiality retained the baseline. These are tiny local fixture observations, not capacity
or representative customer measurements. Actual timings/ranges remain in the raw reports.

The artificially amplified example produces baseline/candidate horizon costs 344.400000 /
165.600000 synthetic USD units. Those amounts arise from the explicit invented storage
rate, not a provider invoice. Unknown replay usage leaves compute unknown even when its
synthetic rate is zero, and causes abstention.

`s08-verification-results.json` records final fingerprints, exit codes, source hash and resume
identity. The resumed report was byte-for-byte identical to `s08-change.json`; it is not
stored as a redundant second copy. Metadata/startup cases made no Docker calls or cost
calculations. Unknown-usage verification consumes the newly measured matrix without rerunning it.

## Limits and checks not run

Service/PostgreSQL/MinIO integration was not rerun: S08 changes no API, schema, ownership or
object-store path. Async orchestration, leases, service admission/expiration and cancellation API
remain S09. S06 native file scans, true cold cache, tail latency, cloud concurrency and larger
capacity limits remain unvalidated. Snapshot freshness and arbitrary capability requirements
abstain. Retention is a declared assumption, not deployed enforcement.

The finite neighbor optimizer is an uncalibrated prioritization heuristic, with no learned
model, regret/convergence guarantee or global-optimum claim. All recommended results still need
actual passed validation. Private local checkpoints recover published results; a process death
between execution and durable publication can lose a trial and cause a rerun. No parent-SIGKILL,
power-loss, multi-host recovery or live deployment test was run. The injected interruption test
covers the saved-measurement/before-tell boundary. No production data mutation, deployment,
paid provisioning, customer validation, agent commit or push occurred.

Method and decisions: [decision method](../decision-method.md),
[decision 0008](../decisions/0008-s08-ranking-search.md).
