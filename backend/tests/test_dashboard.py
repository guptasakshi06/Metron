"""Discovery has no secrets and preflight validates actual executable contracts."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from data_optimizer.api.main import create_app
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings


def test_config_exposes_only_public_processing_settings():
    client = TestClient(create_app(Settings()))
    response = client.get("/v1/dashboard/config")
    assert response.status_code == 200
    assert set(response.json()) == {
        "version",
        "auth_mode",
        "max_raw_upload_bytes",
        "max_decompressed_bytes",
        "default_retention_days",
    }
    assert response.json()["auth_mode"] == "local"


def test_preflight_validates_real_contract_and_redacts_values(monkeypatch):
    import data_optimizer.auth.dependencies as auth

    monkeypatch.setattr(
        auth,
        "authenticate",
        lambda *args: Identity(
            tenant_id="10000000-0000-0000-0000-000000000001",
            principal_id="20000000-0000-0000-0000-000000000001",
            issuer="local-demo",
            subject="alice",
        ),
    )
    client = TestClient(create_app(Settings()), client=("127.0.0.1", 1234))
    request = json.loads(
        (Path(__file__).parents[2] / "examples/s08-assessment-request.json").read_text()
    )
    result = client.post("/v1/dashboard/validate", json=request)
    assert result.status_code == 200
    assert result.json()["valid"] is True
    request["conversion"]["workload"]["queries"] = [
        {"id": "bad", "kind": "projection", "columns": []}
    ]
    result = client.post("/v1/dashboard/validate", json=request)
    assert result.json()["valid"] is False
    assert result.json()["issues"] == [
        {"path": "conversion.workload.queries.0", "code": "value_error"}
    ]
    assert "bad" not in result.text
    assert client.post("/v1/dashboard/validate", content=b"x" * 524289).status_code == 413
