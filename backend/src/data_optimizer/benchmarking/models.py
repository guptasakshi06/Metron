"""Versioned benchmark requests, observations and explicit incomplete outcomes."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from data_optimizer.conversion.models import ConversionManifest
from data_optimizer.profiling.models import Digest, Model


class SandboxLimits(Model):
    memory_mib: int = Field(default=1024, ge=64, le=4096)
    cpus: float = Field(default=1, ge=0.1, le=2)
    cpu_seconds: int = Field(default=30, ge=1, le=300)
    wall_seconds: float = Field(default=45, ge=0.1, le=600)
    scratch_mib: int = Field(default=64, ge=1, le=512)
    output_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)
    pids: int = Field(default=64, ge=16, le=128)


class BenchmarkRequest(Model):
    version: Literal[1] = 1
    repeats: int = Field(default=3, ge=1, le=5)
    warmups: int = Field(default=0, ge=0, le=2)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    max_trials: int = Field(default=60, ge=1, le=60)
    assessment_seconds: float = Field(default=600, ge=0.1, le=3600)
    max_input_bytes: int = Field(default=536_870_912, ge=1, le=1_073_741_824)
    limits: SandboxLimits = SandboxLimits()


class QueryTiming(Model):
    query_id: str
    seconds: float = Field(ge=0)
    result_rows: int = Field(ge=0)
    result_fingerprint: Digest


class Observation(Model):
    load_seconds: float = Field(ge=0)
    workload_seconds: float = Field(ge=0)
    cpu_seconds: float = Field(ge=0)
    peak_rss_kib: int = Field(ge=0)
    queries: tuple[QueryTiming, ...]
    scanned_bytes: int | None = None
    scanned_bytes_reason: Literal["typed_reader_does_not_expose_physical_io"] = (
        "typed_reader_does_not_expose_physical_io"
    )
    cache: Literal["fresh_process_os_cache_uncontrolled", "warm_process_os_cache_uncontrolled"]


TrialStatus = Literal[
    "passed",
    "timeout",
    "memory_limit",
    "cpu_limit",
    "output_limit",
    "disk_limit",
    "integrity_failed",
    "cancelled",
    "budget_exhausted",
    "failed",
]


class Trial(Model):
    ordinal: int = Field(ge=0)
    repeat: int = Field(ge=0)
    candidate: Digest
    status: TrialStatus
    reason: str
    observation: Observation | None = None
    elapsed_seconds: float = Field(default=0, ge=0)
    exit_code: int | None = None
    oom_killed: bool = False

    @model_validator(mode="after")
    def usable(self) -> Trial:
        if (self.status == "passed") != (self.observation is not None):
            raise ValueError("only_passed_trials_have_usable_observations")
        return self


class Summary(Model):
    candidate: Digest
    query_id: str
    observations: int
    median_seconds: float | None
    minimum_seconds: float | None
    maximum_seconds: float | None
    stdev_seconds: float | None
    p95_seconds: float | None = None
    tail_status: Literal["unvalidated_requires_100_observations"] = (
        "unvalidated_requires_100_observations"
    )


class BenchmarkReport(Model):
    version: Literal[1] = 1
    benchmark_version: Literal["s06.1"] = "s06.1"
    evidence: Literal["local_typed_load_and_in_memory_queries"] = (
        "local_typed_load_and_in_memory_queries"
    )
    report_fingerprint: Digest
    request_fingerprint: Digest
    workload_fingerprint: Digest
    environment_fingerprint: Digest
    request: BenchmarkRequest
    environment: dict[str, str]
    # Full immutable manifests include request/configuration/input and integrity lineage.
    manifests: tuple[ConversionManifest, ...]
    trials: tuple[Trial, ...]
    summaries: tuple[Summary, ...]
    stop_reason: Literal["completed", "cancelled", "budget_exhausted"]
