"""Import structured assistance from the built wheel outside the source checkout."""
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
with tempfile.TemporaryDirectory(prefix="s11-package-") as name:
    path = Path(name)
    with zipfile.ZipFile(wheel) as package:
        package.extractall(path / "package")
    code = '''
import json
from pathlib import Path
import data_optimizer
from data_optimizer.api.main import create_app
from data_optimizer.config import Settings
from data_optimizer.db.migrations import migration_files
from data_optimizer.intake.models import IntakeSelection
from data_optimizer.llm.provider import provider_payload
assert Path(data_optimizer.__file__).resolve().is_relative_to(Path.cwd())
config = Settings(llm_provider="disabled", llm_api_key=None)
assert len(migration_files()) == 6
paths = set(create_app(config).openapi()["paths"])
assert "/v1/projects/{project_id}/intake/{proposal_id}/confirm" in paths
assert "/v1/assessments/{assessment_id}/explanation" in paths
payload = provider_payload(config, {"allowed_fields": []}, IntakeSelection)
assert payload["text"]["format"]["strict"] is True
assert payload["tools"] == [] and payload["store"] is False
print(json.dumps({"status": "passed", "packaged_migrations": 6,
                  "model": config.llm_model, "assistance_routes": True}))
'''
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=path, check=False, text=True, capture_output=True,
        env=dict(os.environ, PYTHONPATH=str(path / "package"), LLM_PROVIDER="disabled"),
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    report = json.loads(result.stdout)
    report["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (ROOT / "docs/evidence/s11-package-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
