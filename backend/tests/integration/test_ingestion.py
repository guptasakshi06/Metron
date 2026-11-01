from __future__ import annotations

import asyncio
import hashlib
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from data_optimizer.api import datasets as dataset_api
from data_optimizer.api.main import create_app
from data_optimizer.config import Settings
from data_optimizer.db.migrations import migrate, migration_files
from data_optimizer.storage.retention import cleanup_expired
from data_optimizer.storage.s3 import S3Storage
from data_optimizer.storage.validation import ValidationResult


def upload(
    client: TestClient, project_id: str, fmt: str, name: str, data: bytes
) -> dict[str, object]:
    initiated = client.post(
        f"/v1/projects/{project_id}/datasets",
        json={
            "format": fmt,
            "filename": name,
            "expected_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "requirements": {"requirements_id": str(uuid.uuid4()), "retention_days": 7},
        },
    )
    assert initiated.status_code == 201, initiated.text
    payload = initiated.json()
    transferred = client.put(payload["upload_url"], content=data)
    assert transferred.status_code == 202, transferred.text
    finalized = client.post(f"/v1/uploads/{payload['upload_session_id']}/finalize")
    assert finalized.status_code == 200, finalized.text
    return finalized.json()


@pytest.mark.integration
def test_migrations_are_idempotent_and_reject_changed_checksums(
    services: tuple[Settings, TestClient],
) -> None:
    config, _client = services
    migration_name, _sql, checksum = migration_files()[0]
    with psycopg.connect(str(config.database_url)) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = %s WHERE name = %s",
            ("0" * 64, migration_name),
        )
    with pytest.raises(RuntimeError, match="checksum changed"):
        migrate(str(config.database_url))
    with psycopg.connect(str(config.database_url)) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = %s WHERE name = %s",
            (checksum, migration_name),
        )
    assert migrate(str(config.database_url)) == []


@pytest.mark.integration
def test_real_postgres_minio_uploads_are_tenant_scoped_and_immutable(
    services: tuple[Settings, TestClient],
    tmp_path,
) -> None:
    config, client = services
    alice = {"X-Local-Identity": "alice"}
    bob = {"X-Local-Identity": "bob"}
    project = client.post("/v1/projects", headers=alice, json={"name": "alpha"})
    assert project.status_code == 201, project.text
    project_id = project.json()["project_id"]
    assert client.get("/v1/projects", headers=bob).json()["items"] == []
    assert client.get(f"/v1/projects/{project_id}", headers=bob).status_code == 404

    parquet_path = tmp_path / "sample.parquet"
    pq.write_table(pa.table({"id": [1, 2], "name": ["a", "b"]}), parquet_path)
    samples = (
        ("csv", "events.csv", b"id,name\n1,a\n2,b\n"),
        ("ndjson", "events.ndjson", b'{"id":1,"name":"a"}\n{"id":2,"name":"b"}\n'),
        ("parquet", "events.parquet", parquet_path.read_bytes()),
    )
    for fmt, filename, data in samples:
        result = upload(client, project_id, fmt, filename, data)
        assert result["state"] == "ready"
        assert result["detected_format"] == fmt
        assert result["original_bytes"] == len(data)
        assert result["sha256"] == hashlib.sha256(data).hexdigest()
        artifact_id = result["artifact_id"]
        downloaded = client.get(result["artifact_content_url"], headers=alice)
        assert downloaded.status_code == 200
        assert downloaded.content == data
        assert client.get(result["artifact_content_url"], headers=bob).status_code == 404
        assert client.get(f"/v1/datasets/{result['dataset_id']}", headers=bob).status_code == 404
        assert client.get(f"/v1/artifacts/{artifact_id}/content", headers=alice).content == data
        with psycopg.connect(str(config.database_url)) as connection:
            session_id = connection.execute(
                "SELECT id FROM upload_sessions WHERE dataset_id = %s",
                (result["dataset_id"],),
            ).fetchone()[0]
            connection.execute(
                "UPDATE upload_sessions SET expires_at = now() - interval '1 second' WHERE id = %s",
                (session_id,),
            )
        assert cleanup_expired(config) == (0, 0)
        assert client.post(f"/v1/uploads/{session_id}/finalize").status_code == 200
        assert client.get(result["artifact_content_url"], headers=alice).content == data

    listed = client.get(f"/v1/projects/{project_id}/datasets", headers=alice)
    assert len(listed.json()["items"]) == 3
    assert all(item["artifact_id"] for item in listed.json()["items"])


