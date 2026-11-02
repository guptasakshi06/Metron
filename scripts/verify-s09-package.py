"""Verify shipped commands/migrations outside the editable source tree."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheel = root / "backend/dist/data_optimizer-0.1.0-py3-none-any.whl"
with tempfile.TemporaryDirectory(prefix="s09-packaged-") as name:
    directory = Path(name)
    with zipfile.ZipFile(wheel) as package:
        package.extractall(directory / "package")
    environment = dict(os.environ, PYTHONPATH=str(directory / "package"))
    for command in ("worker", "dispatch-jobs", "cleanup-assessments", "job-metrics"):
        result = subprocess.run(
            [sys.executable, "-m", "data_optimizer.cli", command, "--help"],
            cwd=directory,
            env=environment,
            capture_output=True,
            check=True,
        )
        assert b"usage:" in result.stdout
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            ("from data_optimizer.db.migrations import migration_files; "
             "print(len(migration_files()))"),
        ],
        cwd=directory,
        env=environment,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == b"5"
    summary = {
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "outside_repository_cli_commands": 4,
        "packaged_migrations": 5,
        "status": "passed",
    }
    (root / "docs/evidence/s09-package-results.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary))
