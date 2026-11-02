"""Owned expiring export grants; no bearer URLs, secrets, or public object access."""

from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from psycopg.rows import dict_row

from data_optimizer.api.assessments import load_result, owned
from data_optimizer.auth.dependencies import identity_dependency
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings
from data_optimizer.optimization.assessment import AssessmentReport
from data_optimizer.profiling.models import fingerprint
from data_optimizer.reports.models import AssessmentBundle, Provenance
from data_optimizer.reports.service import archive, export_files, make_bundle

ExportFormat = Literal["zip", "json", "markdown", "html"]
FORMATS = {
    "zip": ("handoff.zip", "application/zip"),
    "json": ("bundle.json", "application/json"),
    "markdown": ("report.md", "text/markdown; charset=utf-8"),
    "html": ("report.html", "text/html; charset=utf-8"),
}


def bundle_for(config: Settings, item: UUID, identity: Identity) -> AssessmentBundle:
    row = owned(config, identity.tenant_id, item)
    provenance = Provenance(
        assessment_id=str(item),
        requirements_id=str(row["requirements_id"]),
        raw_result_reference=f"/v1/assessments/{item}/result",
        input_fingerprint=row["input_fingerprint"],
        submission_fingerprint=row["request_fingerprint"],
    )
    if row["intake_confirmation_id"]:
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            confirmation = db.execute(
                "SELECT id,version,proposal_id,requirements_fingerprint,accepted_request "
                "FROM intake_confirmations WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (identity.tenant_id, row["project_id"], row["intake_confirmation_id"]),
            ).fetchone()
        if confirmation is None:
            raise HTTPException(503, "confirmation provenance unavailable")
        provenance = provenance.model_copy(
            update={
                "confirmation_id": str(confirmation["id"]),
                "confirmation_version": confirmation["version"],
                "proposal_id": str(confirmation["proposal_id"]),
                "accepted_requirements_fingerprint": confirmation["requirements_fingerprint"],
                "accepted_request_fingerprint": fingerprint(confirmation["accepted_request"]),
            }
        )
    try:
        return make_bundle(
            AssessmentReport.model_validate_json(load_result(config, item, identity)), provenance
        )
    except ValueError:
        raise HTTPException(503, "stored report cannot be exported") from None


def build_reports_router(config: Settings) -> APIRouter:
    router = APIRouter(prefix="/v1/assessments", tags=["reports"])
    verified = identity_dependency(config)

    @router.post("/{assessment_id}/handoff")
    def create_download(
        assessment_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, object]:
        bundle = bundle_for(config, assessment_id, identity)
        row = owned(config, identity.tenant_id, assessment_id)
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            grant = db.execute(
                "INSERT INTO assessment_downloads "
                "(id,tenant_id,assessment_id,bundle_fingerprint,expires_at) "
                "VALUES (%s,%s,%s,%s,LEAST(%s,now()+(%s * interval '1 second'))) "
                "ON CONFLICT (tenant_id,assessment_id,bundle_fingerprint) DO UPDATE "
                "SET id=EXCLUDED.id,created_at=EXCLUDED.created_at,expires_at=EXCLUDED.expires_at "
                "RETURNING id,expires_at",
                (
                    uuid4(),
                    identity.tenant_id,
                    assessment_id,
                    bundle.bundle_fingerprint,
                    row["expires_at"],
                    config.report_download_ttl_seconds,
                ),
            ).fetchone()
        assert grant
        return {
            "download_id": str(grant["id"]),
            "expires_at": grant["expires_at"],
            "bundle_fingerprint": bundle.bundle_fingerprint,
            "links": {
                kind: f"/v1/assessments/{assessment_id}/handoff/{grant['id']}/{kind}"
                for kind in FORMATS
            },
        }

    @router.get("/{assessment_id}/handoff/{download_id}/{format}")
    def download(
        assessment_id: UUID,
        download_id: UUID,
        format: ExportFormat,
        identity: Annotated[Identity, Depends(verified)],
    ) -> Response:
        owned(config, identity.tenant_id, assessment_id)
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            grant = db.execute(
                "SELECT bundle_fingerprint FROM assessment_downloads WHERE tenant_id=%s "
                "AND assessment_id=%s AND id=%s AND expires_at>now()",
                (identity.tenant_id, assessment_id, download_id),
            ).fetchone()
        if grant is None:
            raise HTTPException(404, "download unavailable or expired; request new links")
        bundle = bundle_for(config, assessment_id, identity)
        if bundle.bundle_fingerprint != grant["bundle_fingerprint"]:
            raise HTTPException(409, "export changed; request new links")
        # Ownership/expiry/deletion are checked again after reading and rendering the result.
        name, media = FORMATS[format]
        content = archive(bundle) if format == "zip" else export_files(bundle)[name]
        owned(config, identity.tenant_id, assessment_id)
        with psycopg.connect(str(config.database_url)) as db:
            if not db.execute(
                "SELECT 1 FROM assessment_downloads WHERE tenant_id=%s AND id=%s "
                "AND expires_at>now()",
                (identity.tenant_id, download_id),
            ).fetchone():
                raise HTTPException(404, "download expired; request new links")
        return Response(
            content,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                "Referrer-Policy": "no-referrer",
            },
        )

    return router
