"""Local-first CLI: explicit review fingerprint required for optional network transfer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from data_optimizer.profiling.models import ProfileOptions
from data_optimizer.profiling.service import profile_file, read_report, write_report
from data_optimizer.readers.stream import ProfileError


def add_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    local = commands.add_parser("profile", help="profile locally; never uploads or calls an API")
    local.add_argument("input", type=Path)
    local.add_argument("--format", choices=("csv", "ndjson", "parquet"), required=True)
    local.add_argument("--output", type=Path, required=True)
    local.add_argument(
        "--options", type=Path, help="JSON ProfileOptions overrides (review locally)"
    )
    local.add_argument("--cache", type=Path)
    review = commands.add_parser(
        "profile-review", help="validate metadata and show review fingerprint"
    )
    review.add_argument("report", type=Path)
    importer = commands.add_parser(
        "profile-import", help="validate/store metadata; optionally upload"
    )
    importer.add_argument("report", type=Path)
    importer.add_argument("--store", type=Path, help="local metadata store directory")
    importer.add_argument("--api-url", help="explicit base URL; sends only reviewed metadata")
    importer.add_argument("--project-id", type=UUID)
    importer.add_argument("--reviewed-fingerprint", help="fingerprint of the report you reviewed")
    importer.add_argument("--local-identity", choices=("alice", "bob"), default="alice")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.command == "profile":
            if args.output.resolve() == args.input.resolve():
                raise ProfileError("output_must_preserve_source")
            supplied = json.loads(args.options.read_text()) if args.options else {}
            supplied["format"] = args.format
            options = ProfileOptions.model_validate(supplied)
            report = profile_file(args.input, options, args.cache)
            write_report(args.output, report)
            print(
                f"Local metadata exported: {args.output}; no network transfer. "
                "Review the entire report before optional import."
            )
        else:
            report = read_report(args.report)
            if args.command == "profile-review":
                print(
                    f"Rows: {report.row_count}; profiled: {report.profiled_rows}; "
                    f"columns: {len(report.columns)}; evidence: {report.evidence}\n"
                    "Review the JSON for sensitive metadata. "
                    "Raw data was not inspected by a server.\n"
                    f"Review fingerprint: {report.profile_fingerprint}"
                )
            elif args.api_url:
                if not args.project_id or args.reviewed_fingerprint != report.profile_fingerprint:
                    raise ProfileError("matching_review_fingerprint_and_project_required")
                from urllib.parse import urlsplit

                url = urlsplit(args.api_url)
                # Local identity is never sent to a remote host.
                if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1"):
                    raise ProfileError("cli_import_requires_loopback_api")
                if (
                    url.username
                    or url.password
                    or url.query
                    or url.fragment
                    or url.path not in ("", "/")
                ):
                    raise ProfileError("invalid_api_url")
                import httpx

                try:
                    response = httpx.post(
                        f"{args.api_url.rstrip('/')}/v1/projects/{args.project_id}/profiles",
                        json={
                            "report": report.model_dump(mode="json"),
                            "reviewed_fingerprint": args.reviewed_fingerprint,
                        },
                        headers={"X-Local-Identity": args.local_identity},
                        timeout=30,
                        follow_redirects=False,
                        trust_env=False,
                    )
                except httpx.TransportError:
                    raise ProfileError("metadata_api_unreachable") from None
                if response.status_code != 201:
                    raise ProfileError(f"metadata_import_http_{response.status_code}")
                print(json.dumps(response.json(), sort_keys=True))
            elif args.store:
                destination = args.store / f"{report.profile_fingerprint}.json"
                if destination.resolve() == args.report.resolve():
                    raise ProfileError("store_must_differ_from_source")
                write_report(destination, report)
                print(f"Validated local metadata stored at {destination}; no server inspection.")
            else:
                raise ProfileError("choose_local_store_or_explicit_api")
    except (OSError, ValueError):
        # Do not echo exceptions from parsers/Pydantic: they may contain raw values or paths.
        import sys

        error = sys.exception()
        parser.exit(
            2, f"Profile failed: {error if isinstance(error, ProfileError) else 'invalid_input'}.\n"
        )
