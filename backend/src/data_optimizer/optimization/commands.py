"""One offline-capable assessment CLI; immutable output and explicit scenario mode."""

import argparse
from pathlib import Path
from typing import Any

from data_optimizer.benchmarking.service import write_report
from data_optimizer.optimization.assessment import AssessmentRequest, assess


def add_commands(commands: Any) -> None:
    parser = commands.add_parser("assess", help="profile, test and rank local analytical copies")
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("--metadata", type=Path, help="reviewable metadata only; no savings claim")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument(
        "--root", required=True, type=Path, help="private resumable local workspace"
    )
    parser.add_argument("--output", required=True, type=Path, help="new immutable JSON report")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.request.stat().st_size > 4_194_304:
            raise ValueError("assessment_request_byte_quota")
        request = AssessmentRequest.model_validate_json(args.request.read_bytes())
        sources = tuple(p for p in (args.source, args.metadata, args.request) if p)
        if (
            args.output.exists()
            or args.output.is_symlink()
            or any(args.output.resolve() == p.resolve() for p in sources)
            or args.output.resolve().is_relative_to(args.root.resolve())
        ):
            raise ValueError("new_output_outside_workspace_required")
        report = assess(args.source, args.root, request, metadata=args.metadata)
        write_report(args.output, report, sources + (args.root,))
        print(f"Assessment: {args.output}; {report.decision.outcome}")
        if report.decision.outcome == "insufficient_evidence":
            parser.exit(1)
    except (OSError, ValueError, ArithmeticError, RuntimeError) as error:
        parser.exit(
            2,
            f"Assessment failed: {type(error).__name__}; "
            "check local Docker, input, request and new output path.\n",
        )
