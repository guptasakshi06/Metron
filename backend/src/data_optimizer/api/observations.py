"""Tenant-owned append-only adoption plans, observation revisions and comparisons."""

from decimal import Context, Decimal, localcontext
from typing import Annotated, Any
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from data_optimizer.api.assessments import load_result, owned
from data_optimizer.auth.dependencies import identity_dependency
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings
from data_optimizer.observations.models import ObservationInput, PlanInput
from data_optimizer.observations.service import evaluate, original_scenario
from data_optimizer.optimization.assessment import AssessmentReport


def report_for(config: Settings, item: UUID, identity: Identity) -> AssessmentReport:
    report = AssessmentReport.model_validate_json(load_result(config, item, identity))
    try:
        original_scenario(report)
    except (ValueError, StopIteration):
        raise HTTPException(
            409, "adoption requires a tested change with original cost evidence"
        ) from None
    return report


async def bounded_body(request: Request, model: type[BaseModel]) -> Any:
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 131072:
            raise HTTPException(413, "manual entry exceeds 128 KiB")
        data.extend(chunk)
    try:
        return model.model_validate_json(data)
    except ValueError:
        raise HTTPException(
            422, "invalid manual entry; inspect period, units and required fields"
        ) from None


def build_observations_router(config: Settings) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["observations"])
    verified = identity_dependency(config)

    def plan_row(plan: UUID, identity: Identity) -> dict[str, Any]:
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            row = db.execute(
                "SELECT * FROM migration_plans WHERE tenant_id=%s AND id=%s",
                (identity.tenant_id, plan),
            ).fetchone()
        if row is None:
            raise HTTPException(404, "migration plan not found")
        owned(config, identity.tenant_id, row["assessment_id"])
        return row

    @router.post("/assessments/{assessment_id}/migration-plan")
    async def save_plan(
        assessment_id: UUID, request: Request, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        report = report_for(config, assessment_id, identity)
        payload: PlanInput = await bounded_body(request, PlanInput)
        selected = next(
            c
            for c in report.decision.candidates
            if c.candidate_id == report.decision.selected_candidate_id
        )
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            db.execute(
                "SELECT id FROM assessments WHERE tenant_id=%s AND id=%s FOR UPDATE",
                (identity.tenant_id, assessment_id),
            )
            row = db.execute(
                "SELECT * FROM migration_plans WHERE tenant_id=%s AND assessment_id=%s",
                (identity.tenant_id, assessment_id),
            ).fetchone()
            previous = None
            if row:
                previous = db.execute(
                    "SELECT * FROM migration_plan_versions WHERE tenant_id=%s "
                    "AND plan_id=%s ORDER BY version DESC LIMIT 1",
                    (identity.tenant_id, row["id"]),
                ).fetchone()
            version = previous["version"] if previous else 0
            if payload.expected_version != version:
                raise HTTPException(409, "plan changed; reload history before editing")
            if previous:
                old = PlanInput.model_validate(previous["payload"])
                allowed = {
                    "proposed": {"proposed", "planned"},
                    "planned": {"planned", "deployed"},
                    "deployed": {"deployed", "reverted"},
                    "reverted": {"reverted"},
                }
                if payload.state not in allowed[old.state]:
                    raise HTTPException(422, "invalid adoption state transition")
                if payload.reference_logical_bytes != old.reference_logical_bytes:
                    raise HTTPException(422, "original logical reference is immutable; reassess")
                if old.deployed_at and payload.deployed_at != old.deployed_at:
                    raise HTTPException(422, "original deployment date is immutable")
                if old.reverted_at and payload.reverted_at != old.reverted_at:
                    raise HTTPException(422, "original revert date is immutable")
            elif payload.state != "proposed":
                raise HTTPException(422, "new plan must start proposed")
            plan = row["id"] if row else uuid4()
            if not row:
                db.execute(
                    "INSERT INTO migration_plans "
                    "(id,tenant_id,assessment_id,report_fingerprint,candidate_id,configuration) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        plan,
                        identity.tenant_id,
                        assessment_id,
                        report.report_fingerprint,
                        selected.candidate_id,
                        Jsonb(selected.configuration.model_dump(mode="json")),
                    ),
                )
            db.execute(
                "INSERT INTO migration_plan_versions "
                "(tenant_id,plan_id,version,payload,actor_principal_id) VALUES (%s,%s,%s,%s,%s)",
                (
                    identity.tenant_id,
                    plan,
                    version + 1,
                    Jsonb(payload.model_dump(mode="json")),
                    identity.principal_id,
                ),
            )
            audit(db, identity, plan, "plan_version_created")
        return {"id": plan, "version": version + 1}

    @router.get("/assessments/{assessment_id}/migration-plan")
    def get_plan(
        assessment_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        owned(config, identity.tenant_id, assessment_id)
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            row = db.execute(
                "SELECT id FROM migration_plans WHERE tenant_id=%s AND assessment_id=%s",
                (identity.tenant_id, assessment_id),
            ).fetchone()
        return history(row["id"], identity) if row else {"plan": None}

    @router.post("/migration-plans/{plan_id}/observations")
    async def save_observation(
        plan_id: UUID, request: Request, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        row = plan_row(plan_id, identity)
        report_for(config, row["assessment_id"], identity)
        payload: ObservationInput = await bounded_body(request, ObservationInput)
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            # Parent assessment lock serializes plan edits, revisions and overlap admission.
            db.execute(
                "SELECT id FROM assessments WHERE tenant_id=%s AND id=%s FOR UPDATE",
                (identity.tenant_id, row["assessment_id"]),
            )
            plan_version = db.execute(
                "SELECT * FROM migration_plan_versions WHERE tenant_id=%s "
                "AND plan_id=%s ORDER BY version DESC LIMIT 1",
                (identity.tenant_id, plan_id),
            ).fetchone()
            assert plan_version
            plan = PlanInput.model_validate(plan_version["payload"])
            if (
                not plan.deployed_at
                or payload.period_start < plan.deployed_at
                or (plan.reverted_at and payload.period_end > plan.reverted_at)
            ):
                raise HTTPException(422, "observations must lie within the deployment period")
            rows = db.execute(
                "SELECT DISTINCT ON (id) * FROM observations WHERE tenant_id=%s "
                "AND plan_id=%s ORDER BY id,version DESC",
                (identity.tenant_id, plan_id),
            ).fetchall()
            previous = next((r for r in rows if r["id"] == payload.observation_id), None)
            if payload.expected_version != (previous["version"] if previous else 0) or (
                payload.observation_id and not previous
            ):
                raise HTTPException(409, "observation changed or unavailable; reload history")
            for item in rows:
                old = ObservationInput.model_validate(item["payload"])
                if (
                    item["id"] != payload.observation_id
                    and not old.excluded
                    and not payload.excluded
                ):
                    if (
                        payload.period_start < old.period_end
                        and old.period_start < payload.period_end
                    ):
                        raise HTTPException(
                            409, "observation periods overlap; revise or exclude the old entry"
                        )
            observation = payload.observation_id or uuid4()
            version = payload.expected_version + 1
            db.execute(
                "INSERT INTO observations "
                "(id,tenant_id,plan_id,version,plan_version,payload,actor_principal_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    observation,
                    identity.tenant_id,
                    plan_id,
                    version,
                    plan_version["version"],
                    Jsonb(payload.model_dump(mode="json")),
                    identity.principal_id,
                ),
            )
            audit(db, identity, plan_id, "observation_revision_created")
        return {"id": observation, "version": version}

    @router.get("/migration-plans/{plan_id}/history")
    def history(plan_id: UUID, identity: Annotated[Identity, Depends(verified)]) -> dict[str, Any]:
        row = plan_row(plan_id, identity)
        report = report_for(config, row["assessment_id"], identity)
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            plans = db.execute(
                "SELECT version,payload,created_at,actor_principal_id FROM "
                "migration_plan_versions WHERE tenant_id=%s AND plan_id=%s "
                "ORDER BY version",
                (identity.tenant_id, plan_id),
            ).fetchall()
            observations = db.execute(
                "SELECT id,version,plan_version,payload,created_at,"
                "actor_principal_id FROM observations WHERE tenant_id=%s "
                "AND plan_id=%s ORDER BY created_at,version",
                (identity.tenant_id, plan_id),
            ).fetchall()
        current = PlanInput.model_validate(plans[-1]["payload"])
        latest: dict[str, dict[str, Any]] = {}
        for item in observations:
            key = str(item["id"])
            if key not in latest or item["version"] > latest[key]["version"]:
                latest[key] = item
        values = []
        for item in latest.values():
            obs = ObservationInput.model_validate(item["payload"])
            result = evaluate(report, current, obs)
            values.append({**item, "calculation": result})
        active = [r for r in values if not r["payload"]["excluded"]]
        total = None
        if (
            active
            and current.actual_migration_cost is not None
            and all(r["calculation"]["modeled_savings"] is not None for r in active)
        ):
            with localcontext(Context(prec=80)):
                total = sum(
                    (Decimal(r["calculation"]["modeled_savings"]) for r in active), Decimal(0)
                )
                total -= current.actual_migration_cost
        return {
            "plan": row,
            "versions": plans,
            "observation_revisions": observations,
            "observations": values,
            "cumulative_modeled_benefit": str(total) if total is not None else None,
            "cumulative_scope": "Latest non-excluded recorded periods only; "
            "gaps are not estimated. "
            "Subtract latest user-supplied actual migration cost once. Not verified savings.",
            "currency": original_scenario(report).prices.currency,
        }

    @router.get("/assessments/{assessment_id}/comparison")
    def comparison(
        assessment_id: UUID, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        current = owned(config, identity.tenant_id, assessment_id)
        with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
            link = db.execute(
                "SELECT * FROM reassessment_links WHERE tenant_id=%s AND assessment_id=%s",
                (identity.tenant_id, assessment_id),
            ).fetchone()
        if not link:
            return {"previous": None}
        previous = owned(config, identity.tenant_id, link["previous_assessment_id"])

        def result(row: dict[str, Any]) -> dict[str, Any]:
            report = (
                AssessmentReport.model_validate_json(load_result(config, row["id"], identity))
                if row["result_key"]
                else None
            )
            return {
                "id": row["id"],
                "input_fingerprint": row["input_fingerprint"],
                "request_fingerprint": row["request_fingerprint"],
                "status": row["status"],
                "decision": report.decision if report else None,
                "price_snapshot_ids": sorted(
                    {
                        s.prices.snapshot_id
                        for c in report.costs.values()
                        for s in c.request.scenarios
                    }
                )
                if report
                else [],
            }

        return {
            "reason": link["reason"],
            "previous": result(previous),
            "current": result(current),
            "limitation": "Independent evidence versions; differing usage, currency and prices "
            "are not directly attributable savings.",
        }

    return router


def audit(db: psycopg.Connection[Any], identity: Identity, item: UUID, action: str) -> None:
    db.execute(
        "INSERT INTO audit_events "
        "(id,tenant_id,actor_principal_id,resource_type,resource_id,action) "
        "VALUES (%s,%s,%s,'migration_plan',%s,%s)",
        (uuid4(), identity.tenant_id, identity.principal_id, item, action),
    )
