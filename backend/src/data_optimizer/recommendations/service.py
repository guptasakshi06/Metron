"""Deterministic ranking from raw observations and reconciled S07 forecasts."""

from __future__ import annotations

import statistics
from decimal import Context, Decimal, localcontext

from data_optimizer.benchmarking.models import BenchmarkReport
from data_optimizer.economics.models import CostReport
from data_optimizer.economics.service import calculate
from data_optimizer.profiling.models import fingerprint
from data_optimizer.recommendations.models import Coverage, Decision, DecisionPolicy, Evaluation

LIMITATIONS = (
    "Best tested feasible option within bounded coverage; no global optimality claim.",
    "Local typed load and in-memory queries; no native scans, cloud, concurrency "
    "or tail SLA proof.",
    "Costs are forecasts from explicit assumptions and price snapshots; "
    "synthetic rates stay synthetic.",
    "Retention/copies are declared cost assumptions, not a deployed durability guarantee.",
    "Observed maxima and ranges describe these repeats, not population confidence intervals.",
)


def validate_matrix(report: BenchmarkReport) -> None:
    baseline = next(m for m in report.manifests if m.configuration.baseline)
    if len({m.key for m in report.manifests}) != len(report.manifests):
        raise ValueError("duplicate_matrix_candidate")
    if report.workload_fingerprint != baseline.integrity.workload_fingerprint:
        raise ValueError("workload_lineage_mismatch")
    for m in report.manifests:
        i = m.integrity
        if (
            m.manifest_fingerprint
            != fingerprint(m.model_dump(mode="json", exclude={"manifest_fingerprint"}))
            or i.report_fingerprint
            != fingerprint(i.model_dump(mode="json", exclude={"report_fingerprint"}))
            or i.request_fingerprint != fingerprint(m.verification_request.model_dump(mode="json"))
            or i.workload_fingerprint
            != fingerprint(m.verification_request.workload.model_dump(mode="json"))
            or m.reader != m.verification_request.candidate
            or m.input_fingerprint != baseline.input_fingerprint
            or m.request_fingerprint != baseline.request_fingerprint
            or i.workload_fingerprint != report.workload_fingerprint
            or not i.baseline
            or not i.candidate
            or not baseline.integrity.baseline
            or i.baseline.input_fingerprint != m.input_fingerprint
            or i.candidate.content_fingerprint != baseline.integrity.baseline.content_fingerprint
        ):
            raise ValueError("matrix_manifest_lineage_mismatch")
    keys = {m.key for m in report.manifests}
    pairs = [(t.candidate, t.repeat) for t in report.trials]
    if len(set(pairs)) != len(pairs) or any(
        t.candidate not in keys or t.repeat >= report.request.repeats for t in report.trials
    ):
        raise ValueError("invalid_matrix_trials")


