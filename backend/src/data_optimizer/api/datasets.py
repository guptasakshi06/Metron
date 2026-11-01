"""Tenant-scoped upload sessions, immutable datasets and artifact access."""

import asyncio
import hashlib
import os
import tempfile
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from data_optimizer.auth.dependencies import identity_dependency
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings
from data_optimizer.domain.contracts import DatasetFormat, Requirements
from data_optimizer.storage.s3 import S3Storage
from data_optimizer.storage.validation import ValidationError, ValidationLimits, validate_file


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: DatasetFormat
    filename: str = Field(min_length=1, max_length=255)
    expected_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    retention_days: int | None = Field(default=None, ge=1, le=30)
    semantics: dict[str, Any] = Field(default_factory=dict)
    requirements: Requirements | None = None


def _safe_filename(value: str) -> bool:
    return (
        value not in {".", ".."}
        and ".." not in value
        and "/" not in value
        and "\\" not in value
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _session_key(tenant_id: str, dataset_id: str, session_id: str) -> str:
    return f"tenants/{tenant_id}/datasets/{dataset_id}/uploads/{session_id}/original"


def _fail_session(
    config: Settings, tenant_id: str, session_id: UUID, object_key: str, stored: bool
) -> None:
    with psycopg.connect(str(config.database_url)) as connection:
        with connection.transaction():
            dataset_ref = connection.execute(
                "SELECT dataset_id FROM upload_sessions WHERE tenant_id = %s AND id = %s",
                (tenant_id, session_id),
            ).fetchone()
            if dataset_ref is not None:
                connection.execute(
                    """SELECT id FROM datasets WHERE tenant_id = %s AND id = %s FOR UPDATE""",
                    (tenant_id, dataset_ref[0]),
                )
            connection.execute(
                """UPDATE upload_sessions SET state = %s, updated_at = now()
                   WHERE tenant_id = %s AND id = %s
                     AND (%s OR state NOT IN ('complete','deleted','delete_pending'))""",
                ("delete_pending" if stored else "failed", tenant_id, session_id, stored),
            )
            connection.execute(
                """UPDATE datasets d SET state = 'failed'
                   FROM upload_sessions u WHERE u.tenant_id = %s AND u.id = %s
                   AND d.tenant_id = u.tenant_id AND d.id = u.dataset_id
                   AND d.state NOT IN ('ready','delete_pending','deleted')""",
                (tenant_id, session_id),
            )
            connection.execute(
                """UPDATE artifacts SET state = %s WHERE tenant_id = %s AND object_key = %s
                   AND (%s OR state NOT IN ('delete_pending','deleted'))""",
                ("delete_pending" if stored else "deleted", tenant_id, object_key, stored),
            )
    if stored:
        try:
            S3Storage(config).delete(object_key)
        except Exception:
            return
        with psycopg.connect(str(config.database_url)) as connection:
            connection.execute(
                """UPDATE upload_sessions SET state = 'deleted', updated_at = now()
                   WHERE tenant_id = %s AND id = %s AND state = 'delete_pending'""",
                (tenant_id, session_id),
            )
            connection.execute(
                """UPDATE artifacts SET state = 'deleted', deleted_at = now()
                   WHERE tenant_id = %s AND object_key = %s AND state = 'delete_pending'""",
                (tenant_id, object_key),
            )


def build_datasets_router(config: Settings) -> APIRouter:
    router = APIRouter(tags=["datasets"])
    verified_identity = identity_dependency(config)

    @router.post("/v1/projects/{project_id}/datasets", status_code=status.HTTP_201_CREATED)
    def create_dataset(
        project_id: UUID,
        payload: DatasetCreate,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        if not _safe_filename(payload.filename):
            raise HTTPException(status_code=422, detail="unsafe display filename")
        if (
            payload.expected_bytes is not None
            and payload.expected_bytes > config.max_raw_upload_bytes
        ):
            raise HTTPException(status_code=413, detail="raw upload limit exceeded")
        retention_days = payload.retention_days or config.default_retention_days
        if retention_days > 30:
            raise HTTPException(status_code=422, detail="retention days exceed configured maximum")
        dataset_id, session_id, artifact_id = uuid4(), uuid4(), uuid4()
        object_key = _session_key(identity.tenant_id, str(dataset_id), str(session_id))
        expires_at = datetime.now(UTC) + timedelta(days=retention_days)
        session_expires_at = datetime.now(UTC) + timedelta(
            seconds=config.upload_session_ttl_seconds
        )
        with psycopg.connect(str(config.database_url)) as connection:
            with connection.transaction():
                project = connection.execute(
                    """SELECT id FROM projects WHERE tenant_id = %s AND id = %s
                       AND deleted_at IS NULL FOR UPDATE""",
                    (identity.tenant_id, project_id),
                ).fetchone()
                if project is None:
                    raise HTTPException(status_code=404, detail="project not found")
                connection.execute(
                    "SELECT id FROM tenants WHERE id = %s FOR UPDATE", (identity.tenant_id,)
                )
                active = connection.execute(
                    """SELECT count(*) FROM upload_sessions WHERE tenant_id = %s
                       AND state IN ('pending','receiving','uploaded','validating')
                       AND expires_at > now()""",
                    (identity.tenant_id,),
                ).fetchone()
                if active is None:
                    raise RuntimeError("upload count query returned no row")
                active_count = active[0]
                if active_count >= config.max_uploads_per_tenant:
                    raise HTTPException(
                        status_code=429, detail="tenant upload session quota reached"
                    )
                previous = connection.execute(
                    """SELECT id, version FROM datasets WHERE tenant_id = %s AND project_id = %s
                       ORDER BY version DESC LIMIT 1""",
                    (identity.tenant_id, project_id),
                ).fetchone()
                version = (previous[1] + 1) if previous else 1
                previous_id = previous[0] if previous else None
                connection.execute(
                    """INSERT INTO datasets
                       (id, tenant_id, project_id, previous_dataset_id, version, state,
                        declared_format, display_filename, declared_semantics,
                        retention_days, expires_at)
                       VALUES (%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s)""",
                    (
                        dataset_id,
                        identity.tenant_id,
                        project_id,
                        previous_id,
                        version,
                        payload.format.value,
                        payload.filename,
                        Jsonb(payload.semantics),
                        retention_days,
                        expires_at,
                    ),
                )
                connection.execute(
                    """INSERT INTO upload_sessions
                       (id, tenant_id, dataset_id, state, expected_bytes, expected_sha256,
                        object_key, expires_at)
                       VALUES (%s,%s,%s,'pending',%s,%s,%s,%s)""",
                    (
                        session_id,
                        identity.tenant_id,
                        dataset_id,
                        payload.expected_bytes,
                        payload.sha256,
                        object_key,
                        session_expires_at,
                    ),
                )
                connection.execute(
                    """INSERT INTO artifacts
                       (id, tenant_id, dataset_id, upload_session_id, kind, state, object_key)
                       VALUES (%s,%s,%s,%s,'original','staging',%s)""",
                    (artifact_id, identity.tenant_id, dataset_id, session_id, object_key),
                )
                if payload.requirements is not None:
                    req_version = connection.execute(
                        """SELECT COALESCE(max(version), 0) + 1 FROM requirements_snapshots
                           WHERE tenant_id = %s AND project_id = %s""",
                        (identity.tenant_id, project_id),
                    ).fetchone()
                    if req_version is None:
                        raise RuntimeError("requirements version query returned no row")
                    connection.execute(
                        """INSERT INTO requirements_snapshots
                           (id, tenant_id, project_id, version, contract_version, payload)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (
                            uuid4(),
                            identity.tenant_id,
                            project_id,
                            req_version[0],
                            payload.requirements.version,
                            Jsonb(payload.requirements.model_dump(mode="json")),
                        ),
                    )
                connection.execute(
                    """INSERT INTO audit_events
                       (id, tenant_id, actor_principal_id, resource_type,
                        resource_id, action, details)
                       VALUES (%s,%s,%s,'dataset',%s,'upload_initiated',%s)""",
                    (
                        uuid4(),
                        identity.tenant_id,
                        identity.principal_id,
                        dataset_id,
                        Jsonb({"retention_days": retention_days}),
                    ),
                )
        return {
            "dataset_id": dataset_id,
            "version": version,
            "state": "pending",
            "upload_session_id": session_id,
            "artifact_id": artifact_id,
            "upload_url": f"/v1/uploads/{session_id}",
            "expires_at": session_expires_at,
            "retention_days": retention_days,
            "retention_scope": "uploaded assessment copy only; external source is untouched",
        }

    @router.put("/v1/uploads/{session_id}", status_code=status.HTTP_202_ACCEPTED)
    async def transfer_upload(
        session_id: UUID,
        request: Request,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        content_length_header = request.headers.get("content-length")
        content_length: int | None = None
        if content_length_header is not None:
            try:
                content_length = int(content_length_header)
            except ValueError as error:
                raise HTTPException(status_code=400, detail="invalid content length") from error
            if content_length < 0 or content_length > config.max_raw_upload_bytes:
                raise HTTPException(status_code=413, detail="raw upload limit exceeded")
        with psycopg.connect(str(config.database_url)) as connection:
            with connection.transaction():
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (7_043_211_903,))
                preflight = connection.execute(
                    """SELECT expected_bytes, state, expires_at FROM upload_sessions
                       WHERE tenant_id = %s AND id = %s FOR UPDATE""",
                    (identity.tenant_id, session_id),
                ).fetchone()
                if preflight is None:
                    raise HTTPException(status_code=404, detail="upload session not found")
                if preflight[2] <= datetime.now(UTC):
                    raise HTTPException(status_code=410, detail="upload session expired")
                if preflight[1] != "pending":
                    raise HTTPException(status_code=409, detail="upload session is not writable")
                active = connection.execute(
                    """SELECT count(*), COALESCE(sum(COALESCE(expected_bytes, %s)), 0)
                       FROM upload_sessions WHERE state IN ('receiving','validating')""",
                    (config.max_raw_upload_bytes,),
                ).fetchone()
                if active is None:
                    raise RuntimeError("active upload count returned no row")
                expected_reservation = preflight[0]
                reserved = (
                    expected_reservation
                    if expected_reservation is not None
                    else config.max_raw_upload_bytes
                )
                if active[0] >= config.max_concurrent_uploads:
                    raise HTTPException(status_code=429, detail="concurrent upload quota reached")
                if active[1] + reserved > config.max_upload_temp_bytes:
                    raise HTTPException(
                        status_code=429, detail="temporary upload storage quota reached"
                    )
                row = connection.execute(
                    """UPDATE upload_sessions u SET state = 'receiving', updated_at = now()
                       FROM datasets d, projects p
                       WHERE u.tenant_id = %s AND u.id = %s AND u.state = 'pending'
                         AND u.expires_at > now() AND d.tenant_id = u.tenant_id
                         AND d.id = u.dataset_id
                         AND d.state = 'pending' AND d.deleted_at IS NULL
                         AND p.tenant_id = d.tenant_id AND p.id = d.project_id
                         AND p.deleted_at IS NULL
                       RETURNING u.dataset_id, u.expected_bytes, u.expected_sha256, u.object_key,
                                 d.declared_format""",
                    (identity.tenant_id, session_id),
                ).fetchone()
                if row is None:
                    state = connection.execute(
                        """SELECT state, expires_at FROM upload_sessions
                           WHERE tenant_id = %s AND id = %s""",
                        (identity.tenant_id, session_id),
                    ).fetchone()
                    if state is None:
                        raise HTTPException(status_code=404, detail="upload session not found")
                    if state[1] <= datetime.now(UTC):
                        raise HTTPException(status_code=410, detail="upload session expired")
                    raise HTTPException(status_code=409, detail="upload session is not writable")
        dataset_id, expected_bytes, expected_sha, object_key, _declared_format = row
        if (
            expected_bytes is not None
            and content_length is not None
            and expected_bytes != content_length
        ):
            _fail_session(config, identity.tenant_id, session_id, object_key, stored=False)
            raise HTTPException(
                status_code=400, detail="content length does not match upload initiation"
            )
        temp_root = Path(config.upload_temp_dir).resolve()
        temp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(temp_root, 0o700)
        file_descriptor, temp_name = tempfile.mkstemp(prefix="upload-", dir=temp_root)
        temp_path = Path(temp_name)
        size = 0
        digest = hashlib.sha256()
        put_attempted = False
        try:
            with os.fdopen(file_descriptor, "wb") as target:
                async with asyncio.timeout(config.max_upload_seconds):
                    async for chunk in request.stream():
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > config.max_raw_upload_bytes or (
                            expected_bytes is not None and size > expected_bytes
                        ):
                            raise HTTPException(status_code=413, detail="raw upload limit exceeded")
                        target.write(chunk)
                        digest.update(chunk)
            if content_length is not None and size != content_length:
                raise HTTPException(
                    status_code=400, detail="received bytes do not match content length"
                )
            if expected_bytes is not None and size != expected_bytes:
                raise HTTPException(
                    status_code=400, detail="received bytes do not match upload initiation"
                )
            actual_sha = digest.hexdigest()
            if expected_sha is not None and actual_sha != expected_sha:
                raise HTTPException(status_code=400, detail="uploaded content fingerprint mismatch")
            storage = S3Storage(config)
            put_attempted = True
            await run_in_threadpool(storage.put_file, object_key, temp_path, size)
            head_bytes = await run_in_threadpool(storage.head, object_key)
            if head_bytes != size:
                raise RuntimeError("stored object size mismatch")
            with psycopg.connect(str(config.database_url)) as connection:
                with connection.transaction():
                    changed = connection.execute(
                        """UPDATE upload_sessions SET state = 'uploaded', updated_at = now()
                           WHERE tenant_id = %s AND id = %s AND state = 'receiving'
                           AND expires_at > now() RETURNING id""",
                        (identity.tenant_id, session_id),
                    ).fetchone()
                    if changed is None:
                        raise HTTPException(status_code=409, detail="upload session was cancelled")
                    connection.execute(
                        """UPDATE artifacts SET byte_count = %s, sha256 = %s
                           WHERE tenant_id = %s AND object_key = %s AND state = 'staging'""",
                        (size, actual_sha, identity.tenant_id, object_key),
                    )
            return {"upload_session_id": session_id, "state": "uploaded", "bytes": size}
        except HTTPException:
            _fail_session(config, identity.tenant_id, session_id, object_key, put_attempted)
            raise
        except TimeoutError as error:
            _fail_session(config, identity.tenant_id, session_id, object_key, put_attempted)
            raise HTTPException(status_code=408, detail="upload transfer timed out") from error
        except asyncio.CancelledError:
            _fail_session(config, identity.tenant_id, session_id, object_key, put_attempted)
            raise
        except Exception as error:
            _fail_session(config, identity.tenant_id, session_id, object_key, put_attempted)
            raise HTTPException(status_code=503, detail="upload transfer failed") from error
        finally:
            temp_path.unlink(missing_ok=True)

    @router.post("/v1/uploads/{session_id}/finalize")
    def finalize_upload(
        session_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            with connection.transaction():
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (7_043_211_903,))
                dataset_ref = connection.execute(
                    "SELECT dataset_id FROM upload_sessions WHERE tenant_id = %s AND id = %s",
                    (identity.tenant_id, session_id),
                ).fetchone()
                if dataset_ref is None:
                    raise HTTPException(status_code=404, detail="upload session not found")
                dataset_lock = connection.execute(
                    """SELECT id FROM datasets WHERE tenant_id = %s AND id = %s FOR UPDATE""",
                    (identity.tenant_id, dataset_ref[0]),
                ).fetchone()
                if dataset_lock is None:
                    raise HTTPException(status_code=404, detail="upload session not found")
                row = connection.execute(
                    """SELECT u.dataset_id, u.object_key, u.expected_bytes, u.expected_sha256,
                              d.declared_format, d.expires_at, d.retention_days, d.state
                       FROM upload_sessions u JOIN datasets d
                         ON d.tenant_id = u.tenant_id AND d.id = u.dataset_id
                       JOIN projects p ON p.tenant_id = d.tenant_id AND p.id = d.project_id
                       WHERE u.tenant_id = %s AND u.id = %s AND p.deleted_at IS NULL
                       FOR UPDATE OF u""",
                    (identity.tenant_id, session_id),
                ).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="upload session not found")
                (
                    dataset_id,
                    object_key,
                    expected_bytes,
                    expected_sha,
                    declared,
                    expiry,
                    retain,
                    dataset_state,
                ) = row
                active_uploads = connection.execute(
                    """SELECT count(*), COALESCE(sum(COALESCE(expected_bytes, %s)), 0)
                       FROM upload_sessions WHERE state IN ('receiving','validating')""",
                    (config.max_raw_upload_bytes,),
                ).fetchone()
                current_reservation = (
                    expected_bytes if expected_bytes is not None else config.max_raw_upload_bytes
                )
                if (
                    active_uploads is not None
                    and active_uploads[0] >= config.max_concurrent_uploads
                ):
                    raise HTTPException(status_code=429, detail="concurrent upload quota reached")
                if (
                    active_uploads is not None
                    and active_uploads[1] + current_reservation > config.max_upload_temp_bytes
                ):
                    raise HTTPException(
                        status_code=429, detail="temporary upload storage quota reached"
                    )
                state = connection.execute(
                    """SELECT state, expires_at FROM upload_sessions
                   WHERE tenant_id = %s AND id = %s""",
                    (identity.tenant_id, session_id),
                ).fetchone()
                if state is None:
                    raise HTTPException(status_code=404, detail="upload session not found")
                if expiry <= datetime.now(UTC):
                    raise HTTPException(status_code=410, detail="upload session expired")
                if state[0] == "complete" and dataset_state == "ready":
                    return self_dataset_metadata(connection, identity.tenant_id, dataset_id)
                if state[1] <= datetime.now(UTC):
                    raise HTTPException(status_code=410, detail="upload session expired")
                if dataset_state != "pending" or state[0] != "uploaded":
                    raise HTTPException(status_code=409, detail="upload is not ready to finalize")
                connection.execute(
                    """UPDATE upload_sessions SET state = 'validating', updated_at = now()
                       WHERE tenant_id = %s AND id = %s""",
                    (identity.tenant_id, session_id),
                )
        temp_root = Path(config.upload_temp_dir).resolve()
        temp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(temp_root, 0o700)
        file_descriptor, temp_name = tempfile.mkstemp(prefix="finalize-", dir=temp_root)
        temp_path = Path(temp_name)
        digest = hashlib.sha256()
        copied = 0
        body = None
        try:
            body = S3Storage(config).get(object_key)
            transfer_deadline = time.monotonic() + config.validation_timeout_seconds
            with os.fdopen(file_descriptor, "wb") as target:
                for chunk in body.iter_chunks(chunk_size=64 * 1024):
                    if time.monotonic() > transfer_deadline:
                        raise HTTPException(status_code=408, detail="artifact transfer timed out")
                    if not chunk:
                        continue
                    copied += len(chunk)
                    if copied > config.max_raw_upload_bytes:
                        raise HTTPException(status_code=413, detail="raw upload limit exceeded")
                    target.write(chunk)
                    digest.update(chunk)
            body.close()
            body = None
            if expected_bytes is not None and copied != expected_bytes:
                raise HTTPException(status_code=400, detail="stored upload byte count mismatch")
            actual_sha = digest.hexdigest()
            if expected_sha is not None and actual_sha != expected_sha:
                raise HTTPException(status_code=400, detail="stored upload fingerprint mismatch")
            validation = validate_file(
                temp_path,
                declared,
                ValidationLimits(
                    raw_bytes=config.max_raw_upload_bytes,
                    decompressed_bytes=config.max_decompressed_bytes,
                    timeout_seconds=config.validation_timeout_seconds,
                    memory_mib=config.validation_memory_mib,
                ),
            )
            with psycopg.connect(str(config.database_url)) as connection:
                with connection.transaction():
                    changed = connection.execute(
                        """UPDATE datasets d SET state = 'ready', detected_format = %s,
                           compression = %s, original_bytes = %s, decompressed_bytes = %s,
                           sha256 = %s
                           FROM upload_sessions u, projects p
                           WHERE d.tenant_id = %s AND d.id = %s AND d.state = 'pending'
                             AND d.tenant_id = u.tenant_id AND u.id = %s AND u.state = 'validating'
                             AND p.tenant_id = d.tenant_id AND p.id = d.project_id
                             AND p.deleted_at IS NULL
                             AND d.deleted_at IS NULL
                             AND d.expires_at > now() AND u.expires_at > now()
                           RETURNING d.id""",
                        (
                            validation.detected_format,
                            validation.compression,
                            validation.physical_bytes,
                            validation.decompressed_bytes,
                            actual_sha,
                            identity.tenant_id,
                            dataset_id,
                            session_id,
                        ),
                    ).fetchone()
                    if changed is None:
                        raise HTTPException(
                            status_code=409, detail="dataset was deleted during finalization"
                        )
                    connection.execute(
                        """UPDATE upload_sessions SET state = 'complete', updated_at = now()
                           WHERE tenant_id = %s AND id = %s AND state = 'validating'""",
                        (identity.tenant_id, session_id),
                    )
                    connection.execute(
                        """UPDATE artifacts SET state = 'ready', byte_count = %s, sha256 = %s
                           WHERE tenant_id = %s AND upload_session_id = %s AND state = 'staging'""",
                        (validation.physical_bytes, actual_sha, identity.tenant_id, session_id),
                    )
                    connection.execute(
                        """INSERT INTO audit_events
                           (id, tenant_id, actor_principal_id, resource_type, resource_id, action)
                           VALUES (%s,%s,%s,'dataset',%s,'upload_finalized')""",
                        (uuid4(), identity.tenant_id, identity.principal_id, dataset_id),
                    )
                    return self_dataset_metadata(connection, identity.tenant_id, dataset_id)
        except ValidationError as error:
            _fail_session(config, identity.tenant_id, session_id, object_key, stored=True)
            raise HTTPException(status_code=422, detail={"code": error.code}) from error
        except HTTPException:
            _fail_session(config, identity.tenant_id, session_id, object_key, stored=True)
            raise
        except Exception as error:
            _fail_session(config, identity.tenant_id, session_id, object_key, stored=True)
            raise HTTPException(status_code=503, detail="upload finalization failed") from error
        finally:
            if body is not None:
                body.close()
            temp_path.unlink(missing_ok=True)

    @router.get("/v1/projects/{project_id}/datasets")
    def list_datasets(
        project_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            rows = connection.execute(
                """SELECT d.id,
                          (SELECT a.id FROM artifacts a WHERE a.tenant_id = d.tenant_id
                             AND a.dataset_id = d.id AND a.kind = 'original'),
                          d.version, d.state, d.declared_format, d.detected_format,
                          d.original_bytes, d.sha256, d.created_at, d.expires_at
                   FROM datasets d WHERE d.tenant_id = %s AND d.project_id = %s
                     AND d.deleted_at IS NULL AND d.expires_at > now()
                   ORDER BY d.version DESC""",
                (identity.tenant_id, project_id),
            ).fetchall()
        if not rows:
            with psycopg.connect(str(config.database_url)) as connection:
                exists = connection.execute(
                    """SELECT 1 FROM projects WHERE tenant_id = %s AND id = %s
                       AND deleted_at IS NULL""",
                    (identity.tenant_id, project_id),
                ).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="project not found")
        return {"items": [serialize_dataset(row) for row in rows]}

    @router.get("/v1/datasets/{dataset_id}")
    def get_dataset(
        dataset_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            row = connection.execute(
                """SELECT d.id,
                          (SELECT a.id FROM artifacts a WHERE a.tenant_id = d.tenant_id
                             AND a.dataset_id = d.id AND a.kind = 'original'),
                          d.version, d.state, d.declared_format, d.detected_format,
                          d.original_bytes, d.sha256, d.created_at, d.expires_at
                   FROM datasets d WHERE d.tenant_id = %s AND d.id = %s
                     AND d.deleted_at IS NULL AND d.expires_at > now()""",
                (identity.tenant_id, dataset_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return serialize_dataset(row)

    @router.get("/v1/artifacts/{artifact_id}/content")
    def download_artifact(
        artifact_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> StreamingResponse:
        with psycopg.connect(str(config.database_url)) as connection:
            row = connection.execute(
                """SELECT a.object_key, d.display_filename FROM artifacts a JOIN datasets d
                       ON d.tenant_id = a.tenant_id AND d.id = a.dataset_id
                   WHERE a.tenant_id = %s AND a.id = %s AND a.state = 'ready'
                     AND d.state = 'ready' AND d.expires_at > now() AND d.deleted_at IS NULL""",
                (identity.tenant_id, artifact_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        body = S3Storage(config).get(row[0])

        def stream() -> Iterator[bytes]:
            try:
                yield from body.iter_chunks(chunk_size=64 * 1024)
            finally:
                body.close()

        return StreamingResponse(
            stream(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(row[1])}"},
        )

    @router.delete("/v1/datasets/{dataset_id}", status_code=status.HTTP_202_ACCEPTED)
    def delete_dataset(
        dataset_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            with connection.transaction():
                row = connection.execute(
                    """SELECT d.state, a.object_key FROM datasets d LEFT JOIN artifacts a
                         ON a.tenant_id = d.tenant_id AND a.dataset_id = d.id
                       WHERE d.tenant_id = %s AND d.id = %s FOR UPDATE OF d""",
                    (identity.tenant_id, dataset_id),
                ).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="dataset not found")
                if row[0] == "deleted":
                    return {"dataset_id": dataset_id, "state": "deleted"}
                connection.execute(
                    """UPDATE datasets SET state = 'delete_pending', deleted_at = now()
                       WHERE tenant_id = %s AND id = %s""",
                    (identity.tenant_id, dataset_id),
                )
                connection.execute(
                    """UPDATE upload_sessions SET state = 'delete_pending', updated_at = now()
                       WHERE tenant_id = %s AND dataset_id = %s
                         AND state NOT IN ('deleted','delete_pending')""",
                    (identity.tenant_id, dataset_id),
                )
                connection.execute(
                    """UPDATE artifacts SET state = 'delete_pending'
                       WHERE tenant_id = %s AND dataset_id = %s AND state <> 'deleted'""",
                    (identity.tenant_id, dataset_id),
                )
                connection.execute(
                    """INSERT INTO audit_events
                       (id, tenant_id, actor_principal_id, resource_type,
                        resource_id, action, details)
                       VALUES (%s,%s,%s,'dataset',%s,'delete_requested',
                               '{"scope":"stored assessment copy only"}'::jsonb)""",
                    (uuid4(), identity.tenant_id, identity.principal_id, dataset_id),
                )
        object_key = row[1]
        if object_key is not None:
            try:
                S3Storage(config).delete(object_key)
            except Exception:
                return {
                    "dataset_id": dataset_id,
                    "state": "delete_pending",
                    "scope": "stored assessment copy only",
                }
        with psycopg.connect(str(config.database_url)) as connection:
            connection.execute(
                """UPDATE datasets SET state = 'deleted'
                   WHERE tenant_id = %s AND id = %s AND state = 'delete_pending'""",
                (identity.tenant_id, dataset_id),
            )
            connection.execute(
                """UPDATE upload_sessions SET state = 'deleted', updated_at = now()
                   WHERE tenant_id = %s AND dataset_id = %s AND state = 'delete_pending'""",
                (identity.tenant_id, dataset_id),
            )
            connection.execute(
                """UPDATE artifacts SET state = 'deleted', deleted_at = now()
                   WHERE tenant_id = %s AND dataset_id = %s AND state = 'delete_pending'""",
                (identity.tenant_id, dataset_id),
            )
        return {
            "dataset_id": dataset_id,
            "state": "deleted",
            "scope": "stored assessment copy only",
        }

    return router


def serialize_dataset(row: tuple[Any, ...]) -> dict[str, object]:
    names = (
        "dataset_id",
        "artifact_id",
        "version",
        "state",
        "declared_format",
        "detected_format",
        "original_bytes",
        "sha256",
        "created_at",
        "expires_at",
    )
    result = dict(zip(names, row, strict=True))
    if row[1] is not None and row[3] == "ready":
        result["artifact_content_url"] = f"/v1/artifacts/{row[1]}/content"
    return result


def self_dataset_metadata(
    connection: psycopg.Connection[Any], tenant_id: str, dataset_id: UUID
) -> dict[str, object]:
    row = connection.execute(
        """SELECT d.id,
                  (SELECT a.id FROM artifacts a WHERE a.tenant_id = d.tenant_id
                     AND a.dataset_id = d.id AND a.kind = 'original'),
                  d.version, d.state, d.declared_format, d.detected_format,
                  d.original_bytes, d.sha256, d.created_at, d.expires_at
           FROM datasets d WHERE d.tenant_id = %s AND d.id = %s""",
        (tenant_id, dataset_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return serialize_dataset(row)