@pytest.mark.integration
def test_malformed_oversized_expired_and_deleted_uploads_never_become_usable(
    services: tuple[Settings, TestClient],
) -> None:
    config, client = services
    alice = {"X-Local-Identity": "alice"}
    project_id = client.post("/v1/projects", headers=alice, json={"name": "bounded"}).json()[
        "project_id"
    ]
    malformed = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=alice,
        json={"format": "csv", "filename": "bad.csv"},
    ).json()
    assert client.put(malformed["upload_url"], content=b"a,b\n1\n").status_code == 202
    invalid = client.post(f"/v1/uploads/{malformed['upload_session_id']}/finalize")
    assert invalid.status_code == 422
    failed_metadata = client.get(f"/v1/datasets/{malformed['dataset_id']}", headers=alice).json()
    assert failed_metadata["state"] == "failed"

    too_large = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=alice,
        json={"format": "ndjson", "filename": "large.ndjson"},
    ).json()
    oversized_result = client.put(
        too_large["upload_url"],
        content=b"x" * (config.max_raw_upload_bytes + 1),
    )
    assert oversized_result.status_code == 413

    expired = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=alice,
        json={"format": "ndjson", "filename": "expired.ndjson"},
    ).json()
    with psycopg.connect(str(config.database_url)) as connection:
        connection.execute(
            "UPDATE upload_sessions SET expires_at = now() - interval '1 second' WHERE id = %s",
            (expired["upload_session_id"],),
        )
    assert client.put(expired["upload_url"], content=b'{"ok":true}\n').status_code == 410

    active = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=alice,
        json={"format": "ndjson", "filename": "delete.ndjson"},
    ).json()
    assert client.delete(f"/v1/projects/{project_id}", headers=alice).status_code == 202
    with psycopg.connect(str(config.database_url)) as connection:
        state = connection.execute(
            "SELECT state FROM upload_sessions WHERE id = %s", (active["upload_session_id"],)
        ).fetchone()[0]
    assert state == "delete_pending"
    assert client.put(active["upload_url"], content=b'{"ok":true}\n').status_code == 409


@pytest.mark.integration
def test_interrupted_chunked_upload_is_marked_failed_and_never_ready(
    services: tuple[Settings, TestClient],
) -> None:
    config, client = services
    alice = {"X-Local-Identity": "alice"}
    project_id = client.post("/v1/projects", headers=alice, json={"name": "interrupted"}).json()[
        "project_id"
    ]
    initiated = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=alice,
        json={"format": "ndjson", "filename": "interrupted.ndjson"},
    ).json()

    async def incomplete_body():
        yield b'{"partial":'
        raise RuntimeError("simulated client disconnect")

    async def transfer() -> int:
        async with AsyncClient(
            transport=ASGITransport(app=create_app(config)),
            base_url="http://testserver",
        ) as async_client:
            response = await async_client.put(
                initiated["upload_url"], headers=alice, content=incomplete_body()
            )
            return response.status_code

    assert asyncio.run(transfer()) == 503
    metadata = client.get(f"/v1/datasets/{initiated['dataset_id']}", headers=alice)
    assert metadata.status_code == 200
    assert metadata.json()["state"] == "failed"
    assert (
        client.get(
            f"/v1/artifacts/{initiated['artifact_id']}/content",
            headers=alice,
        ).status_code
        == 404
    )


@pytest.mark.integration
def test_project_deletion_cannot_cross_tenant_or_remove_audit_history(
    services: tuple[Settings, TestClient],
) -> None:
    config, client = services
    project = client.post(
        "/v1/projects", headers={"X-Local-Identity": "alice"}, json={"name": "owned"}
    ).json()
    project_id = project["project_id"]
    assert (
        client.delete(f"/v1/projects/{project_id}", headers={"X-Local-Identity": "bob"}).status_code
        == 404
    )
    assert (
        client.delete(
            f"/v1/projects/{project_id}", headers={"X-Local-Identity": "alice"}
        ).status_code
        == 202
    )
    assert (
        client.get(f"/v1/projects/{project_id}", headers={"X-Local-Identity": "alice"}).status_code
        == 404
    )
    with psycopg.connect(str(config.database_url)) as connection:
        audit_count = connection.execute(
            """SELECT count(*) FROM audit_events WHERE resource_type = 'project'
               AND resource_id = %s AND action = 'delete_requested'""",
            (project_id,),
        ).fetchone()[0]
    assert audit_count == 1


