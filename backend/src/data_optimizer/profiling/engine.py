"""Two-pass bounded profiling and reproducible stratified bottom-k selection."""

from __future__ import annotations

import hashlib
import heapq
import platform
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from data_optimizer.profiling.models import (
    Cardinality,
    ColumnProfile,
    Coverage,
    Kind,
    ProfileOptions,
    ProfileReport,
    Widths,
    fingerprint,
    report_digest,
)
from data_optimizer.readers.stream import Budget, ProfileError, canonical, kind, rows


class WidthCounter:
    def __init__(self) -> None:
        self.count = self.total = self.maximum = 0
        self.minimum: int | None = None
        self.bins = [0] * 5

    def add(self, width: int) -> None:
        self.count += 1
        self.total += width
        self.minimum = width if self.minimum is None else min(self.minimum, width)
        self.maximum = max(self.maximum, width)
        self.bins[next((i for i, cap in enumerate((16, 64, 256, 1024)) if width <= cap), 4)] += 1

    def result(self) -> Widths:
        return Widths(
            minimum=self.minimum or 0,
            maximum=self.maximum,
            mean=self.total / self.count if self.count else 0,
            histogram=cast(tuple[int, int, int, int, int], tuple(self.bins)),
        )


class Sketch:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.values: set[int] = set()
        self.heap: list[int] = []
        self.truncated = False

    def add(self, value: bytes) -> None:
        hashed = int.from_bytes(hashlib.sha256(value).digest()[:16], "big")
        if hashed in self.values:
            return
        if len(self.values) == self.capacity:
            self.truncated = True
            if hashed >= -self.heap[0]:
                return
            self.values.remove(-heapq.heapreplace(self.heap, -hashed))
        else:
            heapq.heappush(self.heap, -hashed)
        self.values.add(hashed)

    def result(self, maximum: int) -> Cardinality:
        estimate = (self.capacity - 1) * (2**128) / (-self.heap[0]) if self.truncated else 0
        return Cardinality(
            value=min(maximum, max(self.capacity, round(estimate)))
            if self.truncated
            else len(self.values),
            method="kmv_estimate" if self.truncated else "exact",
            capacity=self.capacity,
        )


class ColumnCounter:
    def __init__(self, capacity: int, sensitive: bool) -> None:
        self.types: Counter[Kind] = Counter()
        self.widths = WidthCounter()
        self.sketch = Sketch(capacity)
        self.sensitive = sensitive
        self.temporal: dict[str, tuple[datetime, datetime]] = {}

    def add(self, value: Any) -> None:
        value_kind = kind(value)
        self.types[value_kind] += 1
        if self.sensitive:
            return
        encoded = canonical(value)
        self.widths.add(len(encoded))
        if value is not None:
            self.sketch.add(encoded)
        if isinstance(value, datetime):
            aware = value.utcoffset() is not None
            scope = "aware_utc" if aware else "naive_wall_clock"
            stamp = value.astimezone(UTC) if aware else value
            lower, upper = self.temporal.get(scope, (stamp, stamp))
            self.temporal[scope] = min(lower, stamp), max(upper, stamp)

    def result(self, name: str, schema: set[Kind], count: int) -> ColumnProfile:
        present, nulls = sum(self.types.values()), self.types.get("null", 0)
        temporal_scope = next(iter(self.temporal)) if len(self.temporal) == 1 else None
        span = None
        if temporal_scope:
            lower, upper = self.temporal[temporal_scope]
            span = (upper - lower).total_seconds()
        return ColumnProfile(
            field=name,
            schema_types=tuple(sorted(schema)),
            type_counts=dict(sorted(self.types.items())),
            present=present,
            missing=count - present,
            nulls=nulls,
            null_density=nulls / present if present else None,
            cardinality=None if self.sensitive else self.sketch.result(present - nulls),
            widths=None if self.sensitive else self.widths.result(),
            temporal_span_seconds=span,
            temporal_scope=cast(Any, temporal_scope),
            sensitive=self.sensitive,
        )


def input_digest(path: Path, maximum: int) -> str:
    if not path.is_file() or path.is_symlink():
        raise ProfileError("regular_file_required")
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as source:
        while block := source.read(65536):
            count += len(block)
            if count > maximum:
                raise ProfileError("raw_byte_quota")
            digest.update(block)
    return digest.hexdigest()


def stratum(row: dict[str, Any], options: ProfileOptions) -> str:
    parts: list[bytes] = []
    if options.source_column:
        # Hash typed source identifiers; raw source values never enter reports.
        parts.append(
            canonical(row[options.source_column])
            if options.source_column in row
            else b"missing_source"
        )
    if options.time_column:
        stamp = row.get(options.time_column)
        if stamp is None:
            parts.append(b"missing_or_null_time")
        elif isinstance(stamp, datetime):
            aware = stamp.utcoffset() is not None
            if aware:
                stamp = stamp.astimezone(UTC)
            parts.append(str((stamp.date(), aware)).encode())
        else:
            raise ProfileError("time_column_requires_timestamp_override")
    return hashlib.sha256(b"".join(str(len(p)).encode() + b":" + p for p in parts)).hexdigest()


