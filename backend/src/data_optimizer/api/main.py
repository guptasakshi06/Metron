"""FastAPI application with liveness and honest dependency readiness."""

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from data_optimizer import __version__
from data_optimizer.api.assessments import build_assessments_router
from data_optimizer.api.datasets import build_datasets_router
from data_optimizer.api.probes import Probe, dependency_report
from data_optimizer.api.profiles import build_profiles_router
from data_optimizer.api.projects import build_projects_router
from data_optimizer.config import Settings, settings
from data_optimizer.domain.contracts import ErrorEnvelope, ReadinessResponse


def create_app(
    config: Settings = settings,
    probes: Mapping[str, Probe] | None = None,
) -> FastAPI:
    """Build an API instance; optional probes support isolated readiness tests."""
    application = FastAPI(title="Data Optimizer API", version=__version__)
    application.include_router(build_assessments_router(config))
    application.include_router(build_projects_router(config))
    application.include_router(build_profiles_router(config))
    application.include_router(build_datasets_router(config))

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """Report that this process is alive; dependency state belongs to /ready."""
        return {"status": "ok", "version": __version__}

    @application.get("/ready", response_model=ReadinessResponse, tags=["system"])
    async def ready(response: Response) -> ReadinessResponse:
        """Return ready only after all configured local dependencies answer real probes."""
        dependencies = await dependency_report(config, probes)
        is_ready = all(dependency.status == "up" for dependency in dependencies.values())
        response.status_code = 200 if is_ready else 503
        return ReadinessResponse(
            status="ready" if is_ready else "not_ready", dependencies=dependencies
        )

    @application.exception_handler(psycopg.Error)
    @application.exception_handler(BotoCoreError)
    @application.exception_handler(ClientError)
    async def dependency_error_handler(request: Request, exc: Exception) -> JSONResponse:
        del request, exc
        return JSONResponse(status_code=503, content=ErrorEnvelope(
            code="dependency_unavailable", message="A required service is temporarily unavailable.",
            request_id=uuid4(),
        ).model_dump(mode="json"))

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request, exc
        envelope = ErrorEnvelope(
            code="request_validation_error",
            message="The request does not match the versioned API contract.",
            request_id=uuid4(),
        )
        return JSONResponse(status_code=422, content=envelope.model_dump(mode="json"))

    @application.get("/v1/contracts", tags=["contracts"])
    async def contract_catalog() -> dict[str, object]:
        """Expose stable version metadata and provisional local processing bounds."""
        return {
            "version": 1,
            "api_version": application.version,
            "generated_at": datetime.now(UTC).isoformat(),
            "processing_limits": {
                "max_raw_upload_bytes": config.max_raw_upload_bytes,
                "max_decompressed_bytes": config.max_decompressed_bytes,
                "max_candidates": config.max_candidates,
                "max_timed_repeats": config.max_timed_repeats,
                "max_query_seconds": config.max_query_seconds,
                "max_assessment_seconds": config.max_assessment_seconds,
                "max_worker_memory_mib": config.max_worker_memory_mib,
                "status": "provisional; not a measured capacity claim",
            },
        }

    return application


app = create_app()
