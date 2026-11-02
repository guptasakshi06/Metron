"""Real held-out pipeline evaluation; fails closed on correctness gates.

Run from the repository using the locked Python environment. Raw inputs/workspaces are
temporary; keep requests, fingerprinted reports and a compact result ledger as evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import subprocess
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from data_optimizer.economics.service import calculate
from data_optimizer.optimization.assessment import AssessmentRequest, assess
from data_optimizer.profiling.models import fingerprint
from data_optimizer.readers.stream import ProfileError
from data_optimizer.recommendations.service import decide
from data_optimizer.reports.service import make_bundle, render_markdown
from heldout import generate

ROOT = Path(__file__).resolve().parents[1]


def verify(report):
    assert report.report_fingerprint == fingerprint(
        report.model_dump(mode="json", exclude={"report_fingerprint"})
    )
    for cost in report.costs.values():
        assert cost == calculate(cost.request)
        for result in cost.results:
            for breakdown in (
                result.baseline,
                result.candidate,
                result.migration_forecast,
            ):
                known = sum(
                    (i.amount for i in breakdown.items if i.amount is not None),
                    Decimal(0),
                )
                assert known == breakdown.known_subtotal
                if breakdown.total is not None:
                    assert known == breakdown.total
    decision = report.decision
    if decision.selected_candidate_id:
        selected = next(
            c
            for c in decision.candidates
            if c.candidate_id == decision.selected_candidate_id
        )
        assert selected.feasibility == "feasible"
        assert not any(c.status in {"violated", "untested"} for c in selected.coverage)
        manifest = next(
            m for m in report.benchmark.manifests if m.key == selected.candidate_id
        )
        assert manifest.integrity.status == "passed"
        assert manifest.integrity.baseline.row_count == report.profile.row_count
    if report.benchmark:
        assert all(t.status == "passed" for t in report.benchmark.trials)
        assert all(m.integrity.status == "passed" for m in report.benchmark.manifests)
        assert all(s.p95_seconds is None for s in report.benchmark.summaries)
    return decision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    base = json.loads((ROOT / "examples/s08-assessment-request.json").read_text())
    with tempfile.TemporaryDirectory(prefix="s14-holdout-") as temporary:
        root = Path(temporary)
        for case in generate(root / "inputs"):
            source = case["path"]
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            raw = json.loads(json.dumps(base))
            raw["conversion"]["source"] = {"format": case["format"]}
            raw["conversion"]["max_candidates"] = 4
            raw["conversion"]["workload"] = {
                "queries": [{"id": "ids", "kind": "projection", "columns": ["id"]}],
                "concurrency": 1,
                "concurrency_scope": "single_process",
            }
            raw["benchmark"]["repeats"] = 2
            raw["search"].update(max_trials=4, enumeration_limit=4)
            request = AssessmentRequest.model_validate(raw)
            started = time.monotonic()
            if case.get("reject"):
                try:
                    assess(source, root / case["name"], request)
                except ProfileError as error:
                    assert "json" in str(error), str(error)
                    results.append(
                        {
                            "case": case["name"],
                            "input_sha256": digest,
                            "rejected": str(error),
                            "seconds": time.monotonic() - started,
                        }
                    )
                else:
                    raise AssertionError("Malformed holdout was accepted")
                continue
            full = assess(source, root / (case["name"] + "-full"), request)
            verify(full)
            assert full.profile.row_count == case["rows"]
            assert full.search.pending is None
            assert len(full.search.history) == len(full.search.configurations)
            full_seconds = time.monotonic() - started
            (args.output_dir / (case["name"] + "-exhaustive.json")).write_text(
                full.model_dump_json(indent=2) + "\n"
            )
            if case["unsupported_workload"]:
                assert full.decision.outcome == "insufficient_evidence"
            # Independent real adaptive run, smaller trial budget, identical supported space.
            raw["search"].update(max_trials=3, enumeration_limit=1)
            adaptive_request = AssessmentRequest.model_validate(raw)
            started = time.monotonic()
            adaptive = assess(
                source, root / (case["name"] + "-adaptive"), adaptive_request
            )
            verify(adaptive)
            adaptive_seconds = time.monotonic() - started
            assert len(adaptive.search.history) <= 3
            assert {c.fingerprint for c in full.search.configurations} == {
                c.fingerprint for c in adaptive.search.configurations
            }
            (args.output_dir / (case["name"] + "-adaptive.json")).write_text(
                adaptive.model_dump_json(indent=2) + "\n"
            )
            full_best = next(
                (
                    c
                    for c in full.decision.candidates
                    if c.candidate_id == full.decision.best_tested_candidate_id
                ),
                None,
            )
            adaptive_best = next(
                (
                    c
                    for c in adaptive.decision.candidates
                    if c.candidate_id == adaptive.decision.best_tested_candidate_id
                ),
                None,
            )
            regret = (
                adaptive_best.horizon_total - full_best.horizon_total
                if full_best and adaptive_best
                else None
            )
            assert regret is None or regret >= 0
            # Re-evaluate the same immutable measurements under an impossible reader constraint.
            if full.benchmark:
                impossible = decide(
                    full.benchmark,
                    full.costs,
                    full.request.policy.model_copy(update={"allowed_codecs": ()}),
                )
                assert impossible.outcome == "insufficient_evidence"
                assert impossible.selected_candidate_id is None
            # Human and machine exports come from this actual held-out calculation.
            bundle = make_bundle(full)
            markdown = render_markdown(bundle)
            assert full.decision.outcome in markdown
            (args.output_dir / (case["name"] + "-report.md")).write_text(markdown)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
            observations = (
                [t.observation for t in full.benchmark.trials if t.observation]
                if full.benchmark
                else []
            )
            results.append(
                {
                    "case": case["name"],
                    "input_sha256": digest,
                    "input_bytes": source.stat().st_size,
                    "rows": case["rows"],
                    "source_unchanged": True,
                    "outcome": full.decision.outcome,
                    "adaptive_outcome": adaptive.decision.outcome,
                    "exhaustive_configurations": len(full.search.configurations),
                    "exhaustive_tested": len(full.search.history),
                    "adaptive_tested": len(adaptive.search.history),
                    "actual_trials": len(observations),
                    "adaptive_actual_trials": len(adaptive.benchmark.trials)
                    if adaptive.benchmark
                    else 0,
                    "adaptive_stop": adaptive.search.stop_reason,
                    "horizon_cost_regret_synthetic_currency": str(regret)
                    if regret is not None
                    else None,
                    "full_seconds": full_seconds,
                    "adaptive_seconds": adaptive_seconds,
                    "max_trial_peak_rss_kib": max(
                        (o.peak_rss_kib for o in observations), default=None
                    ),
                    "trial_cpu_seconds": sum(o.cpu_seconds for o in observations),
                    "selected_constraint_violations": 0,
                    "costs_reconcile": True,
                    "report_fingerprint": full.report_fingerprint,
                    "excluded": [
                        {"codec": c.configuration.codec, "reasons": c.reasons}
                        for c in full.candidates.candidates
                        if c.status == "excluded"
                    ],
                    "search_reasons": [t.reason for t in full.search.history],
                }
            )
            print(
                json.dumps(
                    {
                        "case": case["name"],
                        "outcome": full.decision.outcome,
                        "regret": str(regret),
                    }
                ),
                flush=True,
            )
    result = {
        "version": "s14.1",
        "dataset_split": "s14_generated_whole_datasets_only",
        "tuning": "none; frozen generator, no learned model or post-result tuning",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "child_peak_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "docker": subprocess.check_output(["docker", "--version"], text=True).strip(),
        "cases": results,
        "gates_passed": True,
        "boundary": "Actual local measurements; amplified synthetic prices. Bounded four-"
        "configuration space, no global optimum, cloud, native scan, tail or pilot claim.",
    }
    (args.output_dir / "results.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
