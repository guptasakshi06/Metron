# Decision 0008: tested feasibility, explicit materiality and bounded sequential search

Date: 2026-11-02 (Asia/Kolkata)

- Keep the S01–S07 stack and lockfiles. Add versioned `s08.1` executable decision/assessment
  contracts. Consume raw S06 observations and reconciled S07 scenarios, with input/workload,
  content, environment, price and evidence lineage. Authenticated asynchronous service
  persistence belongs to S09, as planned.
- Rank complete tested feasible candidates by horizon operating costs plus once-only
  migration. Retain baseline and cost/latency Pareto alternatives. Distinguish violations,
  untested requirements and unnecessary constraints. Required freshness/production concurrency
  remain untested rather than inferred. Retention is declared lifetime coverage only.
- Materiality defaults to max(10 currency units, 1% baseline horizon cost). Support change,
  feasible keep_current and insufficient_evidence. Query ceilings compare observed query-only
  maxima, with explicit scope; no native scan, cloud or tail performance claim.
- Implement finite `ask`/`tell`, tiny-space enumeration and distance-weighted adaptive
  exploration for larger bounded spaces. Reviewed Optuna 5.0.0's current official ask/tell
  API; chose a dependency-free finite heuristic because the space is at most twelve
  predefined configurations and duplicate expensive trials must be avoided. Predictions
  and exploration distance are heuristic, never calibrated confidence or validated results.
- Persist hash-checked private checkpoints and pending trials, published measurements and
  complete history. Reuse identical completed benchmark trials under compatible immutable
  image/environment/request/manifests. Charge interrupted time conservatively; no multi-host
  or exactly-once external-execution guarantee. Never delete originals or automatically migrate.
- Add a real CLI assessment from local profile through sandboxed measurements and forecast
  decision. Metadata/startup paths return scenario guidance without savings calculations.
  The reproducible demonstration uses amplified explicitly synthetic prices over actual
  tiny-file measurements; it is not customer validation.

Defaults, formulas, API shapes, run/verify commands and boundaries:
[decision method](../decision-method.md).
