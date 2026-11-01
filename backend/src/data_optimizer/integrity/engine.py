"""One complete comparison, with every pass tied to observed check evidence."""

from __future__ import annotations

import platform
import tempfile
from pathlib import Path

import duckdb
import pyarrow

from data_optimizer.integrity.baseline import capabilities, create_store, summarize
from data_optimizer.integrity.models import (
    Capability,
    Check,
    IntegrityReport,
    QueryEvidence,
    VerificationRequest,
)
from data_optimizer.profiling.models import fingerprint
from data_optimizer.readers.stream import ProfileError
from data_optimizer.workloads.runner import compare_results, execute_workload, result_fingerprint


def seal(report: IntegrityReport) -> IntegrityReport:
    return report.model_copy(
        update={
            "report_fingerprint": fingerprint(
                report.model_dump(mode="json", exclude={"report_fingerprint"})
            )
        }
    )


def verify(
    baseline_path: Path,
    candidate_path: Path,
    request: VerificationRequest,
    *,
    scratch_root: Path | None = None,
) -> IntegrityReport:
    request = VerificationRequest.model_validate(request.model_dump())
    checks: list[Check] = []
    queries: list[QueryEvidence] = []

    def check(name: str, passed: bool, failure: str) -> None:
        checks.append(
            Check(
                name=name,
                status="passed" if passed else "failed",
                reason="equivalent" if passed else failure,
            )
        )

    baseline = candidate = None
    matrix = {}
    try:
        with tempfile.TemporaryDirectory(
            prefix="data-optimizer-content-", dir=scratch_root
        ) as directory:
            db = create_store(Path(directory) / "content.sqlite", request.limits)
            try:
                baseline = summarize(baseline_path, request.baseline, request.limits, db, 1)
                candidate = summarize(candidate_path, request.candidate, request.limits, db, -1)
                matrix = capabilities(baseline, request.baseline)
                matrix["byte_changing_conversion"] = Capability(
                    supported=not request.limits.original_bytes_required,
                    reasons=("original_byte_retention_required",)
                    if request.limits.original_bytes_required
                    else (),
                )
                same_content = (
                    db.execute("SELECT 1 FROM content WHERE n<>0 LIMIT 1").fetchone() is None
                )
            finally:
                db.close()
        check("row_count", baseline.row_count == candidate.row_count, "record_count_changed")
        check(
            "logical_schema",
            {n: c.types for n, c in baseline.columns.items()}
            == {n: c.types for n, c in candidate.columns.items()},
            "field_or_logical_type_changed",
        )
        check(
            "null_missing",
            {n: (c.missing, c.nulls) for n, c in baseline.columns.items()}
            == {n: (c.missing, c.nulls) for n, c in candidate.columns.items()},
            "null_or_missing_counts_changed",
        )
        check(
            "decimal_precision",
            {n: (c.decimal_scales, c.decimal_integer_digits) for n, c in baseline.columns.items()}
            == {
                n: (c.decimal_scales, c.decimal_integer_digits)
                for n, c in candidate.columns.items()
            },
            "decimal_scale_or_precision_changed",
        )
        if baseline.declared_schema_fingerprint and candidate.declared_schema_fingerprint:
            check(
                "declared_parquet_schema",
                baseline.declared_schema_fingerprint == (candidate.declared_schema_fingerprint),
                "declared_parquet_schema_changed",
            )
        check(
            "canonical_content_and_multiplicity",
            same_content,
            "typed_content_or_duplicate_multiplicity_changed",
        )
        if request.limits.order_required:
            check(
                "record_order",
                baseline.ordered_fingerprint == candidate.ordered_fingerprint,
                "record_order_changed",
            )
        if request.limits.original_bytes_required:
            check(
                "original_bytes",
                baseline.input_fingerprint == candidate.input_fingerprint,
                "original_byte_retention_required",
            )
        if request.workload.queries:
            candidate_capability = capabilities(candidate, request.candidate)["workload"]
            if not matrix["workload"].supported or not candidate_capability.supported:
                queries.extend(
                    QueryEvidence(
                        query_id=q.id,
                        status="not_checked",
                        reason="unsupported_workload_semantics",
                        tolerance=q.tolerance,
                        ordered=bool(q.order_by),
                    )
                    for q in request.workload.queries
                )
            else:
                try:
                    left = execute_workload(
                        baseline_path, request.baseline, baseline, request.workload, request.limits
                    )
                    right = execute_workload(
                        candidate_path,
                        request.candidate,
                        candidate,
                        request.workload,
                        request.limits,
                    )
                    for query in request.workload.queries:
                        equivalent = compare_results(left[query.id], right[query.id], query)
                        queries.append(
                            QueryEvidence(
                                query_id=query.id,
                                tolerance=query.tolerance,
                                ordered=bool(query.order_by),
                                status="passed" if equivalent else "failed",
                                reason="equivalent" if equivalent else "workload_output_changed",
                                baseline_rows=len(left[query.id]),
                                candidate_rows=len(right[query.id]),
                                baseline_fingerprint=result_fingerprint(
                                    left[query.id], bool(query.order_by)
                                ),
                                candidate_fingerprint=result_fingerprint(
                                    right[query.id], bool(query.order_by)
                                ),
                            )
                        )
                except (ProfileError, ValueError, duckdb.Error) as error:
                    reason = (
                        str(error)
                        if isinstance(error, ProfileError)
                        else "invalid_or_unsupported_workload"
                    )
                    completed_ids = {q.query_id for q in queries}
                    queries.extend(
                        QueryEvidence(
                            query_id=q.id,
                            status="not_checked",
                            reason=reason,
                            tolerance=q.tolerance,
                            ordered=bool(q.order_by),
                        )
                        for q in request.workload.queries
                        if q.id not in completed_ids
                    )
    except ProfileError as error:
        checks.append(Check(name="complete_input_read", status="failed", reason=str(error)))
    failed = any(c.status == "failed" for c in checks) or any(q.status == "failed" for q in queries)
    incomplete = any(q.status == "not_checked" for q in queries)
    workload_status = (
        "failed"
        if any(q.status == "failed" for q in queries)
        else "not_checked"
        if not queries or incomplete
        else "passed"
    )
    return seal(
        IntegrityReport(
            status="failed" if failed else "not_checked" if incomplete else "passed",
            workload_status=workload_status,
            workload_reason="missing_workload"
            if not request.workload.queries
            else (
                "outputs_compared"
                if workload_status == "passed"
                else "incomplete_or_changed_outputs"
            ),
            report_fingerprint="0" * 64,
            request_fingerprint=fingerprint(request.model_dump(mode="json")),
            workload_fingerprint=fingerprint(request.workload.model_dump(mode="json")),
            engine_versions={
                "python": platform.python_version(),
                "duckdb": duckdb.__version__,
                "pyarrow": pyarrow.__version__,
                "canonical": "s04.1",
            },
            baseline=baseline,
            candidate=candidate,
            checks=tuple(checks),
            queries=tuple(queries),
            capabilities=matrix,
        )
    )
