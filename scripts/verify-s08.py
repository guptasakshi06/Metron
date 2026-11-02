"""Reproduce actual packaged profile-to-decision CLI, raw trials and resume evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from data_optimizer.optimization.assessment import AssessmentReport
from data_optimizer.profiling.models import fingerprint

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source = REPO / "examples/s04-events.ndjson"
    fixture = REPO / "examples/s08-assessment-request.json"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    records = []
    with tempfile.TemporaryDirectory(prefix="verify-s08-") as temporary:
        root = Path(temporary)
        wheel_root = root / "wheel"
        wheels = list((REPO / "backend/dist").glob("*.whl"))
        assert len(wheels) == 1, "Run make build first"
        with zipfile.ZipFile(wheels[0]) as wheel:
            wheel.extractall(wheel_root)
        environment = dict(os.environ, PYTHONPATH=str(wheel_root))
        imported = subprocess.run(
            [
                sys.executable,
                "-c",
                "import data_optimizer; print(data_optimizer.__file__)",
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        assert str(wheel_root) in imported.stdout

        def run(
            label: str,
            input_path: Path | None,
            expected: str,
            request_path: Path = fixture,
            workspace: Path | None = None,
            metadata: Path | None = None,
        ) -> AssessmentReport:
            output = root / f"{label}.json"
            command = [sys.executable, "-m", "data_optimizer.cli", "assess"]
            if input_path:
                command.append(str(input_path))
            command += [
                "--request",
                str(request_path),
                "--root",
                str(workspace or root / label),
                "--output",
                str(output),
            ]
            if metadata:
                command += ["--metadata", str(metadata)]
            outcome = subprocess.run(
                command,
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            expected_exit = 1 if expected == "insufficient_evidence" else 0
            assert outcome.returncode == expected_exit, outcome.stderr
            report = AssessmentReport.model_validate_json(output.read_bytes())
            assert report.decision.outcome == expected, (
                report.decision.model_dump_json()
            )
            assert report.report_fingerprint == fingerprint(
                report.model_dump(mode="json", exclude={"report_fingerprint"})
            )
            if report.benchmark:
                assert all(
                    t.status == "passed" and t.observation
                    for t in report.benchmark.trials
                )
                assert len(report.benchmark.trials) == (
                    len(report.benchmark.manifests) * report.benchmark.request.repeats
                )
            if label != "resumed":
                shutil.copyfile(output, args.output_dir / f"s08-{label}.json")
            records.append(
                {
                    "case": label,
                    "exit_code": outcome.returncode,
                    "outcome": expected,
                    "report_fingerprint": report.report_fingerprint,
                    "selected_candidate": report.decision.selected_candidate_id,
                    "actual_trials": len(report.benchmark.trials)
                    if report.benchmark
                    else 0,
                    "stop_reason": report.search.stop_reason if report.search else None,
                }
            )
            return report

        work = root / "raw-workspace"
        changed = run("change", source, "change", workspace=work)
        checkpoints = list(work.glob("sessions/*/*-benchmark.json"))
        cached_before = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in checkpoints
        }
        resumed = run("resumed", source, "change", workspace=work)
        assert resumed == changed
        cached_after = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in work.glob("sessions/*/*-benchmark.json")
        }
        assert cached_before == cached_after
        # Already compressed input uses the real validated gzip output as its baseline.
        gzip_manifest = next(
            m for m in changed.benchmark.manifests if m.configuration.codec == "gzip"
        )
        gzip_artifact = next(
            work.glob(f"artifacts/*/assessments/*/{gzip_manifest.key}/part-*.ndjson.gz")
        )
        efficient = root / "already-efficient.ndjson.gz"
        shutil.copyfile(gzip_artifact, efficient)
        kept = run("keep-current", efficient, "keep_current")
        assert (
            kept.decision.selected_candidate_id == kept.decision.baseline_candidate_id
        )
        metadata = root / "profile.json"
        metadata.write_text(changed.profile.model_dump_json())
        run("metadata", None, "insufficient_evidence", metadata=metadata)
        run("startup", None, "insufficient_evidence")
        # Unknown replay usage is evaluated from the newly measured raw matrix without rerunning it.
        from data_optimizer.optimization.assessment import (
            AssessmentRequest,
            cost_reports,
        )
        from data_optimizer.recommendations.service import decide

        unknown_request = AssessmentRequest.model_validate_json(
            fixture.read_bytes()
        ).model_copy(update={"replays_per_month": None})
        unknown = decide(
            changed.benchmark,
            cost_reports(unknown_request, changed.benchmark),
            unknown_request.policy,
        )
        assert unknown.outcome == "insufficient_evidence"
        (args.output_dir / "s08-unknown-usage-decision.json").write_text(
            unknown.model_dump_json(indent=2)
        )
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    result = {
        "verified_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "package": "extracted wheel imported outside repository",
        "cases": records,
        "resume_unchanged_checkpoints": cached_before == cached_after,
        "source_sha256": before,
        "source_unchanged": True,
        "boundary": "Actual local Docker query observations plus synthetic amplified prices. "
        "No live provider, cloud/native-scan, production or customer savings validation.",
    }
    (args.output_dir / "s08-verification-results.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "verified_cases": len(records),
                "resume_reused": True,
                "source_unchanged": True,
            }
        )
    )


if __name__ == "__main__":
    main()
