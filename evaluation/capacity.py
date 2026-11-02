"""Measured local workload envelope and explicit quota rejection, never a universal ceiling."""

import argparse
import json
import platform
import tempfile
import time
from pathlib import Path

from data_optimizer.optimization.assessment import AssessmentRequest, assess
from pydantic import ValidationError
from run import verify

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="s14-workload-") as directory:
        root = Path(directory)
        source = root / "capacity.ndjson"
        source.write_text(
            "".join(
                json.dumps(
                    {
                        "id": f"{i:08}",
                        "category": str(i % 7),
                        "value": i,
                        "text": "x" * 192,
                    }
                )
                + "\n"
                for i in range(4096)
            )
        )
        raw = json.loads((ROOT / "examples/s08-assessment-request.json").read_text())
        raw["conversion"]["source"] = {"format": "ndjson"}
        raw["conversion"]["max_candidates"] = 4
        raw["conversion"]["workload"] = {
            "queries": [
                {
                    "id": f"groups_{i}",
                    "kind": "grouped_aggregate",
                    "group_by": ["category"],
                    "aggregates": [
                        {"op": "count", "alias": "n"},
                        {"op": "sum", "column": "value", "alias": "total"},
                    ],
                    "target_latency_seconds": "60",
                }
                for i in range(32)
            ],
            "concurrency": 1,
            "concurrency_scope": "single_process",
        }
        raw["benchmark"]["repeats"] = 5
        raw["search"].update(max_trials=4, enumeration_limit=4)
        request = AssessmentRequest.model_validate(raw)
        started = time.monotonic()
        report = assess(source, root / "workspace", request)
        verify(report)
        assert len(report.benchmark.trials) == 20
        assert len(report.search.history) == 4
        assert all(len(t.observation.queries) == 32 for t in report.benchmark.trials)
        (args.output_dir / "workload-report.json").write_text(
            report.model_dump_json(indent=2) + "\n"
        )
        for mutation in ("queries", "repeats"):
            invalid = json.loads(json.dumps(raw))
            if mutation == "queries":
                invalid["conversion"]["workload"]["queries"].append(
                    {"id": "query_33", "kind": "full_scan"}
                )
            else:
                invalid["benchmark"]["repeats"] = 6
            try:
                AssessmentRequest.model_validate(invalid)
            except ValidationError:
                pass
            else:
                raise AssertionError("Over-limit request accepted")
        results = {
            "platform": platform.platform(),
            "input_bytes": source.stat().st_size,
            "input_sha256": report.candidates.input_fingerprint,
            "rows": 4096,
            "queries": 32,
            "repeats": 5,
            "candidates": 4,
            "passed_trials": 20,
            "seconds": time.monotonic() - started,
            "peak_trial_rss_kib": max(
                t.observation.peak_rss_kib for t in report.benchmark.trials
            ),
            "over_limit_query_and_repeat_rejected": True,
            "boundary": "One generated categorical workload, typed materialization; "
            "not worst-case records, native scans, concurrency, tail or 256 MiB capacity.",
        }
        # Same source, deliberately impossible query-only latency bound, measured afresh.
        strict = json.loads(json.dumps(raw))
        strict["conversion"]["workload"]["queries"] = [
            {
                "id": "impossible",
                "kind": "projection",
                "columns": ["id"],
                "target_latency_seconds": "0.000000000001",
            }
        ]
        strict["benchmark"]["repeats"] = 1
        strict_report = assess(
            source, root / "strict", AssessmentRequest.model_validate(strict)
        )
        verify(strict_report)
        assert strict_report.decision.outcome == "insufficient_evidence"
        assert all(
            any(
                c.requirement == "latency:impossible" and c.status == "violated"
                for c in e.coverage
            )
            for e in strict_report.decision.candidates
        )
        results["impossible_latency_abstains"] = True
        (args.output_dir / "strict-latency-report.json").write_text(
            strict_report.model_dump_json(indent=2) + "\n"
        )
        (args.output_dir / "workload-results.json").write_text(
            json.dumps(results, indent=2) + "\n"
        )
        print(json.dumps(results))


if __name__ == "__main__":
    main()
