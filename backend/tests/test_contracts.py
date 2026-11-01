from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from data_optimizer.domain.contracts import (
    AssessmentLifecycle,
    AssessmentStatus,
    CandidateConfiguration,
    DatasetDescriptor,
    DatasetFormat,
    Decision,
    EvidenceSource,
    IntegrityStatus,
    PriceRate,
    PriceSnapshot,
    PriceUnit,
    RecommendationOutcome,
    Requirements,
    WorkloadKind,
    WorkloadSpecification,
)
from data_optimizer.domain.states import transition, transition_lifecycle


def test_unknown_optional_measurement_round_trips_as_null() -> None:
    dataset = DatasetDescriptor(
        dataset_id=uuid4(),
        format=DatasetFormat.CSV,
        source=EvidenceSource.USER_SUPPLIED,
        physical_bytes=0,
    )

    serialized = dataset.model_dump(mode="json")

    assert serialized["row_count"] is None
    assert DatasetDescriptor.model_validate_json(dataset.model_dump_json()) == dataset


def test_dataset_rejects_negative_bytes_and_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        DatasetDescriptor(
            dataset_id=uuid4(), format="csv", source="user_supplied", physical_bytes=-1
        )
    with pytest.raises(ValidationError):
        DatasetDescriptor(
            dataset_id=uuid4(),
            format="csv",
            source="user_supplied",
            physical_bytes=0,
            measured_at=datetime(2026, 1, 1),
        )
    with pytest.raises(ValidationError, match="UTC"):
        DatasetDescriptor(
            dataset_id=uuid4(),
            format="csv",
            source="user_supplied",
            physical_bytes=0,
            measured_at=datetime.fromisoformat("2026-01-01T00:00:00+05:30"),
        )


def test_workload_requires_fields_for_its_kind() -> None:
    with pytest.raises(ValidationError):
        WorkloadSpecification(
            workload_id=uuid4(),
            kind=WorkloadKind.PROJECTION,
            evidence=EvidenceSource.USER_SUPPLIED,
        )


def test_candidate_fingerprint_is_canonical_and_settings_are_coherent() -> None:
    first = CandidateConfiguration(format="parquet", codec="zstd", partition_by=("day",))
    second = CandidateConfiguration(format="parquet", codec="zstd", partition_by=("day",))

    assert first.fingerprint == second.fingerprint
    with pytest.raises(ValidationError):
        CandidateConfiguration(format="parquet")
    with pytest.raises(ValidationError):
        CandidateConfiguration(format="csv", row_group_rows=100)


def test_change_requires_measured_experiment_and_integrity() -> None:
    with pytest.raises(ValidationError):
        Decision(outcome=RecommendationOutcome.CHANGE, evidence=EvidenceSource.USER_SUPPLIED)

    decision = Decision(
        outcome="change",
        evidence="server_measured",
        candidate_id=uuid4(),
        experiment_ids=(uuid4(),),
        integrity=IntegrityStatus.PASSED,
        monthly_savings=Decimal("2.50"),
        currency="USD",
    )
    assert decision.monthly_savings == Decimal("2.50")


def test_state_transitions_reject_skips_and_terminal_mutation() -> None:
    assert transition(AssessmentStatus.DRAFT, AssessmentStatus.QUEUED) == AssessmentStatus.QUEUED
    assert (
        transition(AssessmentStatus.SCORING, AssessmentStatus.COMPLETED)
        == AssessmentStatus.COMPLETED
    )
    with pytest.raises(ValueError, match="cannot transition"):
        transition(AssessmentStatus.DRAFT, AssessmentStatus.COMPLETED)
    with pytest.raises(ValueError, match="cannot transition"):
        transition(AssessmentStatus.COMPLETED, AssessmentStatus.CANCELLED)


def test_lifecycle_transition_updates_timestamp_and_rejects_invalid_time() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    lifecycle = AssessmentLifecycle(
        assessment_id=uuid4(),
        status=AssessmentStatus.DRAFT,
        created_at=started,
        updated_at=started,
    )
    updated = transition_lifecycle(
        lifecycle,
        AssessmentStatus.NEEDS_INPUT,
        at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert updated.status == AssessmentStatus.NEEDS_INPUT
    assert updated.updated_at > lifecycle.updated_at
    with pytest.raises(ValidationError):
        transition_lifecycle(
            lifecycle, AssessmentStatus.NEEDS_INPUT, at=started.replace(tzinfo=None)
        )


def test_required_fields_units_and_currency_coherence_are_validated() -> None:
    with pytest.raises(ValidationError):
        DatasetDescriptor.model_validate(
            {"format": "csv", "source": "user_supplied", "physical_bytes": 0}
        )
    with pytest.raises(ValidationError):
        PriceRate(item="storage", unit="mystery", amount=Decimal("1"), currency="USD")
    with pytest.raises(ValidationError, match="currency"):
        Requirements(requirements_id=uuid4(), monthly_budget=Decimal("10"))
    rate = PriceRate(
        item="storage", unit=PriceUnit.GIBIBYTE_MONTH, amount=Decimal("0.02"), currency="USD"
    )
    with pytest.raises(ValidationError, match="currencies"):
        PriceSnapshot(
            snapshot_id=uuid4(),
            provider="fixture",
            region="local",
            currency="EUR",
            effective_at=datetime.now(UTC),
            source="synthetic_fixture",
            rates=(rate,),
        )


def test_change_decision_rejects_profile_only_evidence() -> None:
    with pytest.raises(ValidationError, match="measured evidence"):
        Decision(
            outcome="change",
            evidence="local_profile",
            candidate_id=uuid4(),
            experiment_ids=(uuid4(),),
            integrity="passed",
        )
