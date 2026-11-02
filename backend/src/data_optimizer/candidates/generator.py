"""Conservative candidates from measured S04 source capabilities."""

from __future__ import annotations

import platform
import zlib
from pathlib import Path

import duckdb
import pyarrow as pa

from data_optimizer.candidates.models import (
    Candidate,
    CandidateConfig,
    CandidateList,
    ConversionRequest,
    ExecutionContext,
)
from data_optimizer.integrity.models import IntegrityReport
from data_optimizer.profiling.models import fingerprint


def context() -> ExecutionContext:
    return ExecutionContext(
        engine_versions={
            "python": platform.python_version(),
            "pyarrow": pa.__version__,
            "arrow_cpp": pa.cpp_version,
            "arrow_worker_memory_pool": "system",
            "duckdb": duckdb.__version__,
            "canonical": "s04.1",
            "zlib": zlib.ZLIB_RUNTIME_VERSION,
        }
    )


def exclusion(
    config: CandidateConfig, request: ConversionRequest, evidence: IntegrityReport
) -> tuple[str, ...]:
    if config.context != context():
        return ("execution_context_mismatch",)
    if config.baseline:
        if (
            config.format != request.source.format
            or config.codec != "original"
            or config.partition_by
            or config.sort_by
            or config.compression_level is not None
        ):
            return ("invalid_baseline_configuration",)
        return ()
    reasons: list[str] = []
    if request.limits.original_bytes_required:
        reasons.append("original_byte_retention_required")
    supported = (
        config.format == "ndjson"
        and config.codec == "gzip"
        and config.compression_level in (None, 1, 6, 9)
    ) or (
        config.format == "parquet"
        and config.codec in ("snappy", "zstd")
        and (config.compression_level is None or config.codec == "zstd")
    )
    if not supported:
        reasons.append("unsupported_format_codec_or_level")
    elif config.format == "parquet" and not pa.Codec.is_available(config.codec):
        reasons.append("codec_unavailable")
    capability = evidence.capabilities.get(config.format)
    if capability is None or not capability.supported:
        reasons.extend(capability.reasons if capability else ("reader_incompatible",))
    if config.format != "parquet" and (config.partition_by or config.sort_by):
        reasons.append("layout_requires_parquet")
    if request.limits.order_required and (config.partition_by or config.sort_by):
        reasons.append("layout_conflicts_with_record_order")
    baseline = evidence.baseline
    if baseline is not None:
        if config.format == "parquet" and any(
            len(c.decimal_scales) > 1 for c in baseline.columns.values()
        ):
            reasons.append("varying_decimal_scale_requires_encoding")
        for col in config.partition_by + config.sort_by:
            if col not in baseline.columns:
                reasons.append("unknown_layout_column")
    return tuple(sorted(set(reasons)))


def generate(path: Path, request: ConversionRequest, evidence: IntegrityReport) -> CandidateList:
    assert evidence.baseline is not None
    base = CandidateConfig(
        baseline=True, format=request.source.format, codec="original", context=context()
    )
    configs = [
        base,
        CandidateConfig(format="ndjson", codec="gzip", compression_level=6, context=context()),
        CandidateConfig(format="parquet", codec="snappy", context=context()),
        CandidateConfig(format="parquet", codec="zstd", compression_level=3, context=context()),
    ]
    configs.append(configs[3].model_copy(update={"row_group_rows": 16_384}))
    # Only workload-referenced columns guide layouts. Keep the unpartitioned configurations.
    partitions = [c for q in request.workload.queries for c in q.group_by]
    sorts = [q.time_range.column for q in request.workload.queries if q.time_range]
    sorts += [p.column for q in request.workload.queries for p in q.predicates]
    if sorts:
        configs.append(configs[3].model_copy(update={"sort_by": (sorts[0],)}))
    if partitions:
        configs.append(configs[3].model_copy(update={"partition_by": (partitions[0],)}))
    configs = configs[: request.max_candidates]
    return CandidateList(
        input_fingerprint=evidence.baseline.input_fingerprint,
        request_fingerprint=fingerprint(request.model_dump(mode="json")),
        candidates=tuple(
            Candidate(
                configuration=c,
                status="excluded" if (r := exclusion(c, request, evidence)) else "eligible",
                reasons=r,
            )
            for c in configs
        ),
    )