@pytest.mark.integration
def test_delete_failure_keeps_tombstone_until_cleanup_retries(
    services: tuple[Settings, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, client = services
    alice = {"X-Local-Identity": "alice"}
    project_id = client.post("/v1/projects", headers=alice, json={"name": "retry"}).json()[
        "project_id"
    ]
    dataset = upload(client, project_id, "ndjson", "retry.ndjson", b'{"n":1}\n')

    def fail_delete(self: S3Storage, object_key: str) -> None:
        del self, object_key
        raise ConnectionError("injected MinIO outage")

    monkeypatch.setattr(S3Storage, "delete", fail_delete)
    response = client.delete(f"/v1/datasets/{dataset['dataset_id']}", headers=alice)
    assert response.status_code == 202
    assert response.json()["state"] == "delete_pending"
    assert client.get(dataset["artifact_content_url"], headers=alice).status_code == 404
    assert cleanup_expired(config) == (0, 1)
    with psycopg.connect(str(config.database_url)) as connection:
        state = connection.execute(
            "SELECT state FROM datasets WHERE id = %s", (dataset["dataset_id"],)
        ).fetchone()[0]
    assert state == "delete_pending"

    monkeypatch.undo()
    assert cleanup_expired(config) == (1, 0)
    assert client.get(f"/v1/datasets/{dataset['dataset_id']}", headers=alice).status_code == 404


@pytest.mark.integration
def test_late_put_after_delete_reopens_tombstone_for_cleanup(
    services: tuple[Settings, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, client = services
    alice = {"X-Local-Identity": "alice"}
    project_id = client.post("/v1/projects", headers=alice, json={"name": "race-put"}).json()[
        "project_id"
    ]
    data = b'{"raced":true}\n'
    initiated = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=alice,
        json={
            "format": "ndjson",
            "filename": "race.ndjson",
            "expected_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    ).json()
    object_written = threading.Event()
    release_put = threading.Event()
    original_put = S3Storage.put_file

    def delayed_put(self: S3Storage, key: str, path, byte_count: int) -> None:
        original_put(self, key, path, byte_count)
        object_written.set()
        if not release_put.wait(timeout=10):
            raise TimeoutError("test did not release upload")

    def unavailable_delete(self: S3Storage, key: str) -> None:
        del self, key
        raise ConnectionError("injected delete outage")

    monkeypatch.setattr(S3Storage, "put_file", delayed_put)
    monkeypatch.setattr(S3Storage, "delete", unavailable_delete)
    other_client = TestClient(create_app(config), client=("127.0.0.1", 12346))
    with ThreadPoolExecutor(max_workers=1) as pool:
        transfer = pool.submit(client.put, initiated["upload_url"], content=data, headers=alice)
        assert object_written.wait(timeout=10)
        deletion = other_client.delete(f"/v1/datasets/{initiated['dataset_id']}", headers=alice)
        assert deletion.status_code == 202
        assert deletion.json()["state"] == "delete_pending"
        release_put.set()
        assert transfer.result(timeout=10).status_code == 409

    with psycopg.connect(str(config.database_url)) as connection:
        session_state = connection.execute(
            "SELECT state FROM upload_sessions WHERE id = %s",
            (initiated["upload_session_id"],),
        ).fetchone()[0]
        dataset_state = connection.execute(
            "SELECT state FROM datasets WHERE id = %s", (initiated["dataset_id"],)
        ).fetchone()[0]
    assert session_state == "delete_pending"
    assert dataset_state == "delete_pending"

    monkeypatch.undo()
    assert cleanup_expired(config) == (1, 0)
    assert (
        other_client.get(f"/v1/datasets/{initiated['dataset_id']}", headers=alice).status_code
        == 404
    )


@pytest.mark.integration
def test_finalize_cannot_publish_after_concurrent_project_deletion(
    services: tuple[Settings, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, client = services
    alice = {"X-Local-Identity": "alice"}
    project_id = client.post("/v1/projects", headers=alice, json={"name": "race-finalize"}).json()[
        "project_id"
    ]
    data = b'{"raced":true}\n'
    initiated = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=alice,
        json={
            "format": "ndjson",
            "filename": "race.ndjson",
            "expected_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    ).json()
    assert client.put(initiated["upload_url"], content=data, headers=alice).status_code == 202
    validation_entered = threading.Event()
    release_validation = threading.Event()

    def delayed_validation(*_args, **_kwargs) -> ValidationResult:
        validation_entered.set()
        if not release_validation.wait(timeout=10):
            raise TimeoutError("test did not release validator")
        return ValidationResult("ndjson", None, len(data), len(data))

    def unavailable_delete(self: S3Storage, key: str) -> None:
        del self, key
        raise ConnectionError("injected delete outage")

    monkeypatch.setattr(dataset_api, "validate_file", delayed_validation)
    monkeypatch.setattr(S3Storage, "delete", unavailable_delete)
    other_client = TestClient(create_app(config), client=("127.0.0.1", 12347))
    with ThreadPoolExecutor(max_workers=1) as pool:
        finalization = pool.submit(
            client.post,
            f"/v1/uploads/{initiated['upload_session_id']}/finalize",
            headers=alice,
        )
        assert validation_entered.wait(timeout=10)
        assert other_client.delete(f"/v1/projects/{project_id}", headers=alice).status_code == 202
        release_validation.set()
        assert finalization.result(timeout=10).status_code == 409

    with psycopg.connect(str(config.database_url)) as connection:
        state = connection.execute(
            "SELECT state FROM datasets WHERE id = %s", (initiated["dataset_id"],)
        ).fetchone()[0]
        session_state = connection.execute(
            "SELECT state FROM upload_sessions WHERE id = %s",
            (initiated["upload_session_id"],),
        ).fetchone()[0]
    assert state == "delete_pending"
    assert session_state == "delete_pending"

    monkeypatch.undo()
    assert cleanup_expired(config) == (1, 0)
