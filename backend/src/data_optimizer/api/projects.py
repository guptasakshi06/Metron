"""Tenant-scoped project creation and lookup routes."""

from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from data_optimizer.auth.dependencies import identity_dependency
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings

PROJECT_COLUMNS = ("project_id", "name", "business_context", "version", "created_at")


def _serialize_project(row: tuple[object, ...]) -> dict[str, object]:
    return dict(zip(PROJECT_COLUMNS, row, strict=True))


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    business_context: str | None = Field(default=None, max_length=4000)


def build_projects_router(config: Settings) -> APIRouter:
    router = APIRouter(prefix="/v1/projects", tags=["projects"])
    verified_identity = identity_dependency(config)

    @router.post("", status_code=status.HTTP_201_CREATED)
    def create_project(
        payload: ProjectCreate,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        project_id = uuid4()
        with psycopg.connect(str(config.database_url)) as connection:
            created_row = connection.execute(
                """INSERT INTO projects (id, tenant_id, owner_principal_id, name, business_context)
                   VALUES (%s, %s, %s, %s, %s) RETURNING created_at""",
                (
                    project_id,
                    identity.tenant_id,
                    identity.principal_id,
                    payload.name,
                    payload.business_context,
                ),
            ).fetchone()
            if created_row is None:
                raise RuntimeError("project insert returned no creation timestamp")
            created_at = created_row[0]
            connection.execute(
                """INSERT INTO audit_events
                   (id, tenant_id, actor_principal_id, resource_type, resource_id, action)
                   VALUES (%s, %s, %s, 'project', %s, 'created')""",
                (uuid4(), identity.tenant_id, identity.principal_id, project_id),
            )
        return {
            "project_id": project_id,
            "name": payload.name,
            "business_context": payload.business_context,
            "version": 1,
            "created_at": created_at,
        }

    @router.get("")
    def list_projects(
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            rows = connection.execute(
                """SELECT id, name, business_context, version, created_at
                   FROM projects WHERE tenant_id = %s AND deleted_at IS NULL
                   ORDER BY created_at DESC""",
                (identity.tenant_id,),
            ).fetchall()
        return {"items": [_serialize_project(row) for row in rows]}

    @router.get("/{project_id}")
    def get_project(
        project_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            row = connection.execute(
                """SELECT id, name, business_context, version, created_at
                   FROM projects WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL""",
                (identity.tenant_id, project_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="project not found")
        return _serialize_project(row)

    @router.delete("/{project_id}", status_code=status.HTTP_202_ACCEPTED)
    def delete_project(
        project_id: UUID,
        identity: Annotated[Identity, Depends(verified_identity)],
    ) -> dict[str, object]:
        with psycopg.connect(str(config.database_url)) as connection:
            with connection.transaction():
                row = connection.execute(
                    """UPDATE projects SET deleted_at = now()
                       WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL RETURNING id""",
                    (identity.tenant_id, project_id),
                ).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="project not found")
                connection.execute(
                    """UPDATE datasets SET state = 'delete_pending', deleted_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND state <> 'deleted'""",
                    (identity.tenant_id, project_id),
                )
                connection.execute(
                    """UPDATE upload_sessions SET state = 'delete_pending', updated_at = now()
                       WHERE tenant_id = %s AND dataset_id IN
                         (SELECT id FROM datasets WHERE tenant_id = %s AND project_id = %s)
                         AND state NOT IN ('deleted', 'delete_pending')""",
                    (identity.tenant_id, identity.tenant_id, project_id),
                )
                connection.execute(
                    """UPDATE artifacts SET state = 'delete_pending'
                       WHERE tenant_id = %s AND dataset_id IN
                         (SELECT id FROM datasets WHERE tenant_id = %s AND project_id = %s)""",
                    (identity.tenant_id, identity.tenant_id, project_id),
                )
                connection.execute(
                    """INSERT INTO audit_events
                       (id, tenant_id, actor_principal_id, resource_type,
                        resource_id, action, details)
                       VALUES (%s, %s, %s, 'project', %s, 'delete_requested',
                               '{"scope":"stored assessment copies only"}'::jsonb)""",
                    (uuid4(), identity.tenant_id, identity.principal_id, project_id),
                )
        return {
            "project_id": project_id,
            "status": "delete_pending",
            "scope": "stored assessment copies only",
        }

    return router
