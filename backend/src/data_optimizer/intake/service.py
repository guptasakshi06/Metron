"""Conservative explicit-unit extraction and consequential missing questions."""

import re

from data_optimizer.intake.models import IntakeSelection, ProposedField, Question
from data_optimizer.optimization.assessment import AssessmentRequest
from data_optimizer.profiling.models import fingerprint

QUESTIONS: dict[Question, str] = {
    "retention": "How many days must the analytical data remain available?",
    "freshness": "What maximum data freshness delay is required? This engine does not validate it.",
    "workload": "Which representative analytical queries should be tested?",
    "costs": "Which usage rates, migration effort and price assumptions should be modeled?",
}
PATTERNS = {
    "retention_days": r"\b(?:retention\s*[:=]?|retain(?:\s+data)?\s+for)\s*(\d{1,5})\s*days?\b",
    "freshness_seconds": r"\bfreshness\s*[:=]?\s*(\d{1,5})\s*seconds?\b",
}


def extract(description: str, request: AssessmentRequest) -> IntakeSelection:
    fields = []
    for name, pattern in PATTERNS.items():
        matches = list(re.finditer(pattern, description, re.IGNORECASE))
        # Conflicting mentions and values outside the supported contract require manual editing.
        if len(matches) == 1:
            match = matches[0]
            value = int(match[1])
            if (name != "retention_days" or value >= 1) and value <= 36500:
                fields.append(
                    ProposedField.model_validate(
                        {
                            "field": name,
                            "value": value,
                            "source_quote": match[0],
                        }
                    )
                )
    proposed = {f.field for f in fields}
    questions: list[Question] = []
    if request.policy.retention_days is None and "retention_days" not in proposed:
        questions.append("retention")
    if request.policy.freshness_seconds is None and "freshness_seconds" not in proposed:
        questions.append("freshness")
    if not request.conversion or not request.conversion.workload.queries:
        questions.append("workload")
    if request.cost_template is None or request.replays_per_month is None:
        questions.append("costs")
    return IntakeSelection(fields=tuple(fields), questions=tuple(questions))


def validate_selection(value: IntakeSelection, baseline: IntakeSelection) -> None:
    if (
        len({f.field for f in value.fields}) != len(value.fields)
        or len(set(value.questions)) != len(value.questions)
        or any(f not in baseline.fields for f in value.fields)
        or any(q not in baseline.questions for q in value.questions)
    ):
        raise ValueError("unsupported_requirement_or_question")


def requirements_fingerprint(request: AssessmentRequest) -> str:
    return fingerprint(
        {
            "policy": request.policy.model_dump(mode="json"),
            "workload": request.conversion.workload.model_dump(mode="json")
            if request.conversion
            else None,
        }
    )
