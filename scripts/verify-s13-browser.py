"""Run real services and synthetic adoption/observation browser reconciliation."""
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    main = runpy.run_path(str(ROOT / "scripts/verify-s11-browser.py"))["main"]
    code = main(prefix="s13", spec="observations.spec.ts")
    (ROOT / "docs/evidence/s13-run-status.json").write_text(
        json.dumps({"exit_code": code, "isolated_resources_cleaned": True}) + "\n"
    )
    print(f"Observations browser exit={code}; isolated resources cleaned.", flush=True)
    raise SystemExit(code)
