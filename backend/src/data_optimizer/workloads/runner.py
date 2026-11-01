"""Read-only workload execution against one typed, bounded, in-memory relation."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import duckdb

from data_optimizer.integrity.canonical import encode, frame
from data_optimizer.integrity.models import Baseline, IntegrityOptions
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import ProfileOptions
from data_optimizer.readers.stream import Budget, ProfileError, rows
from data_optimizer.workloads.compiler import TABLE, compile_query
from data_optimizer.workloads.models import Query, Tolerance, Workload, identifier


def connection(limits: IntegrityOptions) -> duckdb.DuckDBPyConnection:
    db = duckdb.connect(
        ":memory:",
        config={
            "enable_external_access": "false",
            "autoload_known_extensions": "false",
            "autoinstall_known_extensions": "false",
            "allow_community_extensions": "false",
            "allow_unsigned_extensions": "false",
            "threads": "1",
            "memory_limit": f"{limits.query_memory_mib}MiB",
            "max_temp_directory_size": "0B",
        },
    )
    db.execute("SET TimeZone='UTC'")
    db.execute("SET lock_configuration=true")
    return db


def logical_types(baseline: Baseline) -> tuple[dict[str, str], dict[str, str]]:
    logical: dict[str, str] = {}
    sql = {}
    mapping = {
        "string": "VARCHAR",
        "integer": "BIGINT",
        "float": "DOUBLE",
        "boolean": "BOOLEAN",
        "timestamp_aware": "TIMESTAMPTZ",
        "timestamp_naive": "TIMESTAMP",
        "date": "DATE",
        "binary": "BLOB",
    }
    for name, column in baseline.columns.items():
        types = set(column.types) - {"null"}
        if len(types) != 1 or column.missing:
            raise ProfileError("workload_requires_rectangular_single_type_columns")
        value_kind = next(iter(types))
        logical[name] = value_kind
        if value_kind == "decimal":
            scale = max((0, *column.decimal_scales))
            precision = max(1, column.decimal_integer_digits + scale)
            if precision > 38:
                raise ProfileError("workload_decimal_precision_unsupported")
            sql[name] = f"DECIMAL({precision},{scale})"
        elif value_kind in mapping:
            sql[name] = mapping[value_kind]
        else:
            raise ProfileError("workload_nested_type_unsupported")
    return logical, sql


def execute_workload(
    path: Path,
    options: ProfileOptions,
    baseline: Baseline,
    workload: Workload,
    limits: IntegrityOptions,
) -> dict[str, list[tuple[Any, ...]]]:
    logical, types = logical_types(baseline)
    queries = {q.id: compile_query(q, logical) for q in workload.queries}
    with connection(limits) as db:
        columns = tuple(types)
        definition = ", ".join(f"{identifier(name)} {types[name]}" for name in columns)
        db.execute(f"CREATE TABLE {TABLE} ({definition})")
        insert = f"INSERT INTO {TABLE} VALUES ({','.join('?' for _ in columns)})"
        batch: list[tuple[Any, ...]] = []
        count = 0
        for row in rows(path, options, Budget(options.max_decoded_bytes)):
            count += 1
            if count > limits.max_rows:
                raise ProfileError("integrity_row_quota")
            if set(row) != set(columns):
                raise ProfileError("input_changed_during_integrity")
            values = tuple(row[name] for name in columns)
            for value in values:
                if isinstance(value, int) and not isinstance(value, bool):
                    if not -(2**63) <= value < 2**63:
                        raise ProfileError("workload_integer_range_unsupported")
                if isinstance(value, datetime):
                    if value.replace(tzinfo=None) in {datetime.min, datetime.max}:
                        raise ProfileError("workload_timestamp_sentinel_unsupported")
                elif isinstance(value, date) and value in {date.min, date.max}:
                    raise ProfileError("workload_date_sentinel_unsupported")
            batch.append(values)
            if len(batch) == 128:
                db.executemany(insert, batch)
                batch.clear()
        if batch:
            db.executemany(insert, batch)
        if count != baseline.row_count or input_digest(path, options.max_raw_bytes) != (
            baseline.input_fingerprint
        ):
            raise ProfileError("input_changed_during_integrity")
        output = {}
        for name, compiled in queries.items():
            result = db.execute(compiled.sql, compiled.parameters).fetchmany(
                limits.max_result_rows + 1
            )
            if len(result) > limits.max_result_rows:
                raise ProfileError("workload_result_row_quota")
            # Validate all returned types, including non-finite aggregate overflow.
            for result_row in result:
                encode(result_row)
            output[name] = result
        return output


def result_fingerprint(result: list[tuple[Any, ...]], ordered: bool) -> str:
    values = [encode(row) for row in result]
    if not ordered:
        values.sort()
    digest = hashlib.sha256()
    for value in values:
        digest.update(frame(b"r", value))
    return digest.hexdigest()


def _close(left: Any, right: Any, tolerance: Tolerance) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, float):
        if not math.isfinite(left) or not math.isfinite(right):
            return False
        # Decimal.from_float avoids tolerance arithmetic silently rounding to binary64.
        with localcontext() as context:
            context.prec = 1100
            a, b = Decimal.from_float(left), Decimal.from_float(right)
            return abs(a - b) <= max(tolerance.absolute, tolerance.relative * max(abs(a), abs(b)))
    return encode(left) == encode(right)


def compare_results(
    left: list[tuple[Any, ...]],
    right: list[tuple[Any, ...]],
    query: Query,
) -> bool:
    if len(left) != len(right):
        return False
    tolerant = bool(query.tolerance.absolute or query.tolerance.relative)
    if not tolerant:
        if query.order_by:
            return [encode(r) for r in left] == [encode(r) for r in right]
        return Counter(encode(r) for r in left) == Counter(encode(r) for r in right)

    def same(a: tuple[Any, ...], b: tuple[Any, ...]) -> bool:
        return len(a) == len(b) and all(
            _close(x, y, query.tolerance) for x, y in zip(a, b, strict=True)
        )

    if query.order_by:
        return all(same(a, b) for a, b in zip(left, right, strict=True))
    # Unordered tolerance requires a multiplicity-preserving perfect matching. A greedy
    # nearest value can fail when tolerance neighborhoods overlap. Bound the quadratic work.
    if len(left) > 256:
        raise ProfileError("tolerant_result_matching_quota")
    edges = [[j for j, b in enumerate(right) if same(a, b)] for a in left]
    matches: dict[int, int] = {}

    def augment(i: int, seen: set[int]) -> bool:
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in matches or augment(matches[j], seen):
                matches[j] = i
                return True
        return False

    return all(augment(i, set()) for i in range(len(left)))