def profile(path: Path, options: ProfileOptions) -> ProfileReport:
    import pyarrow

    original = input_digest(path, options.max_raw_bytes)
    schema: dict[str, set[Kind]] = {}
    populations: Counter[str] = Counter()
    selected: dict[str, list[tuple[int, int]]] = {}
    budget = Budget(options.max_decoded_bytes)
    total = 0
    for index, row in enumerate(rows(path, options, budget)):
        total += 1
        for name, value in row.items():
            schema.setdefault(name, set()).add(kind(value))
        if len(schema) > options.max_columns:
            raise ProfileError("column_quota")
        key = stratum(row, options)
        populations[key] += 1
        if len(populations) > options.max_strata:
            raise ProfileError("strata_quota_choose_coarser_or_full_scan")
        if options.sample_rows_per_stratum is not None:
            priority = int.from_bytes(
                hashlib.sha256(f"{options.seed}:{original}:{index}".encode()).digest()[:16], "big"
            )
            heap = selected.setdefault(key, [])
            item = (-priority, index)
            if len(heap) < options.sample_rows_per_stratum:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    if not total:
        raise ProfileError("empty_dataset")
    required = set(options.schema_overrides) | set(options.redacted_fields)
    required |= {x for x in (options.time_column, options.source_column) if x}
    if not required.issubset(schema):
        raise ProfileError("unknown_configured_field")
    selected_indices = {index for heap in selected.values() for _, index in heap}
    accumulators = {
        name: ColumnCounter(options.cardinality_capacity, name in options.redacted_fields)
        for name in sorted(schema)
    }
    profiled = 0
    row_widths = WidthCounter()
    second_budget = Budget(options.max_decoded_bytes)
    second_count = 0
    for index, row in enumerate(rows(path, options, second_budget)):
        second_count += 1
        if options.sample_rows_per_stratum is not None and index not in selected_indices:
            continue
        profiled += 1
        # Do not expose widths of sensitive values even indirectly through row widths.
        row_widths.add(
            sum(len(canonical(v)) for k, v in row.items() if k not in options.redacted_fields)
        )
        for name, value in row.items():
            if name not in accumulators:
                raise ProfileError("input_changed_during_profile")
            accumulators[name].add(value)
    if second_count != total or input_digest(path, options.max_raw_bytes) != original:
        raise ProfileError("input_changed_during_profile")
    columns = tuple(
        c.result(
            name if options.include_field_names and not c.sensitive else f"column_{i + 1}",
            schema[name],
            profiled,
        )
        for i, (name, c) in enumerate(accumulators.items())
    )
    warnings = ["metadata_may_be_sensitive_review_before_upload"]
    if options.format == "csv":
        warnings.append("csv_text_requires_explicit_overrides")
    if any({"object", "array"} & types for types in schema.values()):
        warnings.append("nested_values_are_opaque")
    if any(len(types - {"null"}) > 1 for types in schema.values()):
        warnings.append("mixed_types_require_schema_review")
    if any({"timestamp_aware", "timestamp_naive"} <= types for types in schema.values()):
        warnings.append("timestamps_have_mixed_awareness")
    if options.sample_rows_per_stratum is not None:
        warnings.append("sample_statistics_not_population_estimates")
    if options.redacted_fields:
        warnings.append("sensitive_statistics_redacted")
    sizes = WidthCounter()
    sizes.add(path.stat().st_size)
    arrow_schema = None
    if options.format == "parquet":
        import pyarrow.parquet as pq

        arrow_schema = str(pq.ParquetFile(path, arrow_extensions_enabled=False).schema_arrow)
    report = ProfileReport(
        input_fingerprint=original,
        schema_fingerprint=fingerprint(
            {"types": {k: sorted(v) for k, v in schema.items()}, "arrow_schema": arrow_schema}
        ),
        settings_fingerprint=fingerprint(options.model_dump(mode="json")),
        profile_fingerprint="0" * 64,
        engine_versions={"python": platform.python_version(), "pyarrow": pyarrow.__version__},
        format=options.format,
        physical_bytes=path.stat().st_size,
        decoded_bytes=budget.used,
        file_sizes=sizes.result(),
        row_count=total,
        profiled_rows=profiled,
        sample_fraction=profiled / total,
        seed=options.seed,
        sampling="full_scan"
        if options.sample_rows_per_stratum is None
        else "seeded_bottom_k_per_stratum",
        strata_by=tuple(
            cast(Any, x)
            for x in (
                "time_day" if options.time_column else None,
                "source" if options.source_column else None,
            )
            if x
        ),
        coverage=tuple(
            Coverage(
                stratum=f"stratum_{i + 1}",
                rows=count,
                profiled_rows=len(selected[key]) if selected else count,
            )
            for i, (key, count) in enumerate(sorted(populations.items()))
        ),
        columns=columns,
        row_widths=row_widths.result(),
        field_names_redacted=not options.include_field_names,
        warnings=cast(Any, tuple(warnings)),
    )
    return report.model_copy(update={"profile_fingerprint": report_digest(report)})
