"""Server resource ceilings and submission contracts are independent of timing."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from data_optimizer.config import Settings
from data_optimizer.jobs.models import Submission, bounded_request
from data_optimizer.optimization.assessment import AssessmentRequest


def request():
    return AssessmentRequest.model_validate_json(
        (Path(__file__).parents[2] / "examples/s08-assessment-request.json").read_bytes()
    )


def test_server_owns_identity_and_caps_resource_settings():
    tenant, assessment = uuid4(), uuid4()
    config = Settings(
        max_timed_repeats=1,
        max_raw_upload_bytes=4096,
        max_decompressed_bytes=8192,
        max_query_seconds=5,
        max_assessment_seconds=10,
        max_worker_memory_mib=512,
        max_job_output_bytes=65536,
    )
    result = bounded_request(request(), config, tenant, assessment)
    assert result.conversion.tenant_id == tenant
    assert result.conversion.assessment_id == assessment
    assert result.conversion.source.max_raw_bytes == 4096
    assert result.conversion.source.max_decoded_bytes == 8192
    assert result.conversion.source.memory_mib == 512
    assert result.conversion.limits.memory_mib == 512
    assert result.conversion.max_output_bytes == 65536
    assert result.benchmark.repeats == 1
    assert result.benchmark.limits.wall_seconds == 5
    assert result.search.max_seconds == 10


@pytest.mark.parametrize(
    "extra", [{"version": 2}, {"dataset_id": str(uuid4()), "profile_id": str(uuid4())}]
)
def test_submission_rejects_ambiguous_input_or_unknown_version(extra):
    with pytest.raises(ValidationError):
        Submission.model_validate({"project_id": str(uuid4()), "request": request(), **extra})


def test_idempotency_normalization_is_stable_for_different_client_ownership():
    original = request()
    alternate = original.model_copy(
        update={
            "conversion": original.conversion.model_copy(
                update={
                    "tenant_id": uuid4(),
                    "assessment_id": uuid4(),
                }
            )
        }
    )
    tenant = uuid4()
    assert bounded_request(original, Settings(), tenant, UUID(int=0)) == bounded_request(
        alternate, Settings(), tenant, UUID(int=0)
    )
