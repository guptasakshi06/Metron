"""Offline candidate listing and conversion CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from data_optimizer.candidates.models import CandidateConfig, ConversionRequest
from data_optimizer.conversion.service import convert, list_candidates


def add_commands(commands: Any) -> None:
    for name in ("candidate-list", "convert"):
        parser = commands.add_parser(
            name,
            help="list candidates"
            if name == "candidate-list"
            else "materialize and validate new assessment copies",
        )
        parser.add_argument("source", type=Path)
        parser.add_argument("--request", required=True, type=Path)
        if name == "convert":
            parser.add_argument("--root", required=True, type=Path, help="private artifact root")
            parser.add_argument("--configuration", type=Path, help="single CandidateConfig JSON")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.request.stat().st_size > 262_144:
            raise ValueError("request_byte_quota")
        request = ConversionRequest.model_validate_json(args.request.read_bytes())
        if args.command == "candidate-list":
            print(list_candidates(args.source, request).model_dump_json(indent=2))
            return
        if args.configuration:
            if args.configuration.stat().st_size > 65_536:
                raise ValueError("configuration_byte_quota")
            configs = [CandidateConfig.model_validate_json(args.configuration.read_bytes())]
        else:
            configs = [c.configuration for c in list_candidates(args.source, request).candidates]
        outcomes = [convert(args.source, args.root, request, config) for config in configs]
        print(
            json.dumps(
                {"version": 1, "outcomes": [o.model_dump(mode="json") for o in outcomes]}, indent=2
            )
        )
        if any(o.status in {"failed", "cancelled"} for o in outcomes):
            parser.exit(1)
    except (ValueError, OSError):
        parser.exit(2, "Conversion could not complete; review inputs, manifests and limits.\n")
    except KeyboardInterrupt:
        parser.exit(130, "Conversion cancelled; unpublished temporary outputs removed.\n")
