"""Deterministic search budgets, adaptive response and local checkpoint recovery."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from data_optimizer.candidates.generator import context
from data_optimizer.candidates.models import CandidateConfig
from data_optimizer.optimization.search import (
    Proposal,
    SearchBudget,
    SearchState,
    SearchTrial,
    ask,
    tell,
)


def space() -> tuple[CandidateConfig, ...]:
    return (
        CandidateConfig(baseline=True, format="ndjson", codec="original", context=context()),
        CandidateConfig(format="ndjson", codec="gzip", compression_level=1, context=context()),
        CandidateConfig(format="ndjson", codec="gzip", compression_level=6, context=context()),
        CandidateConfig(format="parquet", codec="zstd", compression_level=3, context=context()),
        CandidateConfig(format="parquet", codec="zstd", compression_level=6, context=context()),
        CandidateConfig(format="parquet", codec="snappy", context=context()),
    )


def state(**budget: object) -> SearchState:
    return SearchState(
        identity="a" * 64, configurations=space(), budget=SearchBudget.model_validate(budget)
    )


def trial(proposal: Proposal, value: int = 100) -> SearchTrial:
    return SearchTrial(
        proposal=proposal,
        feasibility="feasible",
        objective=Decimal(value),
        evidence_ids=("synthetic-unit-test",),
        reason="test_only",
    )


def test_ask_tell_roundtrip_seed_baseline_and_no_duplicates() -> None:
    first = state()
    chosen = []
    while True:
        first = ask(first)
        if first.stop_reason != "running":
            break
        assert first.pending
        if not chosen:
            assert first.pending.configuration.baseline
        chosen.append(first.pending.candidate_id)
        first = tell(first, trial(first.pending), 1)
        first = SearchState.model_validate_json(first.model_dump_json())
    assert len(chosen) == len(set(chosen)) == 6
    assert first.elapsed_seconds == 6
    assert first.stop_reason == "space_exhausted"
    assert ask(state()).pending == ask(state()).pending


def test_adaptive_choice_responds_to_measurements() -> None:
    initial = state(exploration=0)
    configs = initial.configurations

    def learned(a: int, b: int) -> SearchState:
        histories = []
        for config, value in ((configs[0], 100), (configs[1], a), (configs[3], b)):
            proposal = Proposal(
                candidate_id=config.fingerprint,
                configuration=config,
                prediction=None,
                exploration_distance=None,
                label="seeded_initial",
            )
            histories.append(trial(proposal, value))
        return initial.model_copy(update={"history": tuple(histories)})

    gzip = ask(learned(1, 1000)).pending
    parquet = ask(learned(1000, 1)).pending
    assert gzip and parquet
    assert gzip.configuration.codec == "gzip"
    assert parquet.configuration.codec == "zstd"
    assert gzip.label == "heuristic_prediction_not_evidence"
    assert gzip.prediction is not None and gzip.exploration_distance is not None


def test_tiny_enumeration_independent_of_noisy_objectives() -> None:
    def selected(value: int) -> list[str]:
        current = state(enumeration_limit=12)
        keys = []
        for _ in range(6):
            current = ask(current)
            assert current.pending and current.pending.label == "enumeration"
            keys.append(current.pending.candidate_id)
            current = tell(current, trial(current.pending, value), 0)
        return keys

    assert selected(1) == selected(100000)


def test_time_and_trial_budgets_without_sleep() -> None:
    current = ask(state(max_trials=1))
    assert current.pending
    current = tell(current, trial(current.pending), 0)
    assert ask(current).stop_reason == "trial_budget"
    assert len(current.history) == 1
    limited = state(max_seconds=3).model_copy(update={"elapsed_seconds": 3})
    assert ask(limited).stop_reason == "time_budget"
    assert ask(limited).pending is None


def test_pending_resume_and_invalid_tell() -> None:
    current = ask(state())
    assert current.pending
    assert (
        ask(SearchState.model_validate_json(current.model_dump_json())).pending == current.pending
    )
    with pytest.raises(ValueError):
        tell(current, trial(current.pending), -1)
    finished = tell(current, trial(current.pending), 1)
    with pytest.raises(ValueError):
        tell(finished, trial(current.pending), 1)


@pytest.mark.parametrize("budget", [{"max_trials": 0}, {"max_seconds": 0}, {"seed": -1}])
def test_invalid_budgets(budget: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        state(**budget)


def test_invalid_space_or_history() -> None:
    with pytest.raises(ValidationError):
        SearchState(identity="a" * 64, budget=SearchBudget(), configurations=space()[1:])
    pending = ask(state())
    assert pending.pending
    with pytest.raises(ValidationError):
        SearchState.model_validate(
            pending.model_copy(
                update={
                    "history": (trial(pending.pending), trial(pending.pending)),
                    "pending": None,
                }
            ).model_dump()
        )


def test_checkpoint_integrity(tmp_path: Path) -> None:
    from data_optimizer.optimization.assessment import load_session

    path = tmp_path / "checkpoint.json"
    path.write_text('{"session": {}}')
    with pytest.raises(ValueError):
        load_session(path, "a" * 64)
