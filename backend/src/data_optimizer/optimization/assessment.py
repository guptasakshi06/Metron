"""Real local profile -> conversion -> sandbox measurements -> cost -> decision pipeline."""

from __future__ import annotations

import fcntl
import os
import tempfile
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Literal

from pydantic import Field

from data_optimizer.benchmarking.models import BenchmarkReport, BenchmarkRequest
from data_optimizer.benchmarking.service import benchmark, write_report
from data_optimizer.candidates.models import CandidateList, ConversionRequest
from data_optimizer.conversion.models import ConversionOutcome
from data_optimizer.conversion.service import convert, list_candidates, read_manifest
from data_optimizer.economics.benchmark import bind_benchmark
from data_optimizer.economics.models import CostReport, CostRequest
from data_optimizer.economics.service import calculate
from data_optimizer.optimization.search import SearchBudget, SearchState, SearchTrial, ask, tell
from data_optimizer.pricing.models import Amount, Contract
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import Digest, ProfileReport, fingerprint, server_profile
from data_optimizer.profiling.service import profile_file, read_report
from data_optimizer.recommendations.models import Decision, DecisionPolicy
from data_optimizer.recommendations.service import decide


class AssessmentRequest(Contract):
    version: Literal["s08.1"] = "s08.1"
    conversion: ConversionRequest | None = None
    benchmark: BenchmarkRequest = BenchmarkRequest()
    cost_template: CostRequest | None = None
    replays_per_month: Amount | None = None
    policy: DecisionPolicy
    search: SearchBudget = SearchBudget()


class Session(Contract):
    identity: Digest
    profile: ProfileReport
    candidates: CandidateList
    search: SearchState
    outcomes: dict[str, ConversionOutcome] = Field(default_factory=dict)
    benchmark: BenchmarkReport | None = None
    active_started_at: float | None = None


class AssessmentReport(Contract):
    version: Literal["s08.1"] = "s08.1"
    report_fingerprint: Digest
    request: AssessmentRequest
    evidence: Literal["local_assessment", "scenario_guidance"]
    profile: ProfileReport | None
    candidates: CandidateList | None
    search: SearchState | None
    benchmark: BenchmarkReport | None
    costs: dict[str, CostReport]
    decision: Decision


def checkpoint(path: Path, session: Session) -> None:
    """One local same-filesystem replacement; caller holds the session lock."""
    payload = {
        "fingerprint": fingerprint(session.model_dump(mode="json")),
        "session": session.model_dump(mode="json"),
    }
    import json

    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".checkpoint-")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_session(path: Path, identity: str) -> Session:
    import json

    if path.stat().st_size > 67_108_864:
        raise ValueError("assessment_checkpoint_byte_quota")
    payload = json.loads(path.read_bytes())
    session = Session.model_validate(payload["session"])
    if session.identity != identity or payload["fingerprint"] != fingerprint(
        session.model_dump(mode="json")
    ):
        raise ValueError("assessment_checkpoint_mismatch")
    for outcome in session.outcomes.values():
        if outcome.artifact_prefix and outcome.manifest:
            if read_manifest(Path(outcome.artifact_prefix)) != outcome.manifest:
                raise ValueError("assessment_artifact_changed")
    return session


def expired(deadline: float, cancelled: Callable[[], bool] | None = None) -> bool:
    return time.monotonic() >= deadline or bool(cancelled and cancelled())


def cost_reports(
    request: AssessmentRequest, matrix: BenchmarkReport | None
) -> dict[str, CostReport]:
    if matrix is None or request.cost_template is None:
        return {}
    return {
        m.key: calculate(
            bind_benchmark(
                request.cost_template,
                matrix,
                m.key,
                request.replays_per_month,
            )
        )
        for m in matrix.manifests
        if not m.configuration.baseline
    }


