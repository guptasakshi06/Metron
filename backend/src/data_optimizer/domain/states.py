"""Assessment lifecycle transitions, independent of recommendation outcomes."""

from datetime import UTC, datetime

from data_optimizer.domain.contracts import AssessmentLifecycle, AssessmentStatus

ALLOWED_TRANSITIONS: dict[AssessmentStatus, frozenset[AssessmentStatus]] = {
    AssessmentStatus.DRAFT: frozenset(
        {AssessmentStatus.NEEDS_INPUT, AssessmentStatus.QUEUED, AssessmentStatus.CANCELLED}
    ),
    AssessmentStatus.NEEDS_INPUT: frozenset(
        {AssessmentStatus.DRAFT, AssessmentStatus.QUEUED, AssessmentStatus.CANCELLED}
    ),
    AssessmentStatus.QUEUED: frozenset(
        {AssessmentStatus.PROFILING, AssessmentStatus.FAILED, AssessmentStatus.CANCELLED}
    ),
    AssessmentStatus.PROFILING: frozenset(
        {
            AssessmentStatus.BENCHMARKING,
            AssessmentStatus.SCORING,
            AssessmentStatus.FAILED,
            AssessmentStatus.CANCELLED,
        }
    ),
    AssessmentStatus.BENCHMARKING: frozenset(
        {AssessmentStatus.SCORING, AssessmentStatus.FAILED, AssessmentStatus.CANCELLED}
    ),
    AssessmentStatus.SCORING: frozenset(
        {AssessmentStatus.COMPLETED, AssessmentStatus.FAILED, AssessmentStatus.CANCELLED}
    ),
    AssessmentStatus.COMPLETED: frozenset(),
    AssessmentStatus.FAILED: frozenset(),
    AssessmentStatus.CANCELLED: frozenset(),
}


def transition(current: AssessmentStatus, target: AssessmentStatus) -> AssessmentStatus:
    """Return the next state, rejecting skipped or terminal-state transitions."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"assessment cannot transition from {current.value} to {target.value}")
    return target


def transition_lifecycle(
    lifecycle: AssessmentLifecycle,
    target: AssessmentStatus,
    *,
    at: datetime | None = None,
) -> AssessmentLifecycle:
    """Return an updated lifecycle after validating its allowed transition."""
    transition(lifecycle.status, target)
    timestamp = at or datetime.now(UTC)
    return AssessmentLifecycle.model_validate(
        {**lifecycle.model_dump(), "status": target, "updated_at": timestamp}
    )
