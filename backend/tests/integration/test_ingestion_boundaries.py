from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from httpx import Response

from data_optimizer.config import Settings

ALICE = {"X-Local-Identity": "alice"}
BOB = {"X-Local-Identity": "bob"}


def create_project(client: TestClient, headers: dict[str, str], name: str) -> str:
    response = client.post("/v1/projects", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return str(response.json()["project_id"])


def initiate_upload(
    client: TestClient,
    project_id: str,
    headers: dict[str, str],
    filename: str,
    fmt: str = "ndjson",
    data: bytes | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"format": fmt, "filename": filename}
    if data is not None:
        payload["expected_bytes"] = len(data)
        payload["sha256"] = hashlib.sha256(data).hexdigest()
    response = client.post(f"/v1/projects/{project_id}/datasets", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def transfer_and_finalize(
    client: TestClient,
    upload: dict[str, object],
    headers: dict[str, str],
    data: bytes,
) -> Response:
    transferred = client.put(str(upload["upload_url"]), headers=headers, content=data)
    assert transferred.status_code == 202, transferred.text
    return client.post(f"/v1/uploads/{upload['upload_session_id']}/finalize", headers=headers)


@pytest.mark.integration
def test_tenant_cannot_mutate_another_tenants_project_or_upload(
    services: tuple[Settings, TestClient],
) -> None:
    _config, client = services
    project_id = create_project(client, ALICE, "alice-owned")
    data = b'{"event":"alice"}\n'
    alice_upload = initiate_upload(client, project_id, ALICE, "alice.ndjson", data=data)
    session_id = str(alice_upload["upload_session_id"])
    dataset_id = str(alice_upload["dataset_id"])

    assert (
        client.post(
            f"/v1/projects/{project_id}/datasets",
            headers=BOB,
            json={"format": "ndjson", "filename": "bob.ndjson"},
        ).status_code
        == 404
    )
    assert client.put(str(alice_upload["upload_url"]), headers=BOB, content=data).status_code == 404
    assert client.post(f"/v1/uploads/{session_id}/finalize", headers=BOB).status_code == 404

    finalized = transfer_and_finalize(client, alice_upload, ALICE, data)
    assert finalized.status_code == 200, finalized.text
    assert client.delete(f"/v1/datasets/{dataset_id}", headers=BOB).status_code == 404
    assert client.delete(f"/v1/projects/{project_id}", headers=BOB).status_code == 404

    assert client.get(f"/v1/projects/{project_id}", headers=ALICE).status_code == 200
    dataset = client.get(f"/v1/datasets/{dataset_id}", headers=ALICE)
    assert dataset.status_code == 200
    assert dataset.json()["state"] == "ready"
    artifact = client.get(f"/v1/artifacts/{alice_upload['artifact_id']}/content", headers=ALICE)
    assert artifact.content == data


@pytest.mark.integration
def test_per_tenant_upload_session_quota_is_enforced_independently(
    services: tuple[Settings, TestClient],
) -> None:
    _config, client = services
    alice_project = create_project(client, ALICE, "alice-quota")
    bob_project = create_project(client, BOB, "bob-quota")

    for index in range(2):
        assert (
            initiate_upload(client, alice_project, ALICE, f"alice-{index}.ndjson")["state"]
            == "pending"
        )
    rejected = client.post(
        f"/v1/projects/{alice_project}/datasets",
        headers=ALICE,
        json={"format": "ndjson", "filename": "alice-over-quota.ndjson"},
    )
    assert rejected.status_code == 429, rejected.text

    assert initiate_upload(client, bob_project, BOB, "bob-allowed.ndjson")["state"] == "pending"


@pytest.mark.integration
def test_concurrent_upload_limit_uses_live_database_sessions(
    services: tuple[Settings, TestClient],
) -> None:
    config, client = services
    config.max_concurrent_uploads = 1
    project_id = create_project(client, ALICE, "concurrent-limit")
    first = initiate_upload(client, project_id, ALICE, "first.ndjson", data=b"x")
    second = initiate_upload(client, project_id, ALICE, "second.ndjson", data=b"y")
    with psycopg.connect(str(config.database_url)) as connection:
        connection.execute(
            "UPDATE upload_sessions SET state = 'receiving' WHERE id = %s",
            (first["upload_session_id"],),
        )

    response = client.put(str(second["upload_url"]), headers=ALICE, content=b"y")

    assert response.status_code == 429, response.text
    assert "concurrent upload quota" in response.text


@pytest.mark.integration
def test_temporary_upload_byte_quota_uses_reserved_session_bytes(
    services: tuple[Settings, TestClient],
) -> None:
    config, client = services
    config.max_upload_temp_bytes = 3000
    project_id = create_project(client, ALICE, "temporary-byte-limit")
    first = initiate_upload(client, project_id, ALICE, "first.ndjson", data=b"a" * 2000)
    second = initiate_upload(client, project_id, ALICE, "second.ndjson", data=b"b" * 2000)
    with psycopg.connect(str(config.database_url)) as connection:
        connection.execute(
            "UPDATE upload_sessions SET state = 'receiving' WHERE id = %s",
            (first["upload_session_id"],),
        )

    response = client.put(str(second["upload_url"]), headers=ALICE, content=b"b" * 2000)

    assert response.status_code == 429, response.text
    assert "temporary upload storage quota" in response.text


@pytest.mark.integration
def test_finalize_rejects_gzip_ndjson_over_decompressed_byte_limit(
    services: tuple[Settings, TestClient],
) -> None:
    config, client = services
    project_id = create_project(client, ALICE, "gzip-expansion")
    expanded = b'{"payload":"' + b"a" * (config.max_decompressed_bytes + 1) + b'"}\n'
    compressed = gzip.compress(expanded)
    assert len(compressed) < config.max_raw_upload_bytes
    upload = initiate_upload(client, project_id, ALICE, "expanded.ndjson.gz", data=compressed)

    response = transfer_and_finalize(client, upload, ALICE, compressed)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "decompressed_too_large"
    dataset = client.get(f"/v1/datasets/{upload['dataset_id']}", headers=ALICE)
    assert dataset.json()["state"] == "failed"


@pytest.mark.integration
def test_finalize_bounds_parquet_uncompressed_column_metadata(
    services: tuple[Settings, TestClient], tmp_path: Path
) -> None:
    config, client = services
    project_id = create_project(client, ALICE, "parquet-expansion")
    values = [f"{'x' * 512}{index:04d}" for index in range(100)]
    path = tmp_path / "expanded.parquet"
    pq.write_table(pa.table({"payload": values}), path, compression="zstd")
    compressed = path.read_bytes()
    metadata_bytes = (
        pq.ParquetFile(pa.BufferReader(compressed))
        .metadata.row_group(0)
        .column(0)
        .total_uncompressed_size
    )
    assert len(compressed) < config.max_raw_upload_bytes
    assert metadata_bytes > config.max_decompressed_bytes
    upload = initiate_upload(
        client, project_id, ALICE, "expanded.parquet", fmt="parquet", data=compressed
    )

    response = transfer_and_finalize(client, upload, ALICE, compressed)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "decompressed_too_large"


@pytest.mark.integration
def test_expired_upload_reference_cannot_finalize_uploaded_object(
    services: tuple[Settings, TestClient],
) -> None:
    config, client = services
    project_id = create_project(client, ALICE, "expired-finalize")
    data = b'{"still":"valid"}\n'
    upload = initiate_upload(client, project_id, ALICE, "expires.ndjson", data=data)
    transferred = client.put(str(upload["upload_url"]), headers=ALICE, content=data)
    assert transferred.status_code == 202, transferred.text
    with psycopg.connect(str(config.database_url)) as connection:
        connection.execute(
            "UPDATE upload_sessions SET expires_at = now() - interval '1 second' WHERE id = %s",
            (upload["upload_session_id"],),
        )

    response = client.post(f"/v1/uploads/{upload['upload_session_id']}/finalize", headers=ALICE)

    assert response.status_code == 410, response.text
    dataset = client.get(f"/v1/datasets/{upload['dataset_id']}", headers=ALICE)
    assert dataset.status_code == 200
    assert dataset.json()["state"] == "pending"
    assert (
        client.get(f"/v1/artifacts/{upload['artifact_id']}/content", headers=ALICE).status_code
        == 404
    )
