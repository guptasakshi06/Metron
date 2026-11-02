"""Owned proposal/review/confirm workflow and opt-in summary-only explanations."""

from typing import Annotated, Any
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from data_optimizer.api.assessments import load_result, owned
from data_optimizer.auth.dependencies import identity_dependency
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings
from data_optimizer.explanations.service import (
    ExplanationSelection,
    allowed_cards,
    render_cards,
    validate_cards,
)
from data_optimizer.intake.models import (
    Approval,
    ConfirmationInput,
    IntakeInput,
    IntakeResult,
    IntakeSelection,
)
from data_optimizer.intake.service import (
    QUESTIONS,
    extract,
    requirements_fingerprint,
    validate_selection,
)
from data_optimizer.jobs.models import bounded_request
from data_optimizer.llm.service import assist
from data_optimizer.optimization.assessment import AssessmentReport
from data_optimizer.profiling.models import fingerprint


async def bounded_body(request: Request, model: type[BaseModel]) -> Any:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > 524288:
            raise HTTPException(413, "assistance request byte limit exceeded")
        content.extend(chunk)
    try:
        return model.model_validate_json(content)
    except ValidationError:
        raise HTTPException(422, "invalid assistance request") from None


def project_exists(config: Settings, identity: Identity, project: UUID) -> None:
    with psycopg.connect(str(config.database_url)) as db:
        row = db.execute(
            "SELECT id FROM projects WHERE tenant_id=%s AND id=%s AND deleted_at IS NULL",
            (identity.tenant_id, project),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "project not found")


def proposal(config: Settings, identity: Identity, project: UUID, item: UUID) -> IntakeResult:
    project_exists(config, identity, project)
    with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
        row = db.execute(
            "SELECT payload FROM intake_proposals WHERE tenant_id=%s AND project_id=%s AND id=%s",
            (identity.tenant_id, project, item),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "intake proposal not found")
    return IntakeResult.model_validate(row["payload"])


def save_proposal(
    config: Settings, identity: Identity, project: UUID, result: IntakeResult
) -> None:
    with psycopg.connect(str(config.database_url)) as db:
        db.execute(
            "INSERT INTO intake_proposals (id,tenant_id,project_id,payload) VALUES (%s,%s,%s,%s)",
            (result.id, identity.tenant_id, project, Jsonb(result.model_dump(mode="json"))),
        )


