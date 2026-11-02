"""Narrow versioned assistance contracts with no arbitrary generated prose."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from data_optimizer.optimization.assessment import AssessmentRequest
from data_optimizer.profiling.models import Model

FieldName = Literal["retention_days", "freshness_seconds"]
Question = Literal["retention", "freshness", "workload", "costs"]


class ProposedField(Model):
    field: FieldName
    value: int = Field(ge=0, le=36500)
    source_quote: str = Field(min_length=1, max_length=200)


class IntakeSelection(Model):
    fields: tuple[ProposedField, ...] = Field(max_length=2)
    questions: tuple[Question, ...] = Field(max_length=4)


class IntakeInput(Model):
    description: str = Field(min_length=1, max_length=4000)
    request: AssessmentRequest


class Approval(Model):
    approved_summary_fingerprint: str


class ConfirmationInput(Model):
    request: AssessmentRequest


class IntakeResult(Model):
    version: Literal["s11.1"] = "s11.1"
    id: UUID
    original_description: str
    fields: tuple[ProposedField, ...]
    questions: dict[Question, str]
    summary: dict[str, object]
    summary_fingerprint: str
    source: Literal["deterministic", "provider"]
    status: str
    assumption: str = "Proposed from your description; review and confirm before use."
