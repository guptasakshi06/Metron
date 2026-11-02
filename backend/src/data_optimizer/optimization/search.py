"""Finite ask/tell optimizer with explicit heuristic predictions and durable state.

No model is trained across datasets. Distance-weighted neighbors prioritize experiments;
configuration distance is an exploration proxy, never calibrated uncertainty.
"""

from __future__ import annotations

import random
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from data_optimizer.candidates.models import CandidateConfig
from data_optimizer.pricing.models import Contract
from data_optimizer.profiling.models import Digest, fingerprint


class SearchBudget(Contract):
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    max_trials: int = Field(default=8, ge=1, le=12)
    max_seconds: float = Field(default=600, gt=0, le=3600)
    enumeration_limit: int = Field(default=4, ge=1, le=12)
    exploration: float = Field(default=0.25, ge=0, le=2)


class Proposal(Contract):
    candidate_id: Digest
    configuration: CandidateConfig
    prediction: float | None
    exploration_distance: float | None
    label: Literal["enumeration", "seeded_initial", "heuristic_prediction_not_evidence"]


class SearchTrial(Contract):
    proposal: Proposal
    feasibility: Literal["feasible", "excluded", "untested"]
    objective: Decimal | None
    evidence_ids: tuple[str, ...]
    reason: str


class SearchState(Contract):
    version: Literal["s08.1"] = "s08.1"
    optimizer: Literal["finite_neighbor_exploration_v1"] = "finite_neighbor_exploration_v1"
    identity: Digest
    budget: SearchBudget
    configurations: tuple[CandidateConfig, ...] = Field(min_length=1, max_length=12)
    history: tuple[SearchTrial, ...] = ()
    pending: Proposal | None = None
    elapsed_seconds: float = Field(default=0, ge=0)
    stop_reason: Literal["running", "space_exhausted", "trial_budget", "time_budget"] = "running"
    coverage: Literal["bounded_space_not_global_optimality"] = "bounded_space_not_global_optimality"

    @model_validator(mode="after")
    def consistent(self) -> SearchState:
        keys = {c.fingerprint for c in self.configurations}
        if (
            len(keys) != len(self.configurations)
            or sum(c.baseline for c in self.configurations) != 1
        ):
            raise ValueError("unique_space_with_one_baseline_required")
        history = [t.proposal.candidate_id for t in self.history]
        if len(set(history)) != len(history) or not set(history) <= keys:
            raise ValueError("invalid_search_history")
        if self.pending and (
            self.pending.candidate_id in history or self.pending.candidate_id not in keys
        ):
            raise ValueError("invalid_pending_trial")
        for p in [t.proposal for t in self.history] + ([self.pending] if self.pending else []):
            if p.configuration.fingerprint != p.candidate_id:
                raise ValueError("proposal_configuration_mismatch")
        return self


def distance(a: CandidateConfig, b: CandidateConfig) -> float:
    fields = ("format", "codec", "compression_level", "row_group_rows", "partition_by", "sort_by")
    return float(sum(getattr(a, f) != getattr(b, f) for f in fields)) / len(fields)


def ask(state: SearchState) -> SearchState:
    if state.elapsed_seconds >= state.budget.max_seconds:
        return state.model_copy(update={"stop_reason": "time_budget"})
    if state.pending:
        return state
    if len(state.history) >= state.budget.max_trials:
        return state.model_copy(update={"stop_reason": "trial_budget"})
    seen = {t.proposal.candidate_id for t in state.history}
    remaining = [c for c in state.configurations if c.fingerprint not in seen]
    if not remaining:
        return state.model_copy(update={"stop_reason": "space_exhausted"})
    rng = random.Random(state.budget.seed)
    order = list(state.configurations)
    rng.shuffle(order)
    order.sort(key=lambda c: not c.baseline)
    remaining.sort(key=lambda c: order.index(c))
    chosen = remaining[0]
    prediction = uncertainty = None
    label = (
        "enumeration"
        if len(state.configurations) <= state.budget.enumeration_limit
        else "seeded_initial"
    )
    known = [
        t
        for t in state.history
        if t.feasibility == "feasible"
        and t.objective is not None
        and not t.proposal.configuration.baseline
    ]
    if label != "enumeration" and known and state.history:
        values = [float(t.objective) for t in known if t.objective is not None]
        scale = max(max(values) - min(values), max(abs(v) for v in values), 1.0)
        estimates = []
        for candidate in remaining:
            ds = [distance(candidate, t.proposal.configuration) for t in known]
            weights = [1 / (d + 0.05) for d in ds]
            predicted = sum(w * v for w, v in zip(weights, values, strict=True)) / sum(weights)
            exploration = min(ds)
            score = predicted - state.budget.exploration * scale * exploration
            estimates.append((score, order.index(candidate), candidate, predicted, exploration))
        _, _, chosen, prediction, uncertainty = min(estimates)
        label = "heuristic_prediction_not_evidence"
    proposal = Proposal.model_validate(
        {
            "candidate_id": chosen.fingerprint,
            "configuration": chosen,
            "prediction": prediction,
            "exploration_distance": uncertainty,
            "label": label,
        }
    )
    return state.model_copy(update={"pending": proposal, "stop_reason": "running"})


def tell(state: SearchState, trial: SearchTrial, elapsed_seconds: float) -> SearchState:
    if state.pending != trial.proposal or elapsed_seconds < 0:
        raise ValueError("tell_requires_pending_proposal_and_nonnegative_elapsed")
    return SearchState.model_validate(
        state.model_copy(
            update={
                "history": state.history + (trial,),
                "pending": None,
                "elapsed_seconds": state.elapsed_seconds + elapsed_seconds,
            }
        ).model_dump()
    )


def state_fingerprint(state: SearchState) -> str:
    return fingerprint(state.model_dump(mode="json"))
