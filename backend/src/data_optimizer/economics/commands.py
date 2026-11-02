"""Offline economics CLI: strict inputs, new-file publication and explicit missing values."""

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Any

from data_optimizer.benchmarking.models import BenchmarkReport
from data_optimizer.benchmarking.service import write_report
from data_optimizer.economics.benchmark import bind_benchmark
from data_optimizer.economics.models import CostRequest
from data_optimizer.economics.service import calculate


def add_commands(commands: Any) -> None:
    parser = commands.add_parser("cost", help="calculate itemized offline cost scenarios")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new immutable JSON report")
    parser.add_argument("--benchmark", type=Path, help="optional saved S06 benchmark report")
    parser.add_argument(
        "--candidate", help="selected alternative manifest key, requires --benchmark"
    )
    parser.add_argument("--replays-per-month", type=Decimal, help="explicit sample workload usage")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.request.stat().st_size > 4_194_304:
            raise ValueError("cost_request_byte_quota")
        request = CostRequest.model_validate_json(args.request.read_bytes())
        sources = [args.request]
        if bool(args.benchmark) != bool(args.candidate) or (
            args.replays_per_month is not None and not args.benchmark
        ):
            raise ValueError("benchmark_candidate_pair_required")
        if args.benchmark:
            if args.benchmark.stat().st_size > 67_108_864:
                raise ValueError("benchmark_report_byte_quota")
            benchmark = BenchmarkReport.model_validate_json(args.benchmark.read_bytes())
            request = bind_benchmark(request, benchmark, args.candidate, args.replays_per_month)
            sources.append(args.benchmark)
        report = calculate(request)
        # Shared atomic writer accepts any frozen JSON model; source paths stay protected.
        write_report(args.output, report, tuple(sources))
        incomplete = any(r.missing_inputs for r in report.results)
        print(
            f"Cost forecast: {args.output}; {'missing inputs' if incomplete else 'complete inputs'}"
        )
        if incomplete:
            parser.exit(1)
    except (OSError, ValueError, ArithmeticError) as error:
        parser.exit(
            2,
            f"Cost calculation failed: {type(error).__name__}; "
            "check request, billing units, commitments and new output path.\n",
        )
