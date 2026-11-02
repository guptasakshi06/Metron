"""Portable evidence with original references and an independent export digest."""

from typing import Literal

from pydantic import Field

from data_optimizer.benchmarking.models import BenchmarkReport
from data_optimizer.candidates.models import CandidateList
from data_optimizer.economics.models import CostReport
from data_optimizer.optimization.assessment import AssessmentRequest
from data_optimizer.profiling.models import Digest, Model
from data_optimizer.recommendations.models import Decision


class Provenance(Model):
    assessment_id: str | None = None
    requirements_id: str | None = None
    raw_result_reference: str | None = None
    input_fingerprint: Digest | None = None
    submission_fingerprint: Digest | None = None
    confirmation_id: str | None = None
    confirmation_version: int | None = None
    proposal_id: str | None = None
    accepted_requirements_fingerprint: Digest | None = None
    accepted_request_fingerprint: Digest | None = None


class ProfileCoverage(Model):
    profile_fingerprint: Digest
    schema_fingerprint: Digest
    evidence: str
    physical_bytes: int
    row_count: int
    profiled_rows: int
    sample_fraction: float
    sampling: str
    engine_versions: dict[str, str]


class AssessmentBundle(Model):
    version: Literal["s12.1"] = "s12.1"
    bundle_fingerprint: Digest
    original_report_fingerprint: Digest
    original_request_fingerprint: Digest
    provenance: Provenance
    evidence: Literal["local_assessment", "scenario_guidance"]
    input_fingerprint: Digest | None
    request: AssessmentRequest
    profile: ProfileCoverage | None
    candidates: CandidateList | None
    benchmark: BenchmarkReport | None
    costs: dict[str, CostReport]
    decision: Decision
    search_stop_reason: str | None
    limitations: tuple[str, ...]
    redactions: tuple[str, ...] = Field(
        default=(
            "Business descriptions, AI summaries, source notes/references, "
            "price narrative and paths "
            "are omitted. Schema/workload parameters remain necessary and may be sensitive.",
            "Nested evidence fingerprints reference the original records "
            "before narrative redaction. "
            "The bundle fingerprint covers the exported content; it is not a signature.",
        )
    )
