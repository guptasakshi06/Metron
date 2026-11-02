"""Run CI contracts in a temporary source copy with fresh Python/npm dependencies.

Only verified tool binaries and package-download caches are shared. No source-tree
venv, node_modules, generated dist, .env or metadata/object database is copied.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tracked = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    results = []
    with tempfile.TemporaryDirectory(prefix="s14-clean-") as temporary:
        checkout = Path(temporary)
        for name in set(tracked) - {""}:
            source = ROOT / name
            # Unit tests intentionally consume committed historical measurement fixtures;
            # the fresh demo produces all its own measurements and exports independently.
            if not source.is_file() or (
                name.startswith("docs/evidence/")
                and (not name.endswith(".json") or "/s14" in name)
            ):
                continue
            target = checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        (checkout / "docs/evidence").mkdir(parents=True, exist_ok=True)
        (checkout / ".tools").mkdir()
        for cache in ("node24", "uv-bin", "uv-cache", "npm-cache"):
            (checkout / ".tools" / cache).symlink_to(ROOT / ".tools" / cache)
        env = dict(os.environ, UV_OFFLINE="0", npm_config_offline="false")
        env.pop("VIRTUAL_ENV", None)
        commands = [
            ["make", "setup-deps"],
            ["make", "check"],
            ["make", "test"],
            ["make", "build"],
        ]
        if args.demo:
            commands.append(["make", "demo"])
        for index, command in enumerate(commands):
            log_path = args.output_dir / f"clean-{index}-{command[1]}.log"
            with log_path.open("w") as log:
                outcome = subprocess.run(
                    command,
                    check=False,
                    cwd=checkout,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=900,
                )
            results.append(
                {
                    "command": command[:2],
                    "exit_code": outcome.returncode,
                    "log": log_path.name,
                }
            )
            print(json.dumps(results[-1]), flush=True)
            if outcome.returncode:
                raise RuntimeError(f"Clean check failed; inspect {log_path}")
        assert (checkout / "backend/.venv").is_dir()
        assert not (checkout / "backend/.venv").is_symlink()
        assert (checkout / "frontend/node_modules").is_dir()
        assert not (checkout / "frontend/node_modules").is_symlink()
    (args.output_dir / "clean-results.json").write_text(
        json.dumps(
            {
                "fresh_dependency_directories": True,
                "shared": "tool binaries and download caches only",
                "environment": "temporary current-source copy; locked install with fresh dependency directories",
                "commands": results,
                "passed": True,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
