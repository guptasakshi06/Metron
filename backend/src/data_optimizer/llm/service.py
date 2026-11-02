"""Durable pessimistic usage reservations, including failed and concurrent calls."""

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from data_optimizer.config import Settings
from data_optimizer.llm.provider import (
    OpenAIResponses,
    ProviderFailure,
    StructuredProvider,
    provider_payload,
)


def assist(
    config: Settings,
    tenant: str,
    project: UUID,
    scope: UUID,
    summary: dict[str, Any],
    model: type[BaseModel],
    validate: Callable[[Any], None],
    provider: StructuredProvider | None = None,
) -> tuple[BaseModel | None, str]:
    if config.llm_provider == "disabled":
        return None, "disabled"
    if config.llm_api_key is None:
        return None, "missing_key"
    payload = provider_payload(config, summary, model)
    size = len(json.dumps(payload, ensure_ascii=False).encode())
    if size > config.llm_max_input_bytes:
        return None, "input_budget_exhausted"
    # UTF-8 byte count conservatively bounds input tokens, plus reserved output.
    reservation = size + config.llm_max_output_tokens
    with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
        db.execute(
            "SELECT id FROM projects WHERE tenant_id=%s AND id=%s FOR UPDATE", (tenant, project)
        )
        row = db.execute(
            "SELECT count(*) AS calls,COALESCE(sum(reserved_tokens),0) AS tokens "
            "FROM assistance_usage WHERE tenant_id=%s AND scope_id=%s",
            (tenant, scope),
        ).fetchone()
        assert row
        if (
            row["calls"] >= config.llm_calls_per_scope
            or row["tokens"] + reservation > config.llm_token_budget_per_scope
        ):
            return None, "budget_exhausted"
        db.execute(
            "INSERT INTO assistance_usage (id,tenant_id,project_id,scope_id,reserved_tokens) "
            "VALUES (%s,%s,%s,%s,%s)",
            (uuid4(), tenant, project, scope, reservation),
        )
    try:
        value = model.model_validate((provider or OpenAIResponses(config)).generate(payload))
        validate(value)
        return value, "completed"
    except ProviderFailure as error:
        return None, str(error)
    except (ValueError, TypeError, KeyError):
        return None, "invalid_output"