def assess(
    source: Path | None,
    root: Path,
    request: AssessmentRequest,
    *,
    metadata: Path | None = None,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[str, Session | None], None] | None = None,
    server_execution: bool = False,
) -> AssessmentReport:
    request = AssessmentRequest.model_validate(request.model_dump())
    if source is not None and metadata is not None:
        raise ValueError("choose_raw_or_metadata_input")
    profile = None
    session = None

    def notify(stage: str, current: Session | None = None) -> None:
        if progress:
            progress(stage, current)

    notify("profiling")
    if source is None:
        profile = read_report(metadata) if metadata else None
    else:
        if request.conversion is None:
            raise ValueError("raw_assessment_requires_conversion_request")
        identity = fingerprint(
            {
                "input": input_digest(source, request.conversion.source.max_raw_bytes),
                "request": request.model_dump(mode="json"),
            }
        )
        directory = root / "sessions" / identity
        if source.resolve().is_relative_to(directory.resolve()):
            raise ValueError("assessment_must_preserve_source")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (directory / "lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = directory / "checkpoint.json"
            if path.exists():
                session = load_session(path, identity)
            else:
                profile = profile_file(source, request.conversion.source, cancelled=cancelled)
                if server_execution:
                    profile = server_profile(profile)
                candidates = list_candidates(source, request.conversion, cancelled=cancelled)
                configurations = tuple(
                    c.configuration for c in candidates.candidates if c.status == "eligible"
                )
                session = Session(
                    identity=identity,
                    profile=profile,
                    candidates=candidates,
                    search=SearchState(
                        identity=identity, budget=request.search, configurations=configurations
                    ),
                )
                checkpoint(path, session)
            if server_execution and session.profile.evidence != "server_profile":
                session = session.model_copy(update={"profile": server_profile(session.profile)})
                checkpoint(path, session)
            # Charge pending interrupted work (including downtime) conservatively on resume.
            if session.active_started_at is not None:
                session = session.model_copy(
                    update={
                        "search": session.search.model_copy(
                            update={
                                "elapsed_seconds": session.search.elapsed_seconds
                                + max(0, time.time() - session.active_started_at),
                            }
                        ),
                        "active_started_at": None,
                    }
                )
                checkpoint(path, session)
            notify("benchmarking", session)
            while True:
                if cancelled and cancelled():
                    break
                search = ask(session.search)
                session = session.model_copy(update={"search": search})
                checkpoint(path, session)
                if search.stop_reason != "running" or search.pending is None:
                    break
                proposal = search.pending
                started = time.monotonic()
                deadline = started + max(0, search.budget.max_seconds - search.elapsed_seconds)
                session = session.model_copy(update={"active_started_at": time.time()})
                checkpoint(path, session)
                outcome = session.outcomes.get(proposal.candidate_id)
                if outcome is None:
                    outcome = convert(
                        source,
                        root / "artifacts",
                        request.conversion,
                        proposal.configuration,
                        cancelled=partial(expired, deadline, cancelled),
                    )
                    session = session.model_copy(
                        update={
                            "outcomes": {**session.outcomes, proposal.candidate_id: outcome},
                        }
                    )
                    checkpoint(path, session)
                matrix = session.benchmark
                if outcome.manifest is not None and request.conversion.workload.queries:
                    saved = directory / (proposal.candidate_id + "-benchmark.json")
                    if saved.exists():
                        if saved.stat().st_size > 67_108_864:
                            raise ValueError("benchmark_report_byte_quota")
                        matrix = BenchmarkReport.model_validate_json(saved.read_bytes())
                    else:
                        directories = tuple(
                            Path(o.artifact_prefix)
                            for o in session.outcomes.values()
                            if o.artifact_prefix and o.manifest
                        )
                        matrix = benchmark(
                            directories,
                            request.benchmark,
                            previous=matrix,
                            cancelled=partial(expired, deadline, cancelled),
                        )
                        write_report(saved, matrix, directories + (source,))
                    session = session.model_copy(update={"benchmark": matrix})
                    checkpoint(path, session)
                costs = cost_reports(request, matrix)
                decision = decide(matrix, costs, request.policy)
                evaluation = next(
                    (
                        e
                        for e in decision.candidates
                        if outcome.manifest and e.candidate_id == outcome.manifest.key
                    ),
                    None,
                )
                trial = SearchTrial(
                    proposal=proposal,
                    feasibility=evaluation.feasibility if evaluation else "excluded",
                    objective=evaluation.horizon_total
                    if evaluation and evaluation.feasibility == "feasible"
                    else None,
                    evidence_ids=evaluation.evidence_ids if evaluation else (),
                    reason=outcome.status + ":" + ",".join(outcome.reasons),
                )
                session = session.model_copy(
                    update={
                        "search": tell(search, trial, time.monotonic() - started),
                        "active_started_at": None,
                    }
                )
                checkpoint(path, session)
                notify("benchmarking", session)
            # Detect any source changes between stages, not only inside individual workers.
            if session.candidates.input_fingerprint != input_digest(
                source, request.conversion.source.max_raw_bytes
            ):
                raise ValueError("assessment_source_changed")
            profile = session.profile
    notify("scoring", session)
    matrix = session.benchmark if session else None
    costs = cost_reports(request, matrix)
    report = AssessmentReport(
        report_fingerprint="0" * 64,
        request=request,
        evidence="local_assessment" if source else "scenario_guidance",
        profile=profile,
        candidates=session.candidates if session else None,
        search=session.search if session else None,
        benchmark=matrix,
        costs=costs,
        decision=decide(matrix, costs, request.policy),
    )
    return report.model_copy(
        update={
            "report_fingerprint": fingerprint(
                report.model_dump(mode="json", exclude={"report_fingerprint"})
            )
        }
    )
