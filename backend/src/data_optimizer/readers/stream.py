"""Streaming text and Arrow Parquet readers; no inference that coerces identifiers."""

from __future__ import annotations

import csv
import gzip
import json
import math
import re
import struct
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO, cast

from data_optimizer.profiling.models import Kind, ProfileOptions


class ProfileError(ValueError):
    """Only stable error codes may cross the worker boundary."""


class Budget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.used = 0

    def add(self, count: int) -> None:
        self.used += count
        if self.used > self.maximum:
            raise ProfileError("decoded_byte_quota")


def canonical(value: Any) -> bytes:
    """Typed length-delimited value encoding for statistics, not integrity proof."""
    if isinstance(value, dict):
        return (
            b"o"
            + str(len(value)).encode()
            + b":"
            + b"".join(canonical(k) + canonical(v) for k, v in sorted(value.items()))
        )
    if isinstance(value, (list, tuple)):
        return b"a" + str(len(value)).encode() + b":" + b"".join(canonical(v) for v in value)
    if isinstance(value, bytes):
        payload = value
    else:
        payload = str(value).encode("utf-8")
    return kind(value).encode() + str(len(payload)).encode() + b":" + payload


def kind(value: Any) -> Kind:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, Decimal):
        return "decimal"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProfileError("nonfinite_number_unsupported")
        return "float"
    if isinstance(value, datetime):
        return "timestamp_aware" if value.utcoffset() is not None else "timestamp_naive"
    if isinstance(value, date):
        return "date"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bytes):
        return "binary"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    raise ProfileError("unsupported_logical_type")


def override(value: Any, target: str) -> Any:
    if value is None:
        return None
    try:
        if target == "string":
            if not isinstance(value, str):
                raise ValueError()
            return value
        if target == "integer":
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ValueError()
            return int(value)
        if target == "decimal":
            if isinstance(value, (bool, float, dict, list)):
                raise ValueError()
            number = Decimal(value)
            if not number.is_finite():
                raise ValueError()
            return number
        if target == "timestamp":
            if isinstance(value, str):
                fraction = re.search(r"[T ]\d{2}:\d{2}:\d{2}[.,](\d+)", value)
                if fraction and len(fraction.group(1)) > 6:
                    raise ProfileError("timestamp_precision_unsupported")
            parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
            if not isinstance(parsed, datetime):
                raise ValueError()
            return parsed
        if target == "boolean":
            if isinstance(value, bool):
                return value
            if value not in ("true", "false"):
                raise ValueError()
            return value == "true"
    except ProfileError:
        raise
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        raise ProfileError("schema_override_mismatch") from None
    raise ProfileError("unsupported_override")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileError("duplicate_json_key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ProfileError("nonfinite_number_unsupported")


def _lines(stream: BinaryIO, options: ProfileOptions, budget: Budget) -> Iterator[str]:
    first = True
    while True:
        line = stream.readline(options.max_record_bytes + 1)
        if not line:
            return
        budget.add(len(line))
        if len(line) > options.max_record_bytes:
            raise ProfileError("record_byte_quota")
        yield line.decode("utf-8-sig" if first else "utf-8", errors="strict")
        first = False


def _text(path: Path, options: ProfileOptions, budget: Budget) -> Iterator[dict[str, Any]]:
    with path.open("rb") as raw:
        compressed = raw.read(2) == b"\x1f\x8b"
    if compressed and options.format != "ndjson":
        raise ProfileError("unsupported_compression")
    with gzip.open(path, "rb") if compressed else path.open("rb") as stream:
        lines = _lines(cast(BinaryIO, stream), options, budget)
        if options.format == "ndjson":
            for line in lines:
                if not line.strip():
                    continue
                row = json.loads(
                    line, parse_float=Decimal, parse_constant=_constant, object_pairs_hook=_pairs
                )
                if not isinstance(row, dict):
                    raise ProfileError("json_object_required")
                yield row
        else:
            csv.field_size_limit(options.max_record_bytes)
            reader = csv.reader(lines, strict=True)
            header = next(reader, None)
            if (
                not header
                or len(header) > options.max_columns
                or len(set(header)) != len(header)
                or any(not x.strip() for x in header)
            ):
                raise ProfileError("invalid_csv_header")
            for values in reader:
                if len(values) != len(header):
                    raise ProfileError("nonrectangular_csv")
                if sum(len(v.encode()) for v in values) > options.max_record_bytes:
                    raise ProfileError("record_byte_quota")
                yield dict(
                    zip(
                        header,
                        (None if v in options.csv_null_tokens else v for v in values),
                        strict=True,
                    )
                )


def _parquet(path: Path, options: ProfileOptions, budget: Budget) -> Iterator[dict[str, Any]]:
    import pyarrow.parquet as pq

    with path.open("rb") as stream:
        if stream.read(4) != b"PAR1" or path.stat().st_size < 12:
            raise ProfileError("invalid_parquet")
        stream.seek(-8, 2)
        footer = stream.read(8)
        if footer[4:] != b"PAR1" or struct.unpack("<I", footer[:4])[0] > min(
            16_777_216, path.stat().st_size - 12
        ):
            raise ProfileError("parquet_metadata_quota")
    parquet = pq.ParquetFile(
        path,
        arrow_extensions_enabled=False,
        thrift_string_size_limit=16_777_216,
        thrift_container_size_limit=100_000,
    )
    if len(set(parquet.schema_arrow.names)) != len(parquet.schema_arrow.names):
        raise ProfileError("duplicate_parquet_field")
    if len(parquet.schema_arrow) > options.max_columns:
        raise ProfileError("column_quota")
    expanded = sum(
        parquet.metadata.row_group(g).column(c).total_uncompressed_size
        for g in range(parquet.metadata.num_row_groups)
        for c in range(parquet.metadata.row_group(g).num_columns)
    )
    if expanded > options.max_decoded_bytes:
        raise ProfileError("decoded_byte_quota")
    # Small batches; Arrow/native allocation still enclosed by the process memory quota.
    for batch in parquet.iter_batches(batch_size=128, use_threads=False):
        budget.add(batch.nbytes)
        try:
            yield from batch.to_pylist()
        except ValueError:
            raise ProfileError("parquet_precision_or_type_unsupported") from None


def rows(path: Path, options: ProfileOptions, budget: Budget) -> Iterator[dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise ProfileError("regular_file_required")
    if path.stat().st_size > options.max_raw_bytes:
        raise ProfileError("raw_byte_quota")
    source = (
        _parquet(path, options, budget)
        if options.format == "parquet"
        else _text(path, options, budget)
    )
    try:
        for row in source:
            if len(row) > options.max_columns or any(len(k) > 256 for k in row):
                raise ProfileError("column_quota")
            if len(canonical(row)) > options.max_record_bytes:
                raise ProfileError("record_byte_quota")
            for name, target in options.schema_overrides.items():
                if name in row:
                    row[name] = override(row[name], target)
            yield row
    except ProfileError:
        raise
    except (UnicodeError, csv.Error, ValueError, TypeError, OSError, EOFError, RecursionError):
        raise ProfileError("invalid_structure_or_unsupported_type") from None
