"""Bounded, immutable calculation inputs and auditable output contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from data_optimizer.pricing.models import Amount, Contract, PriceSnapshot, Source, Unit
from data_optimizer.profiling.models import Digest

RecurringComponent = Literal[
    "storage",
    "query_compute",
    "transform_compute",
    "read_requests",
    "write_requests",
    "retrieval",
    "network",
    "backups",
    "replicas",
    "maintenance",
    "service",
]
MigrationComponent = Literal["conversion", "temporary_storage", "transfer", "labor", "rollback"]
Component = RecurringComponent | MigrationComponent
RECURRING: tuple[RecurringComponent, ...] = (
    "storage",
    "query_compute",
    "transform_compute",
    "read_requests",
    "write_requests",
    "retrieval",
    "network",
    "backups",
    "replicas",
    "maintenance",
    "service",
)
MIGRATION: tuple[MigrationComponent, ...] = (
    "conversion",
    "temporary_storage",
    "transfer",
    "labor",
    "rollback",
)
ByteCount = Annotated[int, Field(ge=0, le=2**63 - 1, strict=True)]


class Quantity(Contract):
    value: Amount | None
    unit: Unit
    source: Source


class Footprint(Contract):
    logical_fingerprint: Digest
    retention_days: int = Field(ge=1, le=36500)
    # Metadata files are separate objects, included in physical and minimum billing totals.
    data_file_bytes: tuple[ByteCount, ...] | None = Field(default=None, max_length=10000)
    metadata_file_bytes: tuple[ByteCount, ...] | None = Field(default=None, max_length=10000)
    primary_copies: int = Field(ge=1, le=100)
    backup_copies: int = Field(ge=0, le=100)
    replica_copies: int = Field(ge=0, le=100)
    data_source: Source
    metadata_source: Source


class Charge(Contract):
    component: Component
    rate_id: str | None = None
    # Storage usage quantities are derived from the footprint. Other quantities are explicit.
    quantity: Quantity | None = None
    basis: Literal["usage", "provisioned", "shared_fixed"] = "usage"
    shared_key: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def scoped(self) -> Charge:
        if (self.basis == "shared_fixed") != (self.shared_key is not None):
            raise ValueError("shared_fixed_requires_shared_key_only")
        if self.component in {"storage", "backups", "replicas"} and self.basis == "usage":
            if self.quantity is not None:
                raise ValueError("usage_storage_is_derived_from_footprint")
        return self


class ConfigurationCost(Contract):
    id: str = Field(min_length=1, max_length=120)
    footprint: Footprint
    recurring: tuple[Charge, ...] = Field(max_length=len(RECURRING))

    @model_validator(mode="after")
    def recurring_only(self) -> ConfigurationCost:
        if any(c.component not in RECURRING for c in self.recurring):
            raise ValueError("migration_charge_in_recurring_costs")
        if len({c.component for c in self.recurring}) != len(self.recurring):
            raise ValueError("duplicate_recurring_component")
        keys = [c.shared_key for c in self.recurring if c.shared_key is not None]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate_shared_commitment")
        return self


class MigrationCost(Contract):
    forecast: tuple[Charge, ...] = Field(max_length=len(MIGRATION))
    actual_incurred: Amount | None = None
    actual_source: Source | None = None
    # Additional scratch is distinct from the retained baseline and candidate copies.
    extra_peak_bytes: ByteCount | None = None
    peak_source: Source

    @model_validator(mode="after")
    def migration_only(self) -> MigrationCost:
        if any(c.component not in MIGRATION or c.basis != "usage" for c in self.forecast):
            raise ValueError("migration_requires_one_time_usage_charges")
        if len({c.component for c in self.forecast}) != len(self.forecast):
            raise ValueError("duplicate_migration_component")
        if (self.actual_incurred is None) != (self.actual_source is None):
            raise ValueError("actual_migration_requires_separate_source")
        if self.actual_source and self.actual_source.kind != "user_supplied":
            raise ValueError("actual_cost_is_user_supplied_not_a_forecast")
        return self


class Scenario(Contract):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    assumption: str = Field(min_length=1, max_length=2000)
    prices: PriceSnapshot
    baseline: ConfigurationCost
    candidate: ConfigurationCost
    migration: MigrationCost
    # Required before any differing provisioned commitments can count as savings.
    achievable_capacity_change: Source | None = None
    steady_monthly_usage: bool

    @model_validator(mode="after")
    def comparable(self) -> Scenario:
        b, c = self.baseline.footprint, self.candidate.footprint
        if b.logical_fingerprint != c.logical_fingerprint or b.retention_days != c.retention_days:
            raise ValueError("equivalent_logical_content_and_retention_required")
        if (b.primary_copies, b.backup_copies, b.replica_copies) != (
            c.primary_copies,
            c.backup_copies,
            c.replica_copies,
        ):
            raise ValueError("equivalent_required_copies_required")
        if self.baseline.id == self.candidate.id:
            raise ValueError("distinct_configuration_ids_required")
        return self


class CostRequest(Contract):
    version: Literal["s07.1"] = "s07.1"
    horizon_months: int = Field(ge=1, le=120)
    # Each scenario is a constant monthly average over the horizon, including growth cases.
    scenarios: tuple[Scenario, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def compatible_scenarios(self) -> CostRequest:
        if len({s.name for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("duplicate_scenario_name")
        if len({s.prices.currency for s in self.scenarios}) != 1:
            raise ValueError("scenario_ranges_require_same_currency")
        first = self.scenarios[0].baseline.footprint
        if any(
            s.baseline.footprint.logical_fingerprint != first.logical_fingerprint
            or s.baseline.footprint.retention_days != first.retention_days
            for s in self.scenarios
        ):
            raise ValueError("scenarios_require_same_comparison_boundary")
        return self


class LineItem(Contract):
    component: Component
    basis: str
    formula: str
    quantity: Decimal | None
    unit: Unit | None
    rate_id: str | None
    price_snapshot_id: Digest
    rate_amount: Decimal | None
    per_quantity: Decimal | None
    discount_fraction: Decimal | None
    amount: Decimal | None
    currency: str
    sources: tuple[Source, ...]
    missing_inputs: tuple[str, ...]


class Breakdown(Contract):
    items: tuple[LineItem, ...]
    known_subtotal: Decimal
    total: Decimal | None
    missing_inputs: tuple[str, ...]


class SpaceChange(Contract):
    baseline_physical_bytes: int | None
    candidate_physical_bytes: int | None
    physical_bytes_saved: int | None
    percent_saved: Decimal | None
    migration_peak_bytes: int | None
    missing_inputs: tuple[str, ...]


class ScenarioResult(Contract):
    name: str
    currency: str
    price_snapshot_id: Digest
    baseline: Breakdown
    candidate: Breakdown
    migration_forecast: Breakdown
    migration_actual_incurred: Decimal | None
    space: SpaceChange
    monthly_savings: Decimal | None
    monthly_savings_percent: Decimal | None
    horizon_recurring_savings: Decimal | None
    horizon_net_savings: Decimal | None
    payback_months: Decimal | None
    payback_reason: str
    missing_inputs: tuple[str, ...]


class MetricRange(Contract):
    metric: Literal["monthly_savings", "horizon_net_savings", "payback_months"]
    minimum: Decimal | None
    maximum: Decimal | None
    known_scenarios: int
    total_scenarios: int


class CostReport(Contract):
    version: Literal["s07.1"] = "s07.1"
    evidence: Literal["modeled_forecast"] = "modeled_forecast"
    report_fingerprint: Digest
    request_fingerprint: Digest
    request: CostRequest
    results: tuple[ScenarioResult, ...]
    ranges: tuple[MetricRange, ...]
    limitations: tuple[str, ...]
