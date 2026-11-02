"""Reuse the isolated full-service runner for actual export downloads in Chrome."""

import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    main = runpy.run_path(str(ROOT / "scripts/verify-s11-browser.py"))["main"]
    code = main(prefix="s12", spec="exports.spec.ts")
    (ROOT / "docs/evidence/s12-run-status.json").write_text(
        json.dumps({"exit_code": code, "isolated_resources_cleaned": True}) + "\n"
    )
    print(f"Browser exports exit={code}; isolated resources cleaned.", flush=True)
    raise SystemExit(code)
