"""Real extracted-wheel export, migration, assessment reproduction and mismatch rejection."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence"


def main() -> None:
    wheel = next((ROOT / "backend/dist").glob("*.whl"))
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="s12-package-") as temporary:
        directory = Path(temporary)
        package = directory / "package"
        with zipfile.ZipFile(wheel) as zipped:
            zipped.extractall(package)
        env = {
            **os.environ,
            "PYTHONPATH": str(package),
            "PATH": str(Path(sys.executable).parent) + ":" + os.environ["PATH"],
        }
        cli = [sys.executable, "-m", "data_optimizer.cli"]

        def run(
            label: str, arguments: list[str], expected: int = 0
        ) -> subprocess.CompletedProcess:
            result = subprocess.run(
                arguments,
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if result.returncode != expected:
                raise RuntimeError(
                    f"{label} exit={result.returncode}; {result.stderr[-1500:]}"
                )
            results.append({"case": label, "exit_code": result.returncode})
            return result

        report = EVIDENCE / "s12-measured-change-report.json"
        export = directory / "export ' $(touch BAD) `touch BAD`"
        source = directory / "source ' $(touch BAD) `touch BAD`.ndjson"
        source.write_bytes((ROOT / "examples/s04-events.ndjson").read_bytes())
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        run(
            "export",
            cli + ["export", "--report", str(report), "--output-dir", str(export)],
        )
        run(
            "immutable_export",
            cli + ["export", "--report", str(report), "--output-dir", str(export)],
            2,
        )
        run(
            "quoted_migration_script",
            [
                "sh",
                str(export / "migrate.sh"),
                str(source),
                str(directory / "migration"),
                str(directory / "migration.json"),
            ],
        )
        migration = json.loads((directory / "migration.json").read_bytes())
        assert (
            migration["source_preserved"]
            and not migration["production_reader_switched"]
        )
        assert migration["outcome"]["manifest"]["integrity"]["status"] == "passed"
        run(
            "reproduce_assessment",
            cli
            + [
                "reproduce",
                str(export / "bundle.json"),
                "--source",
                str(source),
                "--root",
                str(directory / "replay"),
                "--output",
                str(directory / "replay.json"),
            ],
        )
        replay = json.loads((directory / "replay.json").read_bytes())
        assert replay["matches_original_decision"] and replay["source_preserved"]
        assert replay["report"]["decision"]["outcome"] == "change"
        assert all(
            t["status"] == "passed" for t in replay["report"]["benchmark"]["trials"]
        )
        source.write_text('{"wrong":"source"}\n')
        mismatch = run(
            "mismatched_source",
            cli
            + [
                "reproduce",
                str(export / "bundle.json"),
                "--source",
                str(source),
                "--root",
                str(directory / "bad-work"),
                "--output",
                str(directory / "bad.json"),
            ],
            2,
        )
        assert "source_fingerprint_mismatch" in mismatch.stderr
        assert (
            not (directory / "bad-work").exists()
            and not (directory / "bad.json").exists()
        )
        assert not (directory / "BAD").exists()
        export_evidence = EVIDENCE / "s12-export"
        export_evidence.mkdir(exist_ok=True)
        for path in export.iterdir():
            shutil.copyfile(path, export_evidence / path.name)
        (EVIDENCE / "s12-reproduced-report.json").write_text(
            json.dumps(replay, indent=2) + "\n"
        )
        (EVIDENCE / "s12-migration-result.json").write_text(
            json.dumps(
                {
                    "source_preserved": migration["source_preserved"],
                    "production_reader_switched": migration[
                        "production_reader_switched"
                    ],
                    "manifest": migration["outcome"]["manifest"],
                },
                indent=2,
            )
            + "\n"
        )
        result = {
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "source_sha256": original,
            "cases": results,
            "package_outside_repository": True,
            "temporary_resources_removed_on_exit": True,
            "outcome": replay["report"]["decision"]["outcome"],
            "measured_trials": len(replay["report"]["benchmark"]["trials"]),
            "bundle_fingerprint": replay["bundle"],
        }
    (EVIDENCE / "s12-package-results.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
