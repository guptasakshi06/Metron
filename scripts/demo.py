"""Packaged measured decision, portable report and independent reproduction demo."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/verify-s08.py"),
            "--output-dir",
            str(output),
        ],
        check=True,
        timeout=600,
    )
    with tempfile.TemporaryDirectory(prefix="s14-demo-package-") as temporary:
        directory = Path(temporary)
        with zipfile.ZipFile(next((ROOT / "backend/dist").glob("*.whl"))) as wheel:
            wheel.extractall(directory / "package")
        env = dict(os.environ, PYTHONPATH=str(directory / "package"))
        cli = [sys.executable, "-m", "data_optimizer.cli"]
        subprocess.run(
            cli
            + [
                "export",
                "--report",
                str(output / "s08-change.json"),
                "--output-dir",
                str(output / "handoff"),
            ],
            cwd=directory,
            env=env,
            check=True,
            timeout=30,
        )
        subprocess.run(
            cli
            + [
                "reproduce",
                str(output / "handoff/bundle.json"),
                "--source",
                str(ROOT / "examples/s04-events.ndjson"),
                "--root",
                str(directory / "fresh-workspace"),
                "--output",
                str(output / "reproduced.json"),
            ],
            cwd=directory,
            env=env,
            check=True,
            timeout=300,
        )
        reproduced = json.loads((output / "reproduced.json").read_text())
        assert (
            reproduced["matches_original_decision"] and reproduced["source_preserved"]
        )
    print(
        json.dumps(
            {
                "demo": "passed",
                "evidence_dir": str(output),
                "report": str(output / "handoff/report.html"),
                "pricing": "invented synthetic fixture; not live or customer savings",
            }
        )
    )


if __name__ == "__main__":
    main()
