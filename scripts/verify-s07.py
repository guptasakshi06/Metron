"""Verify the packaged offline cost CLI and reconcile saved S06 sample evidence."""

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

from data_optimizer.benchmarking.models import BenchmarkReport
from data_optimizer.economics.models import CostReport
from data_optimizer.profiling.models import fingerprint

REPO = Path(__file__).resolve().parents[1]


def decimal_or_null(value: object) -> str | None:
    return str(value) if value is not None else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fixture = REPO / "examples/s07-cost-request.json"
    measured = REPO / "docs/evidence/s06-benchmark-fresh.json"
    sources = (fixture, measured, REPO / "examples/s07-synthetic-prices.json")
    before = {
        str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sources
    }
    benchmark = BenchmarkReport.model_validate_json(measured.read_bytes())
    candidate = next(m for m in benchmark.manifests if not m.configuration.baseline)
    records = []
    with tempfile.TemporaryDirectory(prefix="verify-s07-") as temporary:
        root = Path(temporary)
        wheels = list((REPO / "backend/dist").glob("*.whl"))
        assert len(wheels) == 1, "Run make build first"
        wheel_root = root / "wheel"
        with zipfile.ZipFile(wheels[0]) as wheel:
            wheel.extractall(wheel_root)
        assert (wheel_root / "data_optimizer/economics/service.py").is_file()
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
        base = [
            sys.executable,
            "-m",
            "data_optimizer.cli",
            "cost",
            "--request",
            str(fixture),
        ]
        binding = ["--benchmark", str(measured), "--candidate", candidate.key]
        for label, extra, exit_code in (
            ("synthetic", [], 0),
            ("benchmark", [*binding, "--replays-per-month", "10000"], 0),
            ("unknown-usage", binding, 1),
        ):
            output = root / f"{label}.json"
            command = [*base, *extra, "--output", str(output)]
            outcome = subprocess.run(
                command,
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert outcome.returncode == exit_code, outcome.stderr
            report = CostReport.model_validate_json(output.read_bytes())
            assert report.report_fingerprint == fingerprint(
                report.model_dump(mode="json", exclude={"report_fingerprint"})
            )
            result = report.results[0]
            if label == "synthetic":
                assert (
                    result.baseline.total,
                    result.candidate.total,
                    result.migration_forecast.total,
                    result.payback_months,
                    result.horizon_net_savings,
                ) == (300, 180, 300, 2.5, 1140)
            elif label == "benchmark":
                assert result.space.baseline_physical_bytes == 287
                assert result.space.candidate_physical_bytes == candidate.physical_bytes
                assert result.candidate.total is not None
                for costs in (
                    result.baseline,
                    result.candidate,
                    result.migration_forecast,
                ):
                    assert costs.total == sum(line.amount for line in costs.items)
            else:
                assert result.candidate.total is result.monthly_savings is None
                assert result.payback_months is None
            original = output.read_bytes()
            repeated = subprocess.run(
                command,
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert repeated.returncode == 2 and output.read_bytes() == original
            shutil.copyfile(output, args.output_dir / f"s07-{label}-cost.json")
            records.append(
                {
                    "case": label,
                    "exit_code": outcome.returncode,
                    "overwrite_exit": repeated.returncode,
                    "report_fingerprint": report.report_fingerprint,
                    "baseline_total": decimal_or_null(result.baseline.total),
                    "candidate_total": decimal_or_null(result.candidate.total),
                    "migration_forecast": decimal_or_null(result.migration_forecast.total),
                    "monthly_savings": decimal_or_null(result.monthly_savings),
                    "payback_months": decimal_or_null(result.payback_months),
                    "horizon_net_savings": decimal_or_null(result.horizon_net_savings),
                    "missing_inputs": result.missing_inputs,
                }
            )
    after = {
        str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sources
    }
    assert before == after
    evidence = {
        "verified_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "package": "extracted wheel imported outside repository",
        "records": records,
        "source_hashes": after,
        "benchmark_report_fingerprint": benchmark.report_fingerprint,
        "boundary": "Offline cost calculation over saved S06 measurements; no new Docker run, "
        "live provider, invoice, production or customer validation.",
    }
    (args.output_dir / "s07-verification-results.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print(
        json.dumps(
            {"verified_cases": len(records), "source_files_unchanged": before == after}
        )
    )


if __name__ == "__main__":
    main()
