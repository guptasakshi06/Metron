"""Versioned manifests bind immutable data files to exact validation evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from data_optimizer.candidates.models import CandidateConfig
from data_optimizer.integrity.models import IntegrityReport, VerificationRequest
from data_optimizer.profiling.models import Digest, Model, ProfileOptions


class Artifact(Model):
    path: str = Field(pattern=r"^(p[0-9]{4}/)?part-[0-9]{4}\.(parquet|ndjson\.gz|original)$")
    sha256: Digest
    physical_bytes: int = Field(ge=0)


class ConversionManifest(Model):
    version: Literal[1] = 1
    converter: Literal["s05.1"] = "s05.1"
    evidence: Literal["local_conversion"] = "local_conversion"
    key: Digest
    input_fingerprint: Digest
    request_fingerprint: Digest
    manifest_fingerprint: Digest
    configuration: CandidateConfig
    reader: ProfileOptions
    verification_request: VerificationRequest
    artifacts: tuple[Artifact, ...] = Field(min_length=1)
    physical_bytes: int = Field(ge=0)
    file_count: int = Field(ge=1)
    partition_count: int = Field(ge=1)
    conversion_seconds: float = Field(ge=0)
    verification_seconds: float = Field(ge=0)
    cpu_seconds: float = Field(ge=0)
    peak_rss_kib: int = Field(ge=0)
    integrity: IntegrityReport
    validation_basis: Literal["ordered_concatenation_of_manifest_files"] = (
        "ordered_concatenation_of_manifest_files"
    )
    performance_status: Literal["not_measured"] = "not_measured"
    file_target_policy: Literal["decoded_size_estimate_not_physical_limit"] = (
        "decoded_size_estimate_not_physical_limit"
    )

    @model_validator(mode="after")
    def complete(self) -> ConversionManifest:
        if self.integrity.status != "passed":
            raise ValueError("unverified_outputs_cannot_be_published")
        if (
            self.file_count != len(self.artifacts)
            or self.physical_bytes != sum(a.physical_bytes for a in self.artifacts)
            or len({a.path for a in self.artifacts}) != self.file_count
        ):
            raise ValueError("inconsistent_artifact_totals")
        return self


class ConversionOutcome(Model):
    status: Literal["validated", "reused", "excluded", "failed", "cancelled"]
    reasons: tuple[str, ...] = ()
    integrity: IntegrityReport | None = None
    manifest: ConversionManifest | None = None
    artifact_prefix: str | None = None
