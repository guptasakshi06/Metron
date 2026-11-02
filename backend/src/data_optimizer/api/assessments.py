"""Authenticated asynchronous assessment submission and evidence retrieval."""

from typing import Annotated, Any
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from data_optimizer.auth.dependencies import identity_dependency
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings
from data_optimizer.jobs.models import Submission, bounded_request
from data_optimizer.profiling.models import fingerprint
from data_optimizer.storage.s3 import S3Storage

# Rechecked on every read, including result downloads and cancellation.
VISIBLE = """SELECT a.* FROM assessments a JOIN projects p
 ON (p.tenant_id,p.id)=(a.tenant_id,a.project_id)
 LEFT JOIN datasets d ON (d.tenant_id,d.id)=(a.tenant_id,a.dataset_id)
 LEFT JOIN profiles f ON (f.tenant_id,f.id)=(a.tenant_id,a.profile_id)
 WHERE a.tenant_id=%s AND a.id=%s AND p.deleted_at IS NULL AND a.expires_at>now()
 AND (a.dataset_id IS NULL OR (d.state='ready' AND d.expires_at>now()))
 AND (a.profile_id IS NULL OR f.deleted_at IS NULL)"""


def owned(config: Settings, tenant: UUID | str, assessment: UUID) -> dict[str, Any]:
    with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
        row = db.execute(VISIBLE, (tenant, assessment)).fetchone()
    if row is None:
        raise HTTPException(404, "assessment not found")
    return row


def summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "id",
            "project_id",
            "dataset_id",
            "profile_id",
            "requirements_id",
            "status",
            "progress",
            "attempts",
            "cancel_requested",
            "stop_reason",
            "created_at",
            "updated_at",
            "expires_at",
            "request_fingerprint",
            "input_fingerprint",
        )
    }


