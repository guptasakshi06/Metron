"""Streaming semantic summaries and an exact disk-backed multiset of canonical rows."""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from decimal import Decimal
from pathlib import Path

from data_optimizer.integrity.canonical import encode, frame
from data_optimizer.integrity.models import Baseline, Capability, ColumnBaseline, IntegrityOptions
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import Kind, ProfileOptions, fingerprint
from data_optimizer.readers.stream import Budget, ProfileError, kind, rows


def create_store(path: Path, limits: IntegrityOptions) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA page_size=4096")
    db.execute(f"PRAGMA max_page_count={limits.max_spill_bytes // 4096}")
    db.execute("PRAGMA cache_size=-2048")
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("PRAGMA journal_mode=OFF")
    db.execute(
        "CREATE TABLE content (row BLOB PRIMARY KEY, n INTEGER NOT NULL, c INTEGER NOT NULL) "
        "WITHOUT ROWID"
    )
    return db


def summarize(
    path: Path,
    options: ProfileOptions,
    limits: IntegrityOptions,
    db: sqlite3.Connection,
    sign: int,
) -> Baseline:
    if options.sample_rows_per_stratum is not None:
        raise ProfileError("integrity_requires_full_scan")
    before = input_digest(path, options.max_raw_bytes)
    counters: dict[str, Counter[Kind]] = {}
    scales: dict[str, set[int]] = {}
    integer_digits: dict[str, int] = {}
    integer_out_of_range: set[str] = set()
    count = 0
    ordered = hashlib.sha256()
    for row in rows(path, options, Budget(options.max_decoded_bytes)):
        count += 1
        if count > limits.max_rows:
            raise ProfileError("integrity_row_quota")
        encoded = encode(row)
        ordered.update(frame(b"r", encoded))
        try:
            db.execute(
                "INSERT INTO content(row,n,c) VALUES (?,?,?) "
                "ON CONFLICT(row) DO UPDATE SET n=n+excluded.n,c=c+excluded.c",
                (encoded, sign, int(sign == -1)),
            )
        except sqlite3.DatabaseError:
            raise ProfileError("integrity_spill_quota") from None
        for name, value in row.items():
            counters.setdefault(name, Counter())[kind(value)] += 1
            if isinstance(value, int) and not isinstance(value, bool):
                if not -(2**63) <= value < 2**63:
                    integer_out_of_range.add(name)
            if isinstance(value, Decimal):
                exponent = value.as_tuple().exponent
                if not isinstance(exponent, int):
                    raise ProfileError("nonfinite_number_unsupported")
                scales.setdefault(name, set()).add(-exponent)
                integer_digits[name] = max(
                    integer_digits.get(name, 0), len(value.as_tuple().digits) + exponent, 0
                )
        if len(counters) > options.max_columns:
            raise ProfileError("column_quota")
    if not count:
        raise ProfileError("empty_dataset_unsupported")
    if not set(options.schema_overrides).issubset(counters):
        raise ProfileError("unknown_override_column")
    if input_digest(path, options.max_raw_bytes) != before:
        raise ProfileError("input_changed_during_integrity")
    declared = None
    if options.format == "parquet":
        import pyarrow.parquet as pq

        schema = pq.ParquetFile(path, arrow_extensions_enabled=False).schema_arrow
        declared = hashlib.sha256(schema.serialize().to_pybytes()).hexdigest()
    content = hashlib.sha256()
    # The persisted fingerprint is useful provenance. Equality is proved using full bytes
    # and signed counts in SQLite, rather than trusting a commutative hash accumulator.
    selection = (
        "SELECT row,n FROM content ORDER BY row"
        if sign == 1
        else ("SELECT row,c FROM content WHERE c>0 ORDER BY row")
    )
    for value, multiplicity in db.execute(selection):
        content.update(frame(b"r", value) + encode(multiplicity))
    return Baseline(
        input_fingerprint=before,
        settings_fingerprint=fingerprint(options.model_dump(mode="json")),
        row_count=count,
        columns={
            name: ColumnBaseline(
                types=tuple(sorted(counter)),
                type_counts=dict(counter),
                missing=count - sum(counter.values()),
                nulls=counter["null"],
                decimal_scales=tuple(sorted(scales.get(name, set()))),
                decimal_integer_digits=integer_digits.get(name, 0),
                integer_out_of_range=name in integer_out_of_range,
            )
            for name, counter in sorted(counters.items())
        },
        declared_schema_fingerprint=declared,
        content_fingerprint=content.hexdigest(),
        ordered_fingerprint=ordered.hexdigest(),
    )


def capabilities(baseline: Baseline, options: ProfileOptions) -> dict[str, Capability]:
    all_types = {t for c in baseline.columns.values() for t in c.types if t != "null"}
    missing = any(c.missing for c in baseline.columns.values())
    mixed = any(len(set(c.types) - {"null"}) > 1 for c in baseline.columns.values())
    nested = bool(all_types & {"array", "object"})
    parquet_reasons = []
    if not baseline.columns:
        parquet_reasons.append("empty_schema_requires_row_encoding")
    if missing:
        parquet_reasons.append("missing_fields_require_presence_encoding")
    if mixed:
        parquet_reasons.append("mixed_types_require_tagged_encoding")
    if nested:
        parquet_reasons.append("nested_conversion_requires_explicit_schema")
    if any(c.integer_out_of_range for c in baseline.columns.values()):
        parquet_reasons.append("integer_exceeds_int64")
    if any(
        c.decimal_integer_digits + max((0, *c.decimal_scales)) > 38
        for c in baseline.columns.values()
    ):
        parquet_reasons.append("decimal_exceeds_decimal128")
    query_reasons = list(parquet_reasons)
    try:
        from data_optimizer.workloads.models import identifier

        for name in baseline.columns:
            identifier(name)
        if len({n.casefold() for n in baseline.columns}) != len(baseline.columns):
            raise ValueError("case_insensitive_identifier_collision")
    except ValueError:
        query_reasons.append("unsupported_identifier")
    if any(not (set(c.types) - {"null"}) for c in baseline.columns.values()):
        query_reasons.append("all_null_column_requires_schema")
    ndjson_reasons = []
    if nested and options.format != "ndjson":
        ndjson_reasons.append("nested_ndjson_requires_encoding_contract")
    if all_types & {"float", "binary", "date"}:
        ndjson_reasons.append("typed_values_require_encoding_contract")
    for name, col in baseline.columns.items():
        if set(col.types) & {"timestamp_aware", "timestamp_naive"}:
            if options.schema_overrides.get(name) != "timestamp":
                ndjson_reasons.append("timestamp_requires_reviewed_override")
    csv_reasons = []
    if not baseline.columns:
        csv_reasons.append("empty_schema_unsupported")
    if missing or all_types - {"string"} or any(c.nulls for c in baseline.columns.values()):
        csv_reasons.append("csv_conversion_supports_rectangular_nonnull_text_only")
    return {
        name: Capability(supported=not reasons, reasons=tuple(sorted(set(reasons))))
        for name, reasons in {
            "parquet": parquet_reasons,
            "ndjson": ndjson_reasons,
            "csv": csv_reasons,
            "workload": query_reasons,
        }.items()
    }
