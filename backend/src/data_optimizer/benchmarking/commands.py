"""Offline benchmark CLI over explicit allowlisted conversion directories."""

import argparse
import subprocess
from pathlib import Path
from typing import Any

from data_optimizer.benchmarking.models import BenchmarkRequest
from data_optimizer.benchmarking.service import benchmark, write_report


def add_commands(commands: Any) -> None:
    parser = commands.add_parser("benchmark", help="benchmark verified local conversion manifests")
    parser.add_argument(
        "artifacts", nargs="+", type=Path, help="directories containing manifest.json"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new immutable JSON report")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.request.stat().st_size > 65536:
            raise ValueError("benchmark_request_byte_quota")
        request = BenchmarkRequest.model_validate_json(args.request.read_bytes())
        report = benchmark(tuple(args.artifacts), request)
        write_report(args.output, report, tuple(args.artifacts))
        print(f"Benchmark evidence: {args.output}; stop reason: {report.stop_reason}")
        if any(t.status != "passed" for t in report.trials):
            parser.exit(1)
    except (OSError, ValueError, subprocess.SubprocessError):
        parser.exit(
            2, "Benchmark could not complete; check inputs, new output path and Docker image.\n"
        )
    except KeyboardInterrupt:
        parser.exit(130, "Benchmark cancelled; active container and private snapshots removed.\n")
