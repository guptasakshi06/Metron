"""Immutable configurations and bounded local conversion requests."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from data_optimizer.integrity.models import IntegrityOptions
from data_optimizer.profiling.models import Model, ProfileOptions, fingerprint
from data_optimizer.workloads.models import Identifier, Workload


class ExecutionContext(Model):
    engine: Literal["pyarrow"] = "pyarrow"
    storage: Literal["local_filesystem"] = "local_filesystem"
    converter: Literal["s05.1"] = "s05.1"
    engine_versions: dict[str, str]


class CandidateConfig(Model):
    version: Literal[1] = 1
    baseline: bool = False
    format: Literal["csv", "ndjson", "parquet"]
    codec: str = Field(max_length=32)
    compression_level: int | None = Field(default=None, ge=-5, le=22)
    target_file_bytes: int = Field(default=67_108_864, ge=1024, le=268_435_456)
    row_group_rows: int = Field(default=65_536, ge=1, le=1_048_576)
    partition_by: tuple[Identifier, ...] = Field(default=(), max_length=1)
    sort_by: tuple[Identifier, ...] = Field(default=(), max_length=3)
    context: ExecutionContext

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class ConversionRequest(Model):
    version: Literal[1] = 1
    tenant_id: UUID
    assessment_id: UUID
    source: ProfileOptions
    workload: Workload = Workload()
    limits: IntegrityOptions = IntegrityOptions()
    max_candidates: int = Field(default=8, ge=4, le=12)
    max_partitions: int = Field(default=16, ge=1, le=64)
    max_files: int = Field(default=32, ge=1, le=128)
    min_partition_rows: int = Field(default=128, ge=1)
    max_output_bytes: int = Field(default=536_870_912, ge=1024, le=4_294_967_296)

    @model_validator(mode="after")
    def full_scan(self) -> ConversionRequest:
        if self.source.sample_rows_per_stratum is not None:
            raise ValueError("conversion_requires_full_scan")
        return self


class Candidate(Model):
    configuration: CandidateConfig
    status: Literal["eligible", "excluded"]
    reasons: tuple[str, ...] = ()


class CandidateList(Model):
    version: Literal[1] = 1
    input_fingerprint: str
    request_fingerprint: str
    candidates: tuple[Candidate, ...]
    coverage: Literal["bounded_enumeration_not_exhaustive"] = "bounded_enumeration_not_exhaustive"
