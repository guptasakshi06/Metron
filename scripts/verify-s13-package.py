"""Verify observation contracts, owned routes and migration from an extracted wheel."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wheel = ROOT / "backend/dist/data_optimizer-0.1.0-py3-none-any.whl"
with tempfile.TemporaryDirectory(prefix="s13-package-") as name:
    path = Path(name)
    with zipfile.ZipFile(wheel) as package:
        package.extractall(path / "package")
    code = '''
import hashlib
import json
from pathlib import Path
import data_optimizer
from data_optimizer.api.main import create_app
from data_optimizer.config import Settings
from data_optimizer.db.migrations import migration_files
from data_optimizer.observations.models import ObservationInput, PlanInput
from data_optimizer.observations.service import evaluate
assert Path(data_optimizer.__file__).resolve().is_relative_to(Path.cwd())
files = migration_files()
assert len(files) == 8
name, sql, digest = files[-1]
assert name == "0008_observations.sql"
assert hashlib.sha256(sql.encode()).hexdigest() == digest
assert "immutable_observations" in sql
paths = set(create_app(Settings(llm_provider="disabled")).openapi()["paths"])
expected = {
    "/v1/assessments/{assessment_id}/migration-plan",
    "/v1/migration-plans/{plan_id}/observations",
    "/v1/migration-plans/{plan_id}/history",
    "/v1/assessments/{assessment_id}/comparison",
}
assert expected <= paths
assert "reference_logical_bytes" in PlanInput.model_json_schema()["properties"]
assert "itemized_costs" in ObservationInput.model_json_schema()["properties"]
assert callable(evaluate)
print(json.dumps({"status": "passed", "packaged_migrations": len(files),
                  "migration_sha256": digest, "owned_history_routes": sorted(expected)}))
'''
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=path, check=False, text=True, capture_output=True,
        env=dict(os.environ, PYTHONPATH=str(path / "package"), LLM_PROVIDER="disabled"),
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    report = json.loads(result.stdout)
    report["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (ROOT / "docs/evidence/s13-package-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report))
