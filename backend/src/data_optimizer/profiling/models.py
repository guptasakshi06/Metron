"""Versioned, metadata-only profiling contracts. Never include example values."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Kind = Literal[
    "string",
    "integer",
    "decimal",
    "float",
    "boolean",
    "timestamp_aware",
    "timestamp_naive",
    "date",
    "binary",
    "object",
    "array",
    "null",
]


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ProfileOptions(Model):
    format: Literal["csv", "ndjson", "parquet"]
    schema_overrides: dict[
        str, Literal["string", "integer", "decimal", "timestamp", "boolean"]
    ] = {}
    csv_null_tokens: tuple[str, ...] = ()
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    sample_rows_per_stratum: int | None = Field(default=None, ge=1, le=10_000)
    time_column: str | None = None
    source_column: str | None = None
    max_strata: int = Field(default=32, ge=1, le=128)
    max_columns: int = Field(default=128, ge=1, le=512)
    cardinality_capacity: int = Field(default=1024, ge=16, le=4096)
    include_field_names: bool = False
    redacted_fields: tuple[str, ...] = ()
    max_raw_bytes: int = Field(default=268_435_456, ge=1)
    max_decoded_bytes: int = Field(default=1_073_741_824, ge=1)
    max_record_bytes: int = Field(default=1_048_576, ge=64, le=16_777_216)
    memory_mib: int = Field(default=1024, ge=128, le=4096)
    timeout_seconds: int = Field(default=60, ge=1, le=900)


class Widths(Model):
    minimum: int = Field(ge=0)
    maximum: int = Field(ge=0)
    mean: float = Field(ge=0)
    # Counts in <=16, <=64, <=256, <=1024, >1024 canonical-value byte bins.
    histogram: tuple[int, int, int, int, int]

    @model_validator(mode="after")
    def coherent(self) -> Widths:
        if any(v < 0 for v in self.histogram):
            raise ValueError("negative histogram count")
        if self.minimum > self.maximum or not self.minimum <= self.mean <= self.maximum:
            raise ValueError("inconsistent width distribution")
        return self


class Cardinality(Model):
    value: int = Field(ge=0)
    method: Literal["exact", "kmv_estimate"]
    capacity: int = Field(ge=16, le=4096)
    scope: Literal["profiled_present_nonnull_values"] = "profiled_present_nonnull_values"


class ColumnProfile(Model):
    field: str = Field(min_length=1, max_length=256)
    schema_types: tuple[Kind, ...]
    type_counts: dict[Kind, int]
    present: int = Field(ge=0)
    missing: int = Field(ge=0)
    nulls: int = Field(ge=0)
    null_density: float | None = Field(default=None, ge=0, le=1)
    cardinality: Cardinality | None
    widths: Widths | None
    temporal_span_seconds: float | None = Field(default=None, ge=0)
    temporal_scope: Literal["aware_utc", "naive_wall_clock"] | None = None
    sensitive: bool = False

    @model_validator(mode="after")
    def consistent(self) -> ColumnProfile:
        if any(v < 0 for v in self.type_counts.values()):
            raise ValueError("negative type count")
        if not set(self.type_counts).issubset(self.schema_types):
            raise ValueError("unrecognized observed type")
        if self.cardinality and self.cardinality.value > self.present - self.nulls:
            raise ValueError("cardinality exceeds nonnull population")
        if sum(self.type_counts.values()) != self.present or self.nulls > self.present:
            raise ValueError("inconsistent column counts")
        if self.nulls != self.type_counts.get("null", 0):
            raise ValueError("inconsistent null counts")
        expected = self.nulls / self.present if self.present else None
        if self.null_density != expected:
            raise ValueError("inconsistent null density")
        if self.sensitive and any(
            x is not None
            for x in (
                self.cardinality,
                self.widths,
                self.temporal_span_seconds,
                self.temporal_scope,
            )
        ):
            raise ValueError("sensitive statistics must be redacted")
        return self


class Coverage(Model):
    stratum: str = Field(pattern=r"^stratum_[0-9]+$")
    rows: int = Field(ge=0)
    profiled_rows: int = Field(ge=0)


class ProfileReport(Model):
    version: Literal[1] = 1
    profiler_version: Literal["s03.1"] = "s03.1"
    evidence: Literal["local_profile"] = "local_profile"
    raw_data_inspected_by_server: Literal[False] = False
    input_fingerprint: Digest
    schema_fingerprint: Digest
    settings_fingerprint: Digest
    profile_fingerprint: Digest
    engine_versions: dict[Literal["python", "pyarrow"], str]
    format: Literal["csv", "ndjson", "parquet"]
    physical_bytes: int = Field(ge=0)
    decoded_bytes: int = Field(ge=0)
    file_count: Literal[1] = 1
    file_sizes: Widths
    row_count: int = Field(ge=1)
    profiled_rows: int = Field(ge=1)
    sample_fraction: float = Field(gt=0, le=1)
    seed: int = Field(ge=0, le=2**32 - 1)
    sampling: Literal["full_scan", "seeded_bottom_k_per_stratum"]
    strata_by: tuple[Literal["time_day", "source"], ...] = ()
    coverage: tuple[Coverage, ...] = Field(max_length=128)
    columns: tuple[ColumnProfile, ...] = Field(max_length=512)
    row_widths: Widths
    field_names_redacted: bool
    warnings: tuple[
        Literal[
            "csv_text_requires_explicit_overrides",
            "nested_values_are_opaque",
            "mixed_types_require_schema_review",
            "sample_statistics_not_population_estimates",
            "metadata_may_be_sensitive_review_before_upload",
            "sensitive_statistics_redacted",
            "timestamps_have_mixed_awareness",
        ],
        ...,
    ]

    @model_validator(mode="after")
    def coherent(self) -> ProfileReport:
        if set(self.engine_versions) != {"python", "pyarrow"} or any(
            len(v) > 64 for v in self.engine_versions.values()
        ):
            raise ValueError("missing or invalid engine versions")
        if len({c.stratum for c in self.coverage}) != len(self.coverage):
            raise ValueError("duplicate strata")
        if (
            self.file_sizes.minimum != self.physical_bytes
            or self.file_sizes.maximum != self.physical_bytes
            or self.file_sizes.mean != self.physical_bytes
            or sum(self.file_sizes.histogram) != 1
        ):
            raise ValueError("incorrect file statistics")
        if self.profiled_rows > self.row_count:
            raise ValueError("sample exceeds population")
        if self.sample_fraction != self.profiled_rows / self.row_count:
            raise ValueError("incorrect sample fraction")
        if sum(c.rows for c in self.coverage) != self.row_count:
            raise ValueError("incorrect coverage population")
        if sum(c.profiled_rows for c in self.coverage) != self.profiled_rows:
            raise ValueError("incorrect sample coverage")
        if any(c.profiled_rows > c.rows for c in self.coverage):
            raise ValueError("incorrect stratum sample")
        if self.sampling == "full_scan" and self.profiled_rows != self.row_count:
            raise ValueError("incomplete full scan")
        if len({c.field for c in self.columns}) != len(self.columns):
            raise ValueError("duplicate columns")
        if self.field_names_redacted and any(
            c.field != f"column_{i + 1}" for i, c in enumerate(self.columns)
        ):
            raise ValueError("unredacted field name")
        for c in self.columns:
            if c.present + c.missing != self.profiled_rows:
                raise ValueError("incorrect column population")
            if c.widths and sum(c.widths.histogram) != c.present:
                raise ValueError("incorrect width population")
        if sum(self.row_widths.histogram) != self.profiled_rows:
            raise ValueError("incorrect row width population")
        return self


def report_digest(report: ProfileReport) -> str:
    return fingerprint(report.model_dump(mode="json", exclude={"profile_fingerprint"}))


def validate_report(data: bytes) -> ProfileReport:
    report = ProfileReport.model_validate_json(data)
    if report_digest(report) != report.profile_fingerprint:
        raise ValueError("profile fingerprint mismatch")
    return report
