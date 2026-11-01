from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from data_optimizer.config import Settings
from data_optimizer.profiling.models import ProfileOptions
from data_optimizer.profiling.service import profile_file

pytestmark = pytest.mark.integration


def metadata(tmp_path: Path) -> dict:
    path = tmp_path / "local.csv"
    path.write_text("private_id,amount\n0001,123.000000000001\n0001,123.000000000001\n")
    report = profile_file(path, ProfileOptions(format="csv"))
    return {
        "report": report.model_dump(mode="json"),
        "reviewed_fingerprint": report.profile_fingerprint,
    }


def test_import_versions_ownership_deletion_and_provenance(
    services: tuple[Settings, TestClient],
    tmp_path: Path,
) -> None:
    config, client = services
    project_id = client.post("/v1/projects", json={"name": "Local metadata"}).json()["project_id"]
    base = f"/v1/projects/{project_id}/profiles"
    payload = metadata(tmp_path)
    imported = client.post(base, json=payload)
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["profile_version"] == 1
    assert body["raw_data_inspected_by_server"] is False
    assert body["evidence"] == "local_profile"
    profile_id = body["profile_id"]
    read = client.get(f"{base}/{profile_id}").json()
    assert read["report"] == payload["report"]
    assert len(client.get(base).json()["items"]) == 1
    assert client.post(base, json=payload).json()["reused"] is True
    bob = {"X-Local-Identity": "bob"}
    assert client.post(base, json=payload, headers=bob).status_code == 404
    assert client.get(base, headers=bob).status_code == 404
    assert client.get(f"{base}/{profile_id}", headers=bob).status_code == 404
    assert client.delete(f"{base}/{profile_id}", headers=bob).status_code == 404
    other = client.post("/v1/projects", json={"name": "Other"}, headers=bob).json()["project_id"]
    assert client.get(f"/v1/projects/{other}/profiles/{profile_id}", headers=bob).status_code == 404
    assert client.delete(f"{base}/{profile_id}").status_code == 200
    assert client.get(f"{base}/{profile_id}").status_code == 404
    assert client.post(base, json=payload).status_code == 409
    with psycopg.connect(str(config.database_url)) as connection:
        assert (
            connection.execute(
                "SELECT payload FROM profiles WHERE id = %s", (profile_id,)
            ).fetchone()[0]
            == {}
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM audit_events WHERE resource_id = %s", (profile_id,)
            ).fetchone()[0]
            == 2
        )
        assert connection.execute("SELECT count(*) FROM datasets").fetchone()[0] == 0
    # New settings create a distinct, immutable version of the same input.
    path = tmp_path / "local.csv"
    report = profile_file(path, ProfileOptions(format="csv", seed=2))
    result = client.post(
        base,
        json={
            "report": report.model_dump(mode="json"),
            "reviewed_fingerprint": report.profile_fingerprint,
        },
    )
    assert result.json()["profile_version"] == 2
    assert client.delete(f"/v1/projects/{project_id}").status_code == 202
    assert client.get(base).status_code == 404
    assert client.get(f"{base}/{result.json()['profile_id']}").status_code == 404
    with psycopg.connect(str(config.database_url)) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM profiles WHERE payload <> '{}'::jsonb"
            ).fetchone()[0]
            == 0
        )


def test_import_validation_review_and_size_bounds(
    services: tuple[Settings, TestClient],
    tmp_path: Path,
) -> None:
    _, client = services
    project = client.post("/v1/projects", json={"name": "Validation"}).json()["project_id"]
    base = f"/v1/projects/{project}/profiles"
    payload = metadata(tmp_path)
    assert client.post(base, json={"report": payload["report"]}).status_code == 422
    assert client.post(base, json={**payload, "reviewed_fingerprint": "0" * 64}).status_code == 422
    payload["report"]["row_count"] = 0
    assert client.post(base, json=payload).status_code == 422
    payload = metadata(tmp_path)
    payload["report"]["raw_data_inspected_by_server"] = True
    assert client.post(base, json=payload).status_code == 422
    payload = metadata(tmp_path)
    payload["report"]["raw_records"] = [{"private": "secret"}]
    response = client.post(base, json=payload)
    assert response.status_code == 422
    assert "secret" not in response.text
    assert client.post(base, content=b" " * 2_097_153).status_code == 413
    assert client.get(base).json()["items"] == []
    assert (
        client.post(f"/v1/projects/{uuid4()}/profiles", json=metadata(tmp_path)).status_code == 404
    )


def test_profile_quota(services: tuple[Settings, TestClient], tmp_path: Path) -> None:
    config, client = services
    # Keep production default; use a separate app instance with a reduced quota.
    from data_optimizer.api.main import create_app

    limited = config.model_copy(update={"max_profiles_per_project": 1})
    client = TestClient(create_app(limited), client=("127.0.0.1", 12345))
    project = client.post("/v1/projects", json={"name": "Quota"}).json()["project_id"]
    base = f"/v1/projects/{project}/profiles"
    first = metadata(tmp_path)
    assert client.post(base, json=first).status_code == 201
    assert client.post(base, json=first).json()["reused"] is True
    report = profile_file(tmp_path / "local.csv", ProfileOptions(format="csv", seed=2))
    assert (
        client.post(
            base,
            json={
                "report": report.model_dump(mode="json"),
                "reviewed_fingerprint": report.profile_fingerprint,
            },
        ).status_code
        == 429
    )
