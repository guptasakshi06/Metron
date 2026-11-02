"""S07 price contracts, explicit billing units and content-addressed snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from data_optimizer.profiling.models import Model, fingerprint

Amount = Annotated[Decimal, Field(ge=0, max_digits=30, decimal_places=12)]
Fraction = Annotated[Decimal, Field(ge=0, le=1, max_digits=13, decimal_places=12)]
Unit = Literal["GB_month", "GiB_month", "compute_hour", "request", "GB", "GiB", "hour", "month"]
StorageUnit = Literal["GB_month", "GiB_month"]


class Contract(Model):
    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, validate_default=True
    )


class Source(Contract):
    kind: Literal["synthetic", "assumption", "user_supplied", "local_measurement"]
    reference: str = Field(min_length=1, max_length=1000)
    note: str = Field(min_length=1, max_length=2000)


class Rate(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    unit: Unit
    amount: Amount
    per_quantity: Amount = Field(default=Decimal(1), gt=0)
    source: Source
    minimum_object_bytes: int = Field(default=0, ge=0, le=2**63 - 1)
    minimum_duration_days: int = Field(default=0, ge=0, le=36500)
    discount_fraction: Fraction = Decimal(0)
    discount_assumption: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def storage_minima(self) -> Rate:
        if self.unit not in {"GB_month", "GiB_month"} and (
            self.minimum_object_bytes or self.minimum_duration_days
        ):
            raise ValueError("storage_minima_require_storage_unit")
        return self


class PriceSnapshot(Contract):
    version: Literal["s07.1"] = "s07.1"
    provider: str = Field(min_length=1, max_length=120)
    region: str = Field(min_length=1, max_length=120)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    effective_at: datetime
    retrieved_at: datetime
    source: Literal["synthetic", "user_supplied"]
    source_references: tuple[str, ...] = Field(min_length=1, max_length=64)
    assumptions: tuple[str, ...] = Field(min_length=1, max_length=64)
    rates: tuple[Rate, ...] = Field(min_length=1, max_length=64)

    @field_validator("effective_at", "retrieved_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("price_timestamps_require_utc")
        return value

    @model_validator(mode="after")
    def unique_rates(self) -> PriceSnapshot:
        if len({r.id for r in self.rates}) != len(self.rates):
            raise ValueError("duplicate_rate_id")
        if self.source == "synthetic" and any(r.source.kind != "synthetic" for r in self.rates):
            raise ValueError("synthetic_snapshot_requires_synthetic_rates")
        if self.source == "user_supplied" and any(r.source.kind == "synthetic" for r in self.rates):
            raise ValueError("synthetic_rates_cannot_be_relabelled")
        return self

    @property
    def snapshot_id(self) -> str:
        return fingerprint(self.model_dump(mode="json"))
