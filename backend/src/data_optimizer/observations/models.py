"""Append-only adoption and observation input contracts."""

from datetime import UTC, datetime
from decimal import Context, Decimal, localcontext
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from data_optimizer.economics.models import ByteCount, RecurringComponent
from data_optimizer.pricing.models import Amount, Contract, Fraction
from data_optimizer.profiling.models import Digest


class PlanInput(Contract):
    expected_version: int = Field(ge=0)
    state: Literal["proposed", "planned", "deployed", "reverted"] = "proposed"
    reference_logical_bytes: ByteCount = Field(gt=0)
    deployed_at: datetime | None = None
    reverted_at: datetime | None = None
    actual_migration_cost: Amount | None = None
    source: str = Field(min_length=1, max_length=1000)
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("deployed_at", "reverted_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value and (value.utcoffset() != UTC.utcoffset(value) or value > datetime.now(UTC)):
            raise ValueError("past_utc_timestamp_required")
        return value

    @model_validator(mode="after")
    def dates(self) -> "PlanInput":
        if (self.state in {"deployed", "reverted"}) != (self.deployed_at is not None):
            raise ValueError("deployment_date_required_only_after_deployment")
        if (self.state == "reverted") != (self.reverted_at is not None):
            raise ValueError("revert_date_required_only_when_reverted")
        if self.reverted_at and self.deployed_at and self.reverted_at < self.deployed_at:
            raise ValueError("revert_precedes_deployment")
        return self


class ObservationInput(Contract):
    observation_id: UUID | None = None
    expected_version: int = Field(default=0, ge=0)
    period_start: datetime
    period_end: datetime
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    schema_fingerprint: Digest | None = None
    input_fingerprint: Digest | None = None
    retained_bytes: ByteCount | None = None
    logical_volume_bytes: ByteCount | None = None
    workload_replays: Amount | None = None
    # Exact IDs from the original workload; fractions must sum to one.
    query_mix: dict[str, Fraction] = Field(default_factory=dict, max_length=32)
    # Period totals, in the units recorded on each original non-storage charge.
    access_quantities: dict[RecurringComponent, Amount | None] = Field(
        default_factory=dict, max_length=11
    )
    itemized_costs: dict[RecurringComponent, Amount | None] = Field(
        default_factory=dict, max_length=11
    )
    coverage: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=1000)
    note: str = Field(min_length=1, max_length=2000)
    excluded: bool = False

    @field_validator("period_start", "period_end")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != UTC.utcoffset(value) or value > datetime.now(UTC):
            raise ValueError("past_utc_timestamp_required")
        return value

    @model_validator(mode="after")
    def valid_period(self) -> "ObservationInput":
        seconds = (self.period_end - self.period_start).total_seconds()
        if not 0 < seconds <= 366 * 86400:
            raise ValueError("period_must_be_positive_and_at_most_366_days")
        with localcontext(Context(prec=80)):
            if self.query_mix and abs(sum(self.query_mix.values(), Decimal(0)) - 1) > Decimal(
                "1e-10"
            ):
                raise ValueError("query_mix_fractions_must_sum_to_one")
        if (self.observation_id is None) != (self.expected_version == 0):
            raise ValueError("new_observation_or_expected_revision_required")
        return self
