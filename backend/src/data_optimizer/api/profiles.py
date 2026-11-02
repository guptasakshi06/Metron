"""Tenant-scoped, reviewed local-metadata import. No raw dataset upload implied."""

from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from data_optimizer.auth.dependencies import identity_dependency
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings
from data_optimizer.profiling.models import Digest, Model, ProfileReport, report_digest
from data_optimizer.profiling.service import MAX_REPORT_BYTES


class ProfileImport(Model):
    report: ProfileReport
    reviewed_fingerprint: Digest


def build_profiles_router(config: Settings) -> APIRouter:
    router = APIRouter(prefix="/v1/projects/{project_id}/profiles", tags=["profiles"])
    verified_identity = identity_dependency(config)

    @router.post("", status_code=201)
    async def import_profile(
        project_id: UUID,
        request: Request,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_REPORT_BYTES:
                raise HTTPException(413, "metadata report limit exceeded")
            content.extend(chunk)
        try:
            payload = ProfileImport.model_validate_json(bytes(content))
            report = payload.report
            if report.evidence != "local_profile" or report.raw_data_inspected_by_server:
                raise ValueError("only reviewed local profiles may be imported")
            if report_digest(report) != report.profile_fingerprint:
                raise ValueError()
            if payload.reviewed_fingerprint != report.profile_fingerprint:
                raise ValueError()
        except (ValueError, ValidationError):
            raise HTTPException(
                422, "invalid report or missing matching review fingerprint"
            ) from None
        with psycopg.connect(str(config.database_url)) as connection:
            project = connection.execute(
                """SELECT id FROM projects WHERE tenant_id = %s AND id = %s
                   AND deleted_at IS NULL FOR UPDATE""",
                (identity.tenant_id, project_id),
            ).fetchone()
            if project is None:
                raise HTTPException(404, "project not found")
            existing = connection.execute(
                """SELECT id, version, deleted_at FROM profiles
                   WHERE tenant_id = %s AND project_id = %s AND profile_fingerprint = %s""",
                (identity.tenant_id, project_id, report.profile_fingerprint),
            ).fetchone()
            if existing:
                if existing[2] is not None:
                    raise HTTPException(409, "profile was deleted; generate a new version")
                return {
                    "profile_id": existing[0],
                    "profile_version": existing[1],
                    "evidence": "local_profile",
                    "raw_data_inspected_by_server": False,
                    "reused": True,
                }
            count = connection.execute(
                "SELECT count(*), COALESCE(max(version), 0) FROM profiles "
                "WHERE tenant_id = %s AND project_id = %s",
                (identity.tenant_id, project_id),
            ).fetchone()
            assert count is not None
            if count[0] >= config.max_profiles_per_project:
                raise HTTPException(429, "project metadata profile quota reached")
            profile_id, version = uuid4(), count[1] + 1
            connection.execute(
                """INSERT INTO profiles
                   (id, tenant_id, project_id, version, contract_version, profile_fingerprint,
                    input_fingerprint, schema_fingerprint, settings_fingerprint, evidence, payload)
                   VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s,'local_profile',%s)""",
                (
                    profile_id,
                    identity.tenant_id,
                    project_id,
                    version,
                    report.profile_fingerprint,
                    report.input_fingerprint,
                    report.schema_fingerprint,
                    report.settings_fingerprint,
                    Jsonb(report.model_dump(mode="json")),
                ),
            )
            connection.execute(
                """INSERT INTO audit_events
                   (id, tenant_id, actor_principal_id, resource_type, resource_id, action)
                   VALUES (%s,%s,%s,'profile',%s,'local_metadata_imported')""",
                (uuid4(), identity.tenant_id, identity.principal_id, profile_id),
            )
        return {
            "profile_id": profile_id,
            "profile_version": version,
            "evidence": "local_profile",
            "raw_data_inspected_by_server": False,
            "reused": False,
        }

    @router.get("")
    def list_profiles(
        project_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            found = connection.execute(
                "SELECT id FROM projects WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL",
                (identity.tenant_id, project_id),
            ).fetchone()
            if found is None:
                raise HTTPException(404, "project not found")
            found_rows = connection.execute(
                """SELECT id, version, profile_fingerprint, created_at FROM profiles
                   WHERE tenant_id = %s AND project_id = %s AND deleted_at IS NULL
                   ORDER BY version DESC""",
                (identity.tenant_id, project_id),
            ).fetchall()
        return {
            "items": [
                dict(
                    zip(
                        ("profile_id", "profile_version", "profile_fingerprint", "created_at"),
                        row,
                        strict=True,
                    )
                )
                for row in found_rows
            ]
        }

    @router.get("/{profile_id}")
    def get_profile(
        project_id: UUID,
        profile_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            row = connection.execute(
                """SELECT p.version, p.payload FROM profiles p JOIN projects j
                   ON j.tenant_id = p.tenant_id AND j.id = p.project_id
                   WHERE p.tenant_id = %s AND p.project_id = %s AND p.id = %s
                   AND p.deleted_at IS NULL AND j.deleted_at IS NULL""",
                (identity.tenant_id, project_id, profile_id),
            ).fetchone()
        if row is None:
            raise HTTPException(404, "profile not found")
        return {"profile_id": profile_id, "profile_version": row[0], "report": row[1]}

    @router.delete("/{profile_id}")
    def delete_profile(
        project_id: UUID,
        profile_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            row = connection.execute(
                """UPDATE profiles SET deleted_at = now(), payload = '{}'::jsonb
                   WHERE tenant_id = %s AND project_id = %s AND id = %s
                   AND deleted_at IS NULL AND EXISTS
                   (SELECT 1 FROM projects WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL)
                   RETURNING id""",
                (identity.tenant_id, project_id, profile_id, identity.tenant_id, project_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "profile not found")
            connection.execute(
                """INSERT INTO audit_events
                   (id, tenant_id, actor_principal_id, resource_type, resource_id, action)
                   VALUES (%s,%s,%s,'profile',%s,'metadata_deleted')""",
                (uuid4(), identity.tenant_id, identity.principal_id, profile_id),
            )
        return {"profile_id": profile_id, "status": "deleted"}

    return router