def build_assistance_router(config: Settings) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["assistance"])
    verified = identity_dependency(config)

    @router.post("/projects/{project_id}/intake")
    async def intake(
        project_id: UUID, request: Request, identity: Annotated[Identity, Depends(verified)]
    ) -> IntakeResult:
        project_exists(config, identity, project_id)
        body: IntakeInput = await bounded_body(request, IntakeInput)
        baseline = extract(body.description, body.request)
        summary: dict[str, Any] = {
            "prompt_version": "s11.1",
            "description": body.description,
            "allowed_fields": [f.model_dump(mode="json") for f in baseline.fields],
            "allowed_questions": list(baseline.questions),
        }
        result = IntakeResult(
            id=uuid4(),
            original_description=body.description,
            fields=baseline.fields,
            questions={q: QUESTIONS[q] for q in baseline.questions},
            summary=summary,
            summary_fingerprint=fingerprint(summary),
            source="deterministic",
            status="not_requested",
        )
        save_proposal(config, identity, project_id, result)
        return result

    @router.get("/projects/{project_id}/intake/{proposal_id}")
    def get_intake(
        project_id: UUID, proposal_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> IntakeResult:
        return proposal(config, identity, project_id, proposal_id)

    @router.post("/projects/{project_id}/intake/{proposal_id}/refine")
    async def refine(
        project_id: UUID,
        proposal_id: UUID,
        request: Request,
        identity: Annotated[Identity, Depends(verified)],
    ) -> IntakeResult:
        previous = proposal(config, identity, project_id, proposal_id)
        approval: Approval = await bounded_body(request, Approval)
        if approval.approved_summary_fingerprint != previous.summary_fingerprint:
            raise HTTPException(409, "review the current assistance summary first")
        baseline = IntakeSelection.model_validate(
            {
                "fields": previous.summary["allowed_fields"],
                "questions": previous.summary["allowed_questions"],
            }
        )
        value, status = await run_in_threadpool(
            assist,
            config,
            identity.tenant_id,
            project_id,
            project_id,
            previous.summary,
            IntakeSelection,
            lambda v: validate_selection(v, baseline),
        )
        selection = IntakeSelection.model_validate(value) if value else baseline
        result = previous.model_copy(
            update={
                "id": uuid4(),
                "fields": selection.fields,
                "questions": {q: QUESTIONS[q] for q in selection.questions},
                "source": "provider" if value else "deterministic",
                "status": status,
            }
        )
        save_proposal(config, identity, project_id, result)
        return result

    @router.post("/projects/{project_id}/intake/{proposal_id}/confirm")
    async def confirm(
        project_id: UUID,
        proposal_id: UUID,
        request: Request,
        identity: Annotated[Identity, Depends(verified)],
    ) -> dict[str, Any]:
        proposal(config, identity, project_id, proposal_id)
        body: ConfirmationInput = await bounded_body(request, ConfirmationInput)
        accepted = bounded_request(body.request, config, UUID(identity.tenant_id), UUID(int=0))
        digest = requirements_fingerprint(accepted)
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            db.execute(
                "SELECT id FROM projects WHERE tenant_id=%s AND id=%s FOR UPDATE",
                (identity.tenant_id, project_id),
            )
            version = db.execute(
                "SELECT COALESCE(max(version),0)+1 AS n FROM intake_confirmations "
                "WHERE tenant_id=%s AND project_id=%s",
                (identity.tenant_id, project_id),
            ).fetchone()
            assert version
            item = uuid4()
            db.execute(
                "INSERT INTO intake_confirmations (id,tenant_id,project_id,proposal_id,version,"
                "accepted_request,requirements_fingerprint) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    item,
                    identity.tenant_id,
                    project_id,
                    proposal_id,
                    version["n"],
                    Jsonb(accepted.model_dump(mode="json")),
                    digest,
                ),
            )
        return {"id": item, "version": version["n"], "requirements_fingerprint": digest}

    @router.get("/assessments/{assessment_id}/explanation")
    def explanation_preview(
        assessment_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        return explanation(assessment_id, identity, None)

    @router.post("/assessments/{assessment_id}/explanation")
    async def explain(
        assessment_id: UUID, request: Request, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        approval: Approval = await bounded_body(request, Approval)
        return await run_in_threadpool(
            explanation, assessment_id, identity, approval.approved_summary_fingerprint
        )

    def explanation(
        assessment_id: UUID, identity: Identity, approved: str | None
    ) -> dict[str, Any]:
        row = owned(config, identity.tenant_id, assessment_id)
        report = AssessmentReport.model_validate_json(load_result(config, assessment_id, identity))
        allowed = allowed_cards(report)
        summary = {
            "prompt_version": "s11.1",
            "report_fingerprint": report.report_fingerprint,
            "decision_fingerprint": report.decision.decision_fingerprint,
            "outcome": report.decision.outcome,
            "allowed_cards": allowed.model_dump()["cards"],
        }
        digest = fingerprint(summary)
        value, status = None, "not_requested"
        if approved is not None:
            if approved != digest:
                raise HTTPException(409, "review the current explanation summary first")
            value, status = assist(
                config,
                identity.tenant_id,
                row["project_id"],
                assessment_id,
                summary,
                ExplanationSelection,
                lambda v: validate_cards(v, allowed),
            )
        selection = ExplanationSelection.model_validate(value) if value else allowed
        # Scope warning is mandatory even if the provider omits it.
        if allowed.cards[0] not in selection.cards:
            selection = ExplanationSelection(cards=(allowed.cards[0], *selection.cards)[:24])
        return {
            "version": "s11.1",
            "source": "provider" if value else "deterministic",
            "status": status,
            "summary": summary,
            "summary_fingerprint": digest,
            "report_fingerprint": report.report_fingerprint,
            "cards": render_cards(selection),
        }

    return router
