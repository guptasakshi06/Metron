"""Dashboard discovery and side-effect-free executable-request validation."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from data_optimizer.auth.dependencies import identity_dependency
from data_optimizer.auth.identity import Identity
from data_optimizer.config import Settings
from data_optimizer.optimization.assessment import AssessmentRequest


def build_dashboard_router(config: Settings) -> APIRouter:
    router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])
    verified = identity_dependency(config)

    @router.get("/config")
    def configuration() -> dict[str, Any]:
        return {
            "version": 1,
            "auth_mode": config.auth_mode,
            "max_raw_upload_bytes": config.max_raw_upload_bytes,
            "max_decompressed_bytes": config.max_decompressed_bytes,
            "default_retention_days": config.default_retention_days,
        }

    @router.post("/validate")
    async def validate(
        request: Request, identity: Annotated[Identity, Depends(verified)]
    ) -> dict[str, Any]:
        del identity
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > 524_288:
                raise HTTPException(413, "assessment request byte limit exceeded")
            content.extend(chunk)
        try:
            result = AssessmentRequest.model_validate_json(content)
        except ValidationError as error:
            # Field locations and controlled error codes only; never echo input records/values.
            return {
                "valid": False,
                "issues": [
                    {"path": ".".join(map(str, item["loc"])), "code": item["type"]}
                    for item in error.errors(include_input=False, include_context=False)
                ],
            }
        return {"valid": True, "issues": [], "request": result.model_dump(mode="json")}

    return router
