# S08 decisions and sequential assessments

The `s08.1` local assessment CLI runs the real S03 profile, S05 candidate/conversion/integrity,
S06 Docker benchmark and S07 itemized forecast path. It requires no API key or service database.
Its decision means **best tested feasible option within the recorded bounded search**, under
the named cost scenario and supported requirements. It does not establish global optimality.

## Run

After locked setup and an available local benchmark image:

```bash
export PATH="$PWD/.tools/uv-bin:$PATH"
make benchmark-image
uv run --locked --project backend data-optimizer assess examples/s04-events.ndjson \
  --request examples/s08-assessment-request.json \
  --root /tmp/s08-workspace --output /tmp/s08-assessment.json
```

The example intentionally amplifies an **invented** storage tariff to make differences in a
three-record fixture visible. All other rates/usage are explicitly synthetic zero assumptions.
Measured bytes, query results and timings are real local observations; forecast monetary
benefits are not customer savings or live quotes. Supply realistic reviewed S07 scenarios
for a useful real assessment. Every result embeds the full request, raw benchmark matrix,
configuration/integrity lineage, price snapshots, itemized costs and requirement coverage.

`--request` accepts `AssessmentRequest` (`optimization/assessment.py`): conversion request,
benchmark settings, S07 `cost_template`, explicit `replays_per_month` (null stays unknown),
policy and search budget. The template is applied independently to each tested alternative;
format-specific requests, labor, metadata and other unmeasured quantities remain supplied
assumptions. S09 can build per-candidate inputs; this CLI does not derive provider usage from
format choice. Only one explicitly named scenario is authoritative for ranking; all supplied
scenario calculations remain in the cost reports. Costs across candidates must share the
same baseline, horizon, prices and steady-usage assumptions. Full scope/formulas:
[pricing method](pricing-method.md), [benchmark method](benchmark-method.md).

Use a new output path on every invocation. Exit 0 means `change` or `keep_current`, 1 means
a saved `insufficient_evidence` result, 2 means invalid setup/input/output or unavailable
required runtime. Outputs cannot overwrite sources or live workspace files. The private
workspace retains assessment copies until deliberately removed by its local owner; this
CLI is not a multi-tenant service and has no automatic expiration. No source is deleted.

Repeat the same source/request/workspace with a new output path to resume. Completed
identical experiments are reused, including baseline repeats when the matrix expands.
Changed source/request creates another session. Environment/image/request/manifest drift
cannot reuse an old benchmark as a compatible new experiment.

For metadata-only guidance, first export a local profile and review it as in the
[profiling runbook](runbooks/profiling.md), then:

```bash
uv run --locked --project backend data-optimizer assess --metadata /tmp/profile.json \
  --request examples/s08-assessment-request.json \
  --root /tmp/s08-metadata --output /tmp/s08-guidance.json
```

Omit both the positional source and `--metadata` for a startup without data. These paths
return scenario guidance, questions and `insufficient_evidence`, with no computed savings,
benchmarks or selected candidate. A supplied price/cost template remains input assumptions;
it is not historical evidence. No Docker call occurs for these paths.

## Feasibility, costs and outcomes

Each candidate has per-requirement `passed`, `violated`, `untested` or `not_required` coverage,
reasons and evidence IDs. Any violation excludes it; otherwise any required untested field
makes it untested. A missing/failed benchmark is never ranked as fast or free.

- Exact semantic integrity and query-result equality must pass. Manifest/report/request,
  workload/content and actual data-byte lineage are checked. Duplicate trial pairs and
  unknown candidate/cost references are rejected; economics is recomputed to verify it.
- Reader compatibility uses declared `allowed_formats`/`allowed_codecs`. Null means no
  additional restriction. Only `analytical_snapshot` is a supported required capability;
  transactions, production throughput, durability and other capabilities remain untested.
- Retention checks compare the requested days with the equivalent cost footprint's declared
  lifetime. This is assumption-based coverage, with no operational retention guarantee.
- Any freshness target (policy or query) stays untested: no refresh pipeline is benchmarked.
- Workload needs actual validated queries and explicit single-process concurrency=1.
  Unknown concurrency and production concurrency stay untested.
- A query's `target_latency_seconds` compares the maximum observed **query-only** time across
  all required repeats. This excludes load/startup and does not prove tail, cloud or end-to-end
  response latency. Load plus full-workload median and observed min/max are supplied separately
  for comparison. Missing targets mean no required latency ceiling, not a validated SLA.
- All requested repeats/query-result hashes must pass for a usable benchmark. Timeouts and
  other measured failures exclude; incomplete/cancelled/budget-stopped coverage is untested.
- Complete recurring and once-only migration inputs are needed for comparable horizon costs.
  The optional `maximum_migration_cost` constrains forecast one-time costs; baseline migration
  is zero. Decimal calculations use a private precision-80 context.

