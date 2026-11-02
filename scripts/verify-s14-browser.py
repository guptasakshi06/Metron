"""Run every implemented browser story sequentially in one isolated local stack."""

import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    main = runpy.run_path(str(ROOT / "scripts/verify-s11-browser.py"))["main"]
    # Playwright runs all specs, one worker. Their IDs/fixtures are independent.
    code = main(prefix="s14", spec=".*\\.spec\\.ts")
    (ROOT / "docs/evidence/s14-run-status.json").write_text(
        json.dumps({"exit_code": code, "isolated_resources_cleaned": True}) + "\n"
    )
    print(f"Integrated browser exit={code}; isolated resources cleaned.", flush=True)
    raise SystemExit(code)
