"""Export saved assessment evidence and reproduce it against a user-local source."""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from data_optimizer.migration.service import reproduce
from data_optimizer.optimization.assessment import AssessmentReport
from data_optimizer.reports.service import export_files, make_bundle, read_bundle


def add_commands(commands: Any) -> None:
    export = commands.add_parser("export", help="export a saved assessment into a new directory")
    export.add_argument("--report", type=Path, required=True)
    export.add_argument("--output-dir", type=Path, required=True)
    replay = commands.add_parser("reproduce", help="verify input and reproduce a portable bundle")
    replay.add_argument("bundle", type=Path)
    replay.add_argument("--source", type=Path, required=True)
    replay.add_argument("--root", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--mode", choices=("assessment", "migration"), default="assessment")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.command == "export":
            if args.report.stat().st_size > 67_108_864:
                raise ValueError("report_byte_quota")
            bundle = make_bundle(AssessmentReport.model_validate_json(args.report.read_bytes()))
            # No overwrite or cleanup of an existing user directory.
            args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
            for name, content in export_files(bundle).items():
                with (args.output_dir / name).open("xb") as stream:
                    stream.write(content)
            print(f"Exported bundle: {args.output_dir / 'bundle.json'}")
            return
        if args.bundle.stat().st_size > 67_108_864:
            raise ValueError("bundle_byte_quota")
        bundle = read_bundle(args.bundle.read_bytes())
        if (
            args.output.exists()
            or args.output.is_symlink()
            or args.output.resolve().is_relative_to(args.root.resolve())
            or args.bundle.resolve().is_relative_to(args.root.resolve())
            or args.output.resolve() in {args.source.resolve(), args.bundle.resolve()}
        ):
            raise ValueError("new_output_outside_workspace_required")
        # Reserve the output first so incompatible destinations cannot start expensive work.
        with args.output.open("x", encoding="utf-8") as stream:
            try:
                result = reproduce(
                    bundle, args.source, args.root, migration=args.mode == "migration"
                )
            except Exception:
                args.output.unlink(missing_ok=True)
                raise
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(f"Reproduction: {args.output}")
        if result.get("matches_original_decision") is False:
            parser.exit(1, "Reproduction decision differs; inspect saved evidence.\n")
    except (
        OSError,
        ValueError,
        ArithmeticError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        safe_codes = {
            "source_fingerprint_mismatch",
            "execution_context_mismatch",
            "benchmark_environment_mismatch",
            "workload_or_manifest_fingerprint_mismatch",
            "bundle_fingerprint_mismatch",
            "assessment_report_fingerprint_mismatch",
            "guidance_has_no_executable_raw_evidence",
            "only_tested_change_has_migration",
            "selected_configuration_not_verified_feasible",
            "selected_manifest_missing",
            "migration_conversion_or_integrity_failed",
            "new_workspace_required",
            "new_output_outside_workspace_required",
            "bundle_byte_quota",
            "report_byte_quota",
        }
        reason = str(error) if str(error) in safe_codes else type(error).__name__
        parser.exit(
            2,
            f"Export/reproduction failed: {reason}; check input, matching engines and new paths.\n",
        )
