"""API submission and server-owned resource policy."""

from uuid import UUID

from pydantic import model_validator

from data_optimizer.config import Settings
from data_optimizer.optimization.assessment import AssessmentRequest
from data_optimizer.profiling.models import Model


class Submission(Model):
    version: int = 1
    project_id: UUID
    dataset_id: UUID | None = None
    profile_id: UUID | None = None
    request: AssessmentRequest

    @model_validator(mode="after")
    def input_choice(self) -> "Submission":
        if self.version != 1 or (self.dataset_id and self.profile_id):
            raise ValueError("choose_one_input")
        if self.dataset_id and not self.request.conversion:
            raise ValueError("dataset_requires_conversion")
        return self


def bounded_request(
    request: AssessmentRequest, config: Settings, tenant: UUID, assessment: UUID
) -> AssessmentRequest:
    """Clamp resource ceilings and replace caller-supplied ownership identifiers."""
    data = request.model_dump(mode="json")
    data["search"]["max_seconds"] = min(request.search.max_seconds, config.max_assessment_seconds)
    bench = data["benchmark"]
    bench["repeats"] = min(bench["repeats"], config.max_timed_repeats)
    bench["assessment_seconds"] = min(bench["assessment_seconds"], config.max_assessment_seconds)
    bench["limits"]["memory_mib"] = min(bench["limits"]["memory_mib"], config.max_worker_memory_mib)
    bench["limits"]["wall_seconds"] = min(bench["limits"]["wall_seconds"], config.max_query_seconds)
    if data["conversion"]:
        conv = data["conversion"]
        conv.update(tenant_id=str(tenant), assessment_id=str(assessment))
        conv["max_candidates"] = min(conv["max_candidates"], config.max_candidates)
        conv["max_output_bytes"] = min(conv["max_output_bytes"], config.max_job_output_bytes)
        source = conv["source"]
        source["max_raw_bytes"] = min(source["max_raw_bytes"], config.max_raw_upload_bytes)
        source["max_decoded_bytes"] = min(
            source["max_decoded_bytes"], config.max_decompressed_bytes
        )
        source["memory_mib"] = min(source["memory_mib"], config.max_worker_memory_mib)
        source["timeout_seconds"] = min(source["timeout_seconds"], config.max_query_seconds)
        limits = conv["limits"]
        limits["memory_mib"] = min(limits["memory_mib"], config.max_worker_memory_mib)
        limits["timeout_seconds"] = min(limits["timeout_seconds"], config.max_query_seconds)
    return AssessmentRequest.model_validate(data)
