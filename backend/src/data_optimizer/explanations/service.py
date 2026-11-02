"""Only deterministic statements justified by immutable result references can render."""

from typing import Literal

from pydantic import Field

from data_optimizer.optimization.assessment import AssessmentReport
from data_optimizer.profiling.models import Model

Reason = Literal["selected", "excluded", "untested", "baseline", "scope"]
TEXT: dict[Reason, str] = {
    "selected": (
        "This is the selected tested configuration. Review its calculated costs and coverage below."
    ),
    "excluded": "This configuration was excluded by the recorded requirements or integrity checks.",
    "untested": (
        "This configuration has requirements that remain untested; "
        "it is not a verified feasible choice."
    ),
    "baseline": "The original representation remains available for comparison.",
    "scope": (
        "Evidence is limited to the recorded inputs and coverage. "
        "Cloud concurrency, production savings and tail latency remain unvalidated."
    ),
}


class Card(Model):
    candidate_id: str | None
    evidence_id: str
    reason: Reason


class ExplanationSelection(Model):
    cards: tuple[Card, ...] = Field(min_length=1, max_length=24)


def allowed_cards(report: AssessmentReport) -> ExplanationSelection:
    cards = [Card(candidate_id=None, evidence_id=report.report_fingerprint, reason="scope")]
    decision = report.decision
    for candidate in decision.candidates:
        reasons: list[Reason] = []
        if candidate.candidate_id == decision.baseline_candidate_id:
            reasons.append("baseline")
        if candidate.candidate_id == decision.selected_candidate_id:
            reasons.append("selected")
        if candidate.feasibility in {"excluded", "untested"}:
            reasons.append("excluded" if candidate.feasibility == "excluded" else "untested")
        for reason in reasons:
            cards.append(
                Card(
                    candidate_id=candidate.candidate_id,
                    evidence_id=candidate.evidence_ids[0]
                    if candidate.evidence_ids
                    else decision.decision_fingerprint,
                    reason=reason,
                )
            )
    return ExplanationSelection(cards=tuple(cards[:24]))


def validate_cards(value: ExplanationSelection, allowed: ExplanationSelection) -> None:
    if len(set((c.candidate_id, c.evidence_id, c.reason) for c in value.cards)) != len(
        value.cards
    ) or any(c not in allowed.cards for c in value.cards):
        raise ValueError("unsupported_evidence_reference")


def render_cards(value: ExplanationSelection) -> list[dict[str, str | None]]:
    return [{**card.model_dump(), "text": TEXT[card.reason]} for card in value.cards]
