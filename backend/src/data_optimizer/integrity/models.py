"""Persistable evidence contains fingerprints and check reasons, never row values."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from data_optimizer.profiling.models import Digest, Kind, Model, ProfileOptions
from data_optimizer.workloads.models import Tolerance, Workload


class IntegrityOptions(Model):
    max_rows: int = Field(default=1_000_000, ge=1, le=10_000_000)
    max_spill_bytes: int = Field(default=268_435_456, ge=32768, le=4_294_967_296)
    max_result_rows: int = Field(default=10_000, ge=1, le=100_000)
    query_memory_mib: int = Field(default=128, ge=32, le=1024)
    timeout_seconds: int = Field(default=60, ge=1, le=900)
    memory_mib: int = Field(default=2048, ge=256, le=4096)
    order_required: bool = False
    original_bytes_required: bool = False


class VerificationRequest(Model):
    baseline: ProfileOptions
    candidate: ProfileOptions
    limits: IntegrityOptions = IntegrityOptions()
    workload: Workload = Workload()


class ColumnBaseline(Model):
    types: tuple[Kind, ...]
    type_counts: dict[Kind, int]
    missing: int
    nulls: int
    decimal_scales: tuple[int, ...] = ()
    decimal_integer_digits: int = 0
    integer_out_of_range: bool = False


class Baseline(Model):
    input_fingerprint: Digest
    settings_fingerprint: Digest
    row_count: int
    columns: dict[str, ColumnBaseline]
    declared_schema_fingerprint: Digest | None = None
    content_fingerprint: Digest
    ordered_fingerprint: Digest


class Check(Model):
    name: str
    status: Literal["passed", "failed", "not_checked"]
    reason: str


class Capability(Model):
    supported: bool
    reasons: tuple[str, ...] = ()


class QueryEvidence(Model):
    query_id: str
    status: Literal["passed", "failed", "not_checked"]
    reason: str
    tolerance: Tolerance = Tolerance()
    ordered: bool = False
    baseline_rows: int | None = None
    candidate_rows: int | None = None
    baseline_fingerprint: Digest | None = None
    candidate_fingerprint: Digest | None = None


class IntegrityReport(Model):
    version: Literal[1] = 1
    verifier_version: Literal["s04.1"] = "s04.1"
    evidence: Literal["local_integrity"] = "local_integrity"
    performance_status: Literal["not_measured"] = "not_measured"
    workload_status: Literal["passed", "failed", "not_checked"]
    workload_reason: str
    status: Literal["passed", "failed", "not_checked"]
    report_fingerprint: Digest
    request_fingerprint: Digest
    workload_fingerprint: Digest
    engine_versions: dict[str, str]
    baseline: Baseline | None = None
    candidate: Baseline | None = None
    checks: tuple[Check, ...]
    queries: tuple[QueryEvidence, ...] = ()
    capabilities: dict[str, Capability] = {}

    @model_validator(mode="after")
    def honest_status(self) -> IntegrityReport:
        if self.workload_status == "passed" and (
            not self.queries or any(q.status != "passed" for q in self.queries)
        ):
            raise ValueError("workload pass requires complete query evidence")
        if self.status == "passed":
            if self.baseline is None or self.candidate is None:
                raise ValueError("passed integrity requires complete baselines")
            required = {
                "row_count",
                "logical_schema",
                "null_missing",
                "decimal_precision",
                "canonical_content_and_multiplicity",
            }
            if not required.issubset({c.name for c in self.checks}) or any(
                c.status != "passed" for c in self.checks
            ):
                raise ValueError("passed integrity requires every content check")
            if any(q.status != "passed" for q in self.queries):
                raise ValueError("incomplete workload cannot pass integrity")
        return self
