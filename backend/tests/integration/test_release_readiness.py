"""S14 disaster-recovery and capacity drills against isolated real local services."""

import hashlib
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from test_assessments import drain, submission, submit
from test_ingestion import upload
from test_observations_api import deployed_plan, observation

from data_optimizer.api.main import create_app
from data_optimizer.db.migrations import migrate
from data_optimizer.storage.s3 import S3Storage

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


def test_metadata_backup_restore_preserves_owned_evidence_and_history(services, tmp_path):
    config, client = services
    assessment = submit(client, submission(client, raw=True)).json()["id"]
    drain(config)
    original = client.get(f"/v1/assessments/{assessment}/result")
    assert original.status_code == 200, original.text
    plan = deployed_plan(client, assessment)
    assert (
        client.post(
            f"/v1/migration-plans/{plan}/observations", json=observation().model_dump(mode="json")
        ).status_code
        == 200
    )
    grant = client.post(f"/v1/assessments/{assessment}/handoff").json()
    bundle = client.get(grant["links"]["json"]).content
    history = client.get(f"/v1/migration-plans/{plan}/history").content
    parts = urlsplit(str(config.database_url))
    schema = parse_qs(parts.query)["options"][0].split("=", 1)[1]
    # Tools run inside this project's existing PostgreSQL image (same major version).
    containers = subprocess.check_output(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            "label=com.docker.compose.project=data-optimizer-local",
            "--filter",
            "label=com.docker.compose.service=postgres",
        ],
        text=True,
    ).split()
    assert len(containers) == 1
    prefix = ["docker", "exec", "-i", containers[0]]
    backup = subprocess.run(
        prefix
        + [
            "pg_dump",
            "-Fc",
            "--no-owner",
            "--no-acl",
            "-U",
            parts.username,
            "-d",
            parts.path[1:],
            "-n",
            schema,
        ],
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    assert backup.startswith(b"PGDMP")
    name = "s14_restore_" + uuid4().hex
    restored_url = urlunsplit((parts.scheme, parts.netloc, "/" + name, parts.query, ""))
    started = time.monotonic()
    with psycopg.connect(str(config.database_url), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        try:
            subprocess.run(
                prefix
                + [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "-U",
                    parts.username,
                    "-d",
                    name,
                ],
                input=backup,
                capture_output=True,
                check=True,
                timeout=30,
            )
            assert migrate(restored_url) == []
            restored_config = config.model_copy(update={"database_url": restored_url})
            restored = TestClient(create_app(restored_config), client=("127.0.0.1", 12345))
            assert restored.get(f"/v1/assessments/{assessment}/result").content == original.content
            assert restored.get(f"/v1/migration-plans/{plan}/history").content == history
            assert restored.get(grant["links"]["json"]).content == bundle
            assert (
                restored.get(
                    grant["links"]["json"], headers={"X-Local-Identity": "bob"}
                ).status_code
                == 404
            )
            with psycopg.connect(restored_url) as db:
                with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
                    with db.transaction():
                        db.execute("UPDATE assessments SET request='{}'")
            # Retained artifacts are part of the recovery set: loss cannot look successful.
            with psycopg.connect(restored_url) as db:
                key = db.execute(
                    "SELECT result_key FROM assessments WHERE id=%s", (assessment,)
                ).fetchone()[0]
            storage = S3Storage(config)
            body = storage.get(key)
            try:
                content = body.read()
            finally:
                body.close()
            saved = tmp_path / "result.json"
            saved.write_bytes(content)
            storage.delete(key)
            try:
                assert restored.get(f"/v1/assessments/{assessment}/result").status_code == 503
            finally:
                storage.put_file(key, saved, len(content))
            assert restored.get(f"/v1/assessments/{assessment}/result").content == original.content
            evidence = {
                "metadata_restore": "passed",
                "backup_bytes": len(backup),
                "backup_sha256": hashlib.sha256(backup).hexdigest(),
                "restore_seconds": time.monotonic() - started,
                "eight_migrations_unchanged": True,
                "result_bundle_history_equal": True,
                "tenant_and_immutability_preserved": True,
                "missing_object_fails_closed_then_restored": True,
                "scope": "Fresh temporary database; original private object bucket retained. "
                "No production restore or independent object-store backup claimed.",
            }
            (ROOT / "docs/evidence/s14-backup-restore.json").write_text(
                json.dumps(evidence, indent=2) + "\n"
            )
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_measured_upload_envelope_and_over_limit_rejection(services):
    config, _ = services
    # Calibrate a conservative 16 MiB upload envelope, not the 256 MiB policy maximum.
    cap = 16 * 1024 * 1024
    measured = config.model_copy(
        update={
            "max_raw_upload_bytes": cap,
            "max_decompressed_bytes": cap * 2,
            "validation_memory_mib": 512,
            "validation_timeout_seconds": 30,
        }
    )
    client = TestClient(create_app(measured), client=("127.0.0.1", 12345))
    project = client.post("/v1/projects", json={"name": "S14 capacity holdout"}).json()[
        "project_id"
    ]
    # Exactly 256 bytes per record, preserves legitimate duplicate records.
    row = b'{"id":"000001","text":"' + b"x" * 230 + b'"}\n'
    assert len(row) == 256
    records = []
    for byte_count in (1024 * 1024, cap):
        data = row * (byte_count // len(row))
        started = time.monotonic()
        saved = upload(client, project, "ndjson", "heldout.ndjson", data)
        assert saved["original_bytes"] == byte_count
        downloaded = client.get(saved["artifact_content_url"])
        assert hashlib.sha256(downloaded.content).digest() == hashlib.sha256(data).digest()
        records.append(
            {
                "bytes": byte_count,
                "rows": byte_count // 256,
                "upload_finalize_download_seconds": time.monotonic() - started,
                "sha256": saved["sha256"],
                "status": "ready",
            }
        )
    initiated = client.post(
        f"/v1/projects/{project}/datasets",
        json={"format": "ndjson", "filename": "too-large.ndjson"},
    ).json()
    response = client.put(initiated["upload_url"], content=row * (cap // 256) + b"\n")
    assert response.status_code == 413
    evidence = {
        "envelope_bytes": cap,
        "validator_memory_mib": 512,
        "validator_timeout_seconds": 30,
        "cases": records,
        "over_limit_http_status": response.status_code,
        "boundary": "In-process ASGI API + real PostgreSQL/MinIO/subprocess validation. "
        "Not a network throughput or full assessment at 16 MiB claim.",
    }
    (ROOT / "docs/evidence/s14-upload-capacity.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
