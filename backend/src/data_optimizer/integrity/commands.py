"""Local integrity CLI; sources are user-chosen copies, never DSL-controlled paths."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from data_optimizer.integrity.models import VerificationRequest
from data_optimizer.integrity.service import verify_files, write_evidence


def add_commands(commands: Any) -> None:
    parser = commands.add_parser(
        "integrity-check", help="compare dataset meaning and workload outputs"
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--request", type=Path, required=True, help="reviewed reader/workload JSON")
    parser.add_argument("--output", type=Path, required=True, help="local evidence JSON")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with args.request.open("rb") as source:
            data = source.read(262_145)
        if len(data) > 262_144:
            raise ValueError("request_byte_quota")
        request = VerificationRequest.model_validate_json(data)
        report = verify_files(args.baseline, args.candidate, request)
        write_evidence(args.output, report, (args.baseline, args.candidate, args.request))
    except (ValueError, OSError):
        parser.exit(
            2, "Integrity check could not complete; review inputs, schema and resource limits.\n"
        )
    print(f"Integrity {report.status}; performance not measured. Evidence: {args.output}")
    if report.status != "passed":
        parser.exit(1)