def build_assessments_router(config: Settings) -> APIRouter:
    router = APIRouter(prefix="/v1/assessments", tags=["assessments"])
    verified = identity_dependency(config)

    @router.post("", status_code=202)
    async def create(
        request: Request,
        identity: Annotated[Identity, Depends(verified)],
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > 524_288:
                raise HTTPException(413, "assessment request byte limit exceeded")
            content.extend(chunk)
        try:
            payload = Submission.model_validate_json(content)
            normalized = bounded_request(
                payload.request, config, UUID(identity.tenant_id), UUID(int=0)
            )
        except (ValueError, ValidationError):
            raise HTTPException(422, "invalid assessment request") from None
        digest = fingerprint(
            {**payload.model_dump(mode="json"), "request": normalized.model_dump(mode="json")}
        )
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            # Tenant row lock serializes quota admission and duplicate creation.
            db.execute("SELECT id FROM tenants WHERE id=%s FOR UPDATE", (identity.tenant_id,))
            existing = db.execute(
                "SELECT * FROM assessments WHERE tenant_id=%s AND idempotency_key=%s",
                (identity.tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_fingerprint"] != digest:
                    raise HTTPException(409, "idempotency key already used for different inputs")
                owned(config, identity.tenant_id, existing["id"])
                return {**summary(existing), "reused": True}
            project = db.execute(
                "SELECT id FROM projects WHERE tenant_id=%s AND id=%s AND deleted_at IS NULL "
                "FOR UPDATE",
                (identity.tenant_id, payload.project_id),
            ).fetchone()
            if not project:
                raise HTTPException(404, "project not found")
            input_hash = fingerprint(["startup", payload.project_id.hex])
            expires = None
            if payload.dataset_id:
                dataset = db.execute(
                    "SELECT * FROM datasets WHERE tenant_id=%s AND project_id=%s AND id=%s "
                    "AND state='ready' AND expires_at>now() FOR SHARE",
                    (identity.tenant_id, payload.project_id, payload.dataset_id),
                ).fetchone()
                if not dataset:
                    raise HTTPException(404, "ready dataset not found")
                assert normalized.conversion
                if normalized.conversion.source.format != dataset["detected_format"]:
                    raise HTTPException(422, "reader format does not match uploaded dataset")
                input_hash, expires = dataset["sha256"], dataset["expires_at"]
            elif payload.profile_id:
                profile = db.execute(
                    "SELECT * FROM profiles WHERE tenant_id=%s AND project_id=%s AND id=%s "
                    "AND deleted_at IS NULL FOR SHARE",
                    (identity.tenant_id, payload.project_id, payload.profile_id),
                ).fetchone()
                if not profile:
                    raise HTTPException(404, "profile not found")
                input_hash = profile["profile_fingerprint"]
            count = db.execute(
                "SELECT count(*) AS n FROM assessments WHERE tenant_id=%s AND "
                "status IN ('queued','profiling','benchmarking','scoring') AND expires_at>now()",
                (identity.tenant_id,),
            ).fetchone()
            assert count
            if count["n"] >= config.max_active_assessments_per_tenant:
                raise HTTPException(429, "tenant active assessment quota reached")
            assessment, requirements = uuid4(), uuid4()
            actual = bounded_request(normalized, config, UUID(identity.tenant_id), assessment)
            version = db.execute(
                "SELECT COALESCE(max(version),0)+1 AS n FROM requirements_snapshots "
                "WHERE tenant_id=%s AND project_id=%s",
                (identity.tenant_id, payload.project_id),
            ).fetchone()
            assert version
            db.execute(
                "INSERT INTO requirements_snapshots "
                "(id,tenant_id,project_id,version,contract_version,payload) "
                "VALUES (%s,%s,%s,%s,1,%s)",
                (
                    requirements,
                    identity.tenant_id,
                    payload.project_id,
                    version["n"],
                    Jsonb(actual.policy.model_dump(mode="json")),
                ),
            )
            row = db.execute(
                """INSERT INTO assessments (id,tenant_id,project_id,dataset_id,profile_id,
                requirements_id,idempotency_key,input_fingerprint,request_fingerprint,request,
                status,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',
                COALESCE(%s,now()+(%s * interval '1 day'))) RETURNING *""",
                (
                    assessment,
                    identity.tenant_id,
                    payload.project_id,
                    payload.dataset_id,
                    payload.profile_id,
                    requirements,
                    idempotency_key,
                    input_hash,
                    digest,
                    Jsonb(actual.model_dump(mode="json")),
                    expires,
                    config.default_retention_days,
                ),
            ).fetchone()
            db.execute(
                "INSERT INTO audit_events (id,tenant_id,actor_principal_id,resource_type,"
                "resource_id,action) VALUES (%s,%s,%s,'assessment',%s,'created')",
                (uuid4(), identity.tenant_id, identity.principal_id, assessment),
            )
            assert row
            return {**summary(row), "reused": False}

    @router.get("")
    def list_assessments(
        identity: Annotated[Identity, Depends(verified)], project_id: UUID | None = None
    ) -> dict[str, Any]:
        query = VISIBLE.replace("AND a.id=%s", "")
        values: list[Any] = [identity.tenant_id]
        if project_id is not None:
            query += " AND a.project_id=%s"
            values.append(project_id)
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            rows = db.execute(query + " ORDER BY a.created_at DESC LIMIT 100", values).fetchall()
        return {"items": [summary(row) for row in rows]}

    @router.get("/{assessment_id}")
    def status(
        assessment_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        return summary(owned(config, identity.tenant_id, assessment_id))

    @router.post("/{assessment_id}/cancel", status_code=202)
    def cancel(
        assessment_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        owned(config, identity.tenant_id, assessment_id)
        with psycopg.connect(str(config.database_url)) as db:
            db.execute(
                """UPDATE assessments SET cancel_requested=true,updated_at=now(),
                status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END,
                stop_reason=CASE WHEN status='queued' THEN 'user_cancelled' ELSE stop_reason END
                WHERE tenant_id=%s AND id=%s
                AND status IN ('queued','profiling','benchmarking','scoring')""",
                (identity.tenant_id, assessment_id),
            )
        return summary(owned(config, identity.tenant_id, assessment_id))

    def result(assessment_id: UUID, identity: Identity) -> bytes:
        import hashlib

        row = owned(config, identity.tenant_id, assessment_id)
        if row["result_key"] is None:
            raise HTTPException(409, "result is not available; inspect status and progress")
        body = S3Storage(config).get(row["result_key"])
        try:
            data: bytes = body.read(67_108_865)
        finally:
            body.close()
        if (
            len(data) != row["result_bytes"]
            or hashlib.sha256(data).hexdigest() != row["result_sha256"]
        ):
            raise HTTPException(503, "result integrity check failed")
        return data

    @router.get("/{assessment_id}/result")
    def raw_result(
        assessment_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> Response:
        return Response(result(assessment_id, identity), media_type="application/json")

    @router.get("/{assessment_id}/recommendations")
    def recommendations(
        assessment_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        import json

        data = json.loads(result(assessment_id, identity))
        return {
            "assessment_id": assessment_id,
            "decision": data["decision"],
            "report_fingerprint": data["report_fingerprint"],
        }

    return router
