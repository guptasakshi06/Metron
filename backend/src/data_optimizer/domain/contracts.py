"""Strict versioned contracts used by the API, CLI and later workers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContractVersion = Literal[1]
NonNegativeBytes = Annotated[int, Field(ge=0)]
PositiveSeconds = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=4)]
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    version: ContractVersion = 1


class EvidenceSource(StrEnum):
    USER_SUPPLIED = "user_supplied"
    LOCAL_PROFILE = "local_profile"
    SERVER_MEASURED = "server_measured"
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    PROJECTED = "projected"


class DatasetFormat(StrEnum):
    CSV = "csv"
    NDJSON = "ndjson"
    PARQUET = "parquet"


class WorkloadKind(StrEnum):
    PROJECTION = "projection"
    FILTER = "filter"
    TIME_RANGE = "time_range"
    GROUPED_AGGREGATE = "grouped_aggregate"
    FULL_SCAN = "full_scan"


class AssessmentStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_INPUT = "needs_input"
    QUEUED = "queued"
    PROFILING = "profiling"
    BENCHMARKING = "benchmarking"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecommendationOutcome(StrEnum):
    CHANGE = "change"
    KEEP_CURRENT = "keep_current"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class IntegrityStatus(StrEnum):
    NOT_CHECKED = "not_checked"
    PASSED = "passed"
    FAILED = "failed"


class PriceUnit(StrEnum):
    BYTE_MONTH = "byte_month"
    GIBIBYTE_MONTH = "gibibyte_month"
    REQUEST = "request"
    COMPUTE_HOUR = "compute_hour"
    TRANSFER_GIBIBYTE = "transfer_gibibyte"
    MONTH = "month"


class DatasetDescriptor(StrictContract):
    dataset_id: UUID
    format: DatasetFormat
    source: EvidenceSource
    physical_bytes: NonNegativeBytes
    decompressed_bytes: NonNegativeBytes | None = None
    row_count: NonNegativeBytes | None = None
    schema_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    measured_at: datetime | None = None

    @field_validator("measured_at")
    @classmethod
    def timestamp_must_be_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("timestamps must be UTC")
        return value


class WorkloadSpecification(StrictContract):
    workload_id: UUID
    kind: WorkloadKind
    frequency_per_day: NonNegativeBytes | None = None
    target_latency_seconds: PositiveSeconds | None = None
    freshness_seconds: NonNegativeBytes | None = None
    selected_columns: tuple[str, ...] = ()
    predicate_columns: tuple[str, ...] = ()
    group_by_columns: tuple[str, ...] = ()
    evidence: EvidenceSource

    @model_validator(mode="after")
    def kind_parameters_are_coherent(self) -> WorkloadSpecification:
        if self.kind == WorkloadKind.PROJECTION and not self.selected_columns:
            raise ValueError("projection workloads require at least one selected column")
        if self.kind == WorkloadKind.GROUPED_AGGREGATE and not self.group_by_columns:
            raise ValueError("grouped aggregates require at least one group-by column")
        if self.kind == WorkloadKind.TIME_RANGE and not self.predicate_columns:
            raise ValueError("time-range workloads require a time predicate column")
        return self


class Requirements(StrictContract):
    requirements_id: UUID
    retention_days: NonNegativeBytes | None = None
    max_latency_seconds: PositiveSeconds | None = None
    min_freshness_seconds: NonNegativeBytes | None = None
    required_capabilities: tuple[str, ...] = ()
    workload_ids: tuple[UUID, ...] = ()
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    monthly_budget: Money | None = None

    @model_validator(mode="after")
    def budget_requires_currency(self) -> Requirements:
        if self.monthly_budget is not None and self.currency is None:
            raise ValueError("monthly budget requires a currency")
        return self


class Profile(StrictContract):
    profile_id: UUID
    dataset_id: UUID
    source: EvidenceSource
    sampled_bytes: NonNegativeBytes
    sampled_fraction: Annotated[Decimal, Field(ge=0, le=1, max_digits=6, decimal_places=5)]
    exact_row_count: NonNegativeBytes | None = None
    estimated_distinct_counts: dict[str, NonNegativeBytes] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("timestamps must be UTC")
        return value


class CandidateConfiguration(StrictContract):
    format: DatasetFormat
    codec: str | None = Field(default=None, min_length=1, max_length=32)
    codec_level: int | None = Field(default=None, ge=1, le=22)
    target_file_bytes: NonNegativeBytes | None = None
    row_group_rows: NonNegativeBytes | None = None
    partition_by: tuple[str, ...] = ()
    sort_by: tuple[str, ...] = ()

    @model_validator(mode="after")
    def encoding_options_match_format(self) -> CandidateConfiguration:
        if self.format == DatasetFormat.PARQUET and self.codec is None:
            raise ValueError("Parquet candidates require an explicit codec")
        if self.format != DatasetFormat.PARQUET and self.row_group_rows is not None:
            raise ValueError("row-group settings apply only to Parquet")
        if self.codec_level is not None and self.codec is None:
            raise ValueError("codec_level requires a codec")
        return self

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"version"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Candidate(StrictContract):
    candidate_id: UUID
    configuration: CandidateConfiguration
    configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    is_baseline: bool = False
    exclusion_reason: str | None = None

    @model_validator(mode="after")
    def fingerprint_matches_configuration(self) -> Candidate:
        if self.configuration_fingerprint != self.configuration.fingerprint:
            raise ValueError("configuration_fingerprint does not match canonical configuration")
        if self.is_baseline and self.exclusion_reason is not None:
            raise ValueError("baseline candidates cannot be excluded")
        return self


class ExperimentMeasurements(StrictContract):
    experiment_id: UUID
    candidate_id: UUID
    source: EvidenceSource
    repeat_count: Annotated[int, Field(ge=0, le=5)]
    input_bytes: NonNegativeBytes
    output_bytes: NonNegativeBytes | None = None
    conversion_seconds: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    query_latency_seconds: tuple[PositiveSeconds, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.NOT_CHECKED
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("timestamps must be UTC")
        return value

    @model_validator(mode="after")
    def checked_measurements_require_repeats(self) -> ExperimentMeasurements:
        if self.integrity == IntegrityStatus.PASSED and self.repeat_count == 0:
            raise ValueError("a usable experiment requires at least one repeat")
        if len(self.query_latency_seconds) > self.repeat_count:
            raise ValueError("query latency observations cannot exceed the repeat count")
        return self


class PriceRate(StrictContract):
    item: str = Field(min_length=1, max_length=120)
    unit: PriceUnit
    amount: Money
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_url: str | None = None


class PriceSnapshot(StrictContract):
    snapshot_id: UUID
    provider: str
    region: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    effective_at: datetime
    source: EvidenceSource
    rates: tuple[PriceRate, ...]

    @field_validator("effective_at")
    @classmethod
    def effective_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("timestamps must be UTC")
        return value

    @model_validator(mode="after")
    def rate_currency_matches_snapshot(self) -> PriceSnapshot:
        if any(rate.currency != self.currency for rate in self.rates):
            raise ValueError("all rate currencies must match the snapshot currency")
        return self


class Decision(StrictContract):
    outcome: RecommendationOutcome
    evidence: EvidenceSource
    candidate_id: UUID | None = None
    experiment_ids: tuple[UUID, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.NOT_CHECKED
    monthly_savings: Decimal | None = Field(default=None, max_digits=18, decimal_places=6)
    migration_cost: Money | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def result_has_sufficient_evidence(self) -> Decision:
        if self.outcome == RecommendationOutcome.CHANGE:
            if self.candidate_id is None or not self.experiment_ids:
                raise ValueError("change decisions require a candidate and measured experiment IDs")
            if self.integrity != IntegrityStatus.PASSED:
                raise ValueError("change decisions require passed integrity evidence")
            if self.evidence != EvidenceSource.SERVER_MEASURED:
                raise ValueError("change decisions require measured evidence")
        if self.outcome == RecommendationOutcome.INSUFFICIENT_EVIDENCE and not self.limitations:
            raise ValueError("insufficient-evidence decisions must explain what is missing")
        has_money = self.monthly_savings is not None or self.migration_cost is not None
        if has_money and self.currency is None:
            raise ValueError("monetary values require a currency")
        return self


class ErrorEnvelope(StrictContract):
    code: str
    message: str
    request_id: UUID


class AssessmentLifecycle(StrictContract):
    assessment_id: UUID
    status: AssessmentStatus
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def lifecycle_timestamps_are_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("timestamps must be UTC")
        return value

    @model_validator(mode="after")
    def update_not_before_creation(self) -> AssessmentLifecycle:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class ReadinessDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["up", "down"]
    detail: str | None = None


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "not_ready"]
    dependencies: dict[str, ReadinessDependency]