def decide(
    report: BenchmarkReport | None,
    costs: dict[str, CostReport],
    policy: DecisionPolicy,
) -> Decision:
    policy = DecisionPolicy.model_validate(policy.model_dump())
    evaluations: list[Evaluation] = []
    baseline_id = None
    if report is not None:
        report = BenchmarkReport.model_validate(report.model_dump())
        # S07 validates hashes, content equivalence and workload lineage for the matrix.
        baselines = [m for m in report.manifests if m.configuration.baseline]
        alternatives = [m for m in report.manifests if not m.configuration.baseline]
        if len(baselines) != 1:
            raise ValueError("decision_requires_one_baseline")
        baseline = baselines[0]
        baseline_id = baseline.key
        if report.report_fingerprint != fingerprint(
            report.model_dump(mode="json", exclude={"report_fingerprint"})
        ) or report.environment_fingerprint != fingerprint(report.environment):
            raise ValueError("benchmark_fingerprint_mismatch")
        if report.request_fingerprint != fingerprint(report.request.model_dump(mode="json")):
            raise ValueError("benchmark_request_mismatch")
        validate_matrix(report)
        if set(costs) - {m.key for m in alternatives}:
            raise ValueError("costs_reference_unknown_candidate")
        selected_scenarios = {}
        common = None
        horizon = None
        for key, cost in costs.items():
            if cost != calculate(cost.request):
                raise ValueError("cost_report_must_reconcile")
            scenario = next((s for s in cost.request.scenarios if s.name == policy.scenario), None)
            if scenario is None:
                raise ValueError("selected_cost_scenario_missing")
            manifest = next(m for m in alternatives if m.key == key)
            if (
                scenario.baseline.id != baseline.key
                or scenario.candidate.id != key
                or scenario.baseline.footprint.data_file_bytes
                != tuple(a.physical_bytes for a in baseline.artifacts)
                or scenario.candidate.footprint.data_file_bytes
                != tuple(a.physical_bytes for a in manifest.artifacts)
                or baseline.integrity.baseline is None
                or scenario.baseline.footprint.logical_fingerprint
                != baseline.integrity.baseline.content_fingerprint
            ):
                raise ValueError("cost_measurement_lineage_mismatch")
            signature = fingerprint(
                {
                    "baseline": scenario.baseline.model_dump(mode="json"),
                    "prices": scenario.prices.model_dump(mode="json"),
                    "horizon": cost.request.horizon_months,
                    "steady": scenario.steady_monthly_usage,
                }
            )
            if common is not None and signature != common:
                raise ValueError("candidate_costs_require_identical_comparison_boundary")
            common, horizon = signature, cost.request.horizon_months
            selected_scenarios[key] = scenario
        baseline_result = next(iter(costs.values()), None)
        for manifest in report.manifests:
            key = manifest.key
            refs = (
                report.report_fingerprint,
                manifest.manifest_fingerprint,
                manifest.integrity.report_fingerprint,
            )
            coverage: list[Coverage] = []

            def add(
                name: str,
                status: str,
                reason: str,
                target: list[Coverage] = coverage,
                evidence: tuple[str, ...] = refs,
            ) -> None:
                target.append(
                    Coverage.model_validate(
                        {
                            "requirement": name,
                            "status": status,
                            "reason": reason,
                            "evidence_ids": evidence,
                        }
                    )
                )

            integrity = manifest.integrity
            add(
                "semantics",
                "passed" if integrity.status == "passed" else "violated",
                "Exact content, multiplicity and declared semantics checks.",
            )
            add(
                "reader_compatibility",
                "violated"
                if (
                    policy.allowed_formats is not None
                    and manifest.configuration.format not in policy.allowed_formats
                )
                or (
                    policy.allowed_codecs is not None
                    and manifest.configuration.codec not in policy.allowed_codecs
                )
                else "passed",
                "Compared against explicitly allowed formats/codecs.",
            )
            for capability in policy.required_capabilities:
                add(
                    "capability:" + capability,
                    "passed" if capability == "analytical_snapshot" else "untested",
                    "Only analytical immutable snapshots are implemented.",
                )
            workload = manifest.verification_request.workload
            add(
                "workload",
                "passed"
                if workload.queries and integrity.workload_status == "passed"
                else "untested",
                "Requires actual validated query results.",
            )
            add(
                "concurrency",
                "passed"
                if workload.concurrency == 1 and workload.concurrency_scope == "single_process"
                else "untested",
                "Runner tests one process only; unknown/production scope is unvalidated.",
            )
            fresh = policy.freshness_seconds is not None or any(
                q.freshness_seconds is not None for q in workload.queries
            )
            add(
                "freshness",
                "untested" if fresh else "not_required",
                "No refresh pipeline is benchmarked.",
            )
            trials = [t for t in report.trials if t.candidate == key]
            expected = {q.query_id: q.candidate_fingerprint for q in integrity.queries}
            complete = (
                len(trials) == report.request.repeats
                and {t.repeat for t in trials} == set(range(report.request.repeats))
                and all(
                    t.status == "passed"
                    and t.observation
                    and len(t.observation.queries) == len(expected)
                    and {q.query_id: q.result_fingerprint for q in t.observation.queries}
                    == expected
                    for t in trials
                )
            )
            failed = any(
                t.status not in {"passed", "cancelled", "budget_exhausted"} for t in trials
            )
            add(
                "benchmark",
                "passed" if complete else "violated" if failed else "untested",
                "All requested repeats and query result hashes must pass.",
            )
            for query in workload.queries:
                values = [
                    q.seconds
                    for t in trials
                    if t.observation
                    for q in t.observation.queries
                    if q.query_id == query.id
                ]
                status = "not_required"
                if query.target_latency_seconds is not None:
                    status = (
                        "untested"
                        if not complete or not values
                        else (
                            "passed"
                            if Decimal(str(max(values))) <= query.target_latency_seconds
                            else "violated"
                        )
                    )
                add(
                    "latency:" + query.id,
                    status,
                    "Observed maximum of query-only seconds; "
                    "excludes load/startup, no tail guarantee.",
                )
            candidate_cost = (
                costs.get(key) if not manifest.configuration.baseline else baseline_result
            )
            result = (
                next((r for r in candidate_cost.results if r.name == policy.scenario), None)
                if candidate_cost
                else None
            )
            scenario = selected_scenarios.get(key)
            if manifest.configuration.baseline and selected_scenarios:
                scenario = next(iter(selected_scenarios.values()))
            footprint = (
                scenario.baseline.footprint
                if scenario and manifest.configuration.baseline
                else scenario.candidate.footprint
                if scenario
                else None
            )
            add(
                "retention",
                "not_required"
                if policy.retention_days is None
                else "untested"
                if footprint is None
                else "passed"
                if footprint.retention_days >= policy.retention_days
                else "violated",
                "Declared equivalent retained-copy lifetime, not operational retention validation.",
            )
            total = None
            with localcontext(Context(prec=80)):
                if result and horizon is not None:
                    if manifest.configuration.baseline and result.baseline.total is not None:
                        total = result.baseline.total * horizon
                    elif (
                        result.candidate.total is not None
                        and result.migration_forecast.total is not None
                    ):
                        total = result.candidate.total * horizon + result.migration_forecast.total
            add(
                "cost",
                "passed" if total is not None else "untested",
                "Complete horizon operating cost plus once-only migration; "
                "baseline migration is zero.",
            )
            migration = (
                Decimal(0)
                if manifest.configuration.baseline
                else (result.migration_forecast.total if result else None)
            )
            add(
                "migration_budget",
                "not_required"
                if policy.maximum_migration_cost is None
                else "untested"
                if migration is None
                else "passed"
                if migration <= policy.maximum_migration_cost
                else "violated",
                "Once-only modeled migration total compared to the supplied budget.",
            )
            durations = (
                [
                    t.observation.load_seconds + t.observation.workload_seconds
                    for t in trials
                    if t.observation
                ]
                if complete
                else []
            )
            states = {c.status for c in coverage}
            feasibility = (
                "excluded"
                if "violated" in states
                else ("untested" if "untested" in states else "feasible")
            )
            evaluations.append(
                Evaluation(
                    candidate_id=key,
                    configuration=manifest.configuration,
                    feasibility=feasibility,
                    coverage=tuple(coverage),
                    horizon_total=total,
                    workload_seconds=statistics.median(durations) if durations else None,
                    observed_range_seconds=(min(durations), max(durations)) if durations else None,
                    evidence_ids=refs
                    + ((candidate_cost.report_fingerprint,) if candidate_cost else ()),
                    costs=result,
                )
            )
    feasible = sorted(
        (e for e in evaluations if e.feasibility == "feasible"),
        key=lambda e: (e.horizon_total, not e.configuration.baseline, e.candidate_id),
    )
    best = feasible[0] if feasible else None
    baseline_eval = next((e for e in evaluations if e.candidate_id == baseline_id), None)
    outcome = "insufficient_evidence"
    selected = None
    reason = "Supply raw dataset/workload, complete costs and evidence for required constraints."
    # Unknown costs/constraints on a tested candidate cannot silently make it lose the ranking.
    unknown = any(e.feasibility == "untested" for e in evaluations)
    if best and baseline_eval and baseline_eval.horizon_total is not None and not unknown:
        assert best.horizon_total is not None and baseline_eval.horizon_total is not None
        with localcontext(Context(prec=80)):
            savings = baseline_eval.horizon_total - best.horizon_total
            threshold = max(
                policy.minimum_net_savings,
                baseline_eval.horizon_total * policy.minimum_savings_fraction,
            )
        if best.candidate_id != baseline_id and savings > 0 and savings >= threshold:
            outcome, selected = "change", best.candidate_id
            reason = (
                "Best tested feasible cost including migration meets the materiality threshold."
            )
        elif baseline_eval.feasibility == "feasible":
            outcome, selected = "keep_current", baseline_id
            reason = "No tested feasible change meets the configured net-benefit threshold."
        else:
            reason = "Baseline violates requirements and no feasible change meets materiality."
    pareto = tuple(
        e.candidate_id
        for e in feasible
        if not any(
            other.horizon_total is not None
            and e.horizon_total is not None
            and other.workload_seconds is not None
            and e.workload_seconds is not None
            and other.horizon_total <= e.horizon_total
            and other.workload_seconds <= e.workload_seconds
            and (
                other.horizon_total < e.horizon_total or other.workload_seconds < e.workload_seconds
            )
            for other in feasible
        )
    )
    questions = tuple(
        sorted({c.requirement for e in evaluations for c in e.coverage if c.status == "untested"})
    )
    decision = Decision(
        decision_fingerprint="0" * 64,
        outcome=outcome,
        selected_candidate_id=selected,
        best_tested_candidate_id=best.candidate_id if best else None,
        baseline_candidate_id=baseline_id,
        policy=policy,
        candidates=tuple(evaluations),
        tradeoff_candidate_ids=pareto,
        reason=reason,
        limitations=LIMITATIONS,
        next_questions=questions
        or (
            ("Provide a dataset and constrained workload for measurement.",)
            if report is None
            else ()
        ),
    )
    return decision.model_copy(
        update={
            "decision_fingerprint": fingerprint(
                decision.model_dump(mode="json", exclude={"decision_fingerprint"})
            )
        }
    )