Objective: `monthly_operating_total * horizon_months + once_only_migration_total`.
Baseline uses its monthly total and zero migration. Ranking retains it even when a requirement
excludes it, so the existing reference remains visible. Cost ties favor baseline, then stable ID.
The compact Pareto set contains feasible candidates not dominated in both horizon cost and
median local load-plus-workload seconds; it is a descriptive tradeoff, not another objective.

Default materiality is the greater of **10 catalog currency units** and **1% of baseline
horizon cost**. `change` requires strictly positive net benefit meeting that threshold,
a feasible tested candidate and complete baseline economics. An infeasible baseline can
still be replaced by a beneficial feasible candidate. `keep_current` requires a feasible
baseline and no tested feasible change meeting the threshold. Missing costs or required
coverage on a tested candidate cause `insufficient_evidence`; they cannot silently make it
lose. Candidates outside the tested search coverage are explicitly outside the claim.
When materiality retains baseline, `best_tested_candidate_id` can identify a cheaper option
while `selected_candidate_id` identifies baseline. No invented confidence percentage.

## Finite sequential optimizer

`optimization/search.py` exposes `ask(SearchState)` and `tell(state, SearchTrial, elapsed)`.
State records seed, full configurations, pending proposal, history, feasibility, objective,
evidence IDs, elapsed budget, prediction labels and stop reason. Trials here mean candidate
configurations; S06 separately bounds per-candidate repeated container trials.

Up to four eligible configurations use seeded bounded enumeration, with baseline first.
Larger finite spaces (at most twelve) use `finite_neighbor_exploration_v1`, a deliberately
small dependency-free adaptive heuristic. Baseline is first, then a seeded initial alternative.
After feasible alternatives exist, predict each untested configuration's horizon cost by
inverse-distance-weighted observed costs, weight `1 / (distance + 0.05)`. Distance is the fraction
of unequal format, codec, level, row-group, partition and sort fields. Minimize prediction
minus `exploration * cost_scale * nearest_distance`, with exploration default 0.25 and scale
`max(observed range, largest absolute cost, 1)`. Seeded order resolves ties. Failed/untested
trials supply no cost labels. Every configuration is proposed at most once.

Distance is an **uncalibrated exploration proxy**, not statistical uncertainty; predictions
are labeled `heuristic_prediction_not_evidence`. They only prioritize actual conversion,
integrity and measurements. No prediction can become a recommendation. This is a bounded
heuristic without convergence/regret claims, custom supervised training or cross-dataset learning.

Optuna's current [ask-and-tell documentation](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/009_ask_and_tell.html)
was checked (5.0.0 documentation on implementation day). The interface separates proposals and
measurement ingestion. We use that interface shape with finite enumeration/no-replacement
neighbor exploration rather than adding Optuna to the locked stack for a maximum twelve-point
space. This is a documented implementation choice, not a claim to implement TPE or Optuna.
Revisit with a materially larger configuration space and held-out regret evaluation.

Default search budget: seed 42, eight proposed configurations, 600 experiment seconds.
`max_trials` is 1–12; total sequential elapsed time includes conversion, measurement and scoring.
Profiling and candidate generation precede it and retain their separate bounded S03/S05 limits.
Checks happen before proposals; conversion and Docker execution receive the remaining search
deadline. Docker control/cleanup and bounded preprocessing can add overhead, as in S06. Stops:
`space_exhausted`, `trial_budget`, `time_budget`. No untested global-optimum claim follows.

## Checkpoints and recovery boundary

Session identity hashes input plus complete normalized assessment request. Private sessions
are locked against concurrent writers. Checkpoints have hashes, schema validation and atomic
same-directory replacement with file fsync; they retain input profile, candidate space,
conversion outcomes, current matrix and search state. Artifact files are rehashed on resume.
The proposal is saved before work; each conversion and matrix is saved before `tell`.
Per-proposal immutable benchmark files recover a result saved just before interruption.
An interrupted attempt's wall time, including downtime, is charged conservatively on resume.
Completed trial history never executes again; unchanged matrices reuse completed successful
and failed trials after request/environment/manifest/result-hash checks.

Checksums are change detectors, not authentication. This is trusted local storage. A parent
killed between benchmark execution and durable result publication can lose that result and
rerun it; exactly-once external execution is not claimed. Directory fsync, multi-host recovery,
queue leases, cancellation API, tenant ownership/admission and expiry remain S09. Retain the
same image and artifacts to reproduce; no deployment or production mutation is performed.

## Verify

```bash
make check
make test
make test-benchmark
make build
uv run --locked --project backend python scripts/verify-s08.py --output-dir /tmp/s08-evidence
```

`make demo` builds the package and runs the same verification into a new printed temporary
output directory; it requires the prebuilt benchmark image.

The final script runs the extracted wheel outside the repository, raw and already-compressed
fixtures through actual Docker, metadata/startup guidance and unchanged-session resume. It
also checks unknown usage against the newly measured matrix. See
[S08 verification](evidence/s08-verification.md) for recorded results and remaining limits.
