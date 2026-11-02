"""Versioned constraints and decisions; unsupported requirements stay explicit."""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from data_optimizer.candidates.models import CandidateConfig
from data_optimizer.economics.models import ScenarioResult
from data_optimizer.pricing.models import Amount, Contract
from data_optimizer.profiling.models import Digest


class DecisionPolicy(Contract):
    scenario: str = Field(min_length=1, max_length=64)
    minimum_net_savings: Amount = Decimal("10")
    minimum_savings_fraction: Decimal = Field(default=Decimal("0.01"), ge=0, le=1)
    allowed_formats: tuple[Literal["csv", "ndjson", "parquet"], ...] | None = None
    allowed_codecs: tuple[str, ...] | None = None
    retention_days: int | None = Field(default=None, ge=1, le=36500)
    freshness_seconds: int | None = Field(default=None, ge=0)
    required_capabilities: tuple[str, ...] = ()
    maximum_migration_cost: Amount | None = None
    latency_statistic: Literal["observed_maximum"] = "observed_maximum"


class Coverage(Contract):
    requirement: str
    status: Literal["passed", "violated", "untested", "not_required"]
    reason: str
    evidence_ids: tuple[str, ...] = ()


class Evaluation(Contract):
    candidate_id: Digest
    configuration: CandidateConfig
    feasibility: Literal["feasible", "excluded", "untested"]
    coverage: tuple[Coverage, ...]
    horizon_total: Decimal | None
    workload_seconds: float | None
    observed_range_seconds: tuple[float, float] | None
    evidence_ids: tuple[str, ...]
    costs: ScenarioResult | None


class Decision(Contract):
    version: Literal["s08.1"] = "s08.1"
    decision_fingerprint: Digest
    outcome: Literal["change", "keep_current", "insufficient_evidence"]
    selected_candidate_id: Digest | None
    best_tested_candidate_id: Digest | None
    baseline_candidate_id: Digest | None
    objective: Literal["horizon_operating_plus_once_only_migration"] = (
        "horizon_operating_plus_once_only_migration"
    )
    policy: DecisionPolicy
    candidates: tuple[Evaluation, ...]
    tradeoff_candidate_ids: tuple[Digest, ...]
    reason: str
    limitations: tuple[str, ...]
    next_questions: tuple[str, ...]
    performance_scope: Literal["local_typed_load_and_in_memory_queries"] = (
        "local_typed_load_and_in_memory_queries"
    )
