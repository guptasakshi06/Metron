"""Executable DSL; unlike S01's descriptive contract this contains no SQL or paths."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import Field, StrictStr, model_validator

from data_optimizer.profiling.models import Model
from data_optimizer.readers.stream import kind, override

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")]


class Scalar(Model):
    type: Literal[
        "string",
        "integer",
        "decimal",
        "float",
        "boolean",
        "timestamp_aware",
        "timestamp_naive",
        "date",
    ]
    value: StrictStr = Field(max_length=4096)

    def python_value(self) -> Any:
        if self.type == "float":
            value: Any = float(self.value)
        elif self.type == "date":
            value = date.fromisoformat(self.value)
        elif self.type.startswith("timestamp_"):
            value = override(self.value, "timestamp")
        else:
            value = override(self.value, self.type)
        if kind(value) != self.type:
            raise ValueError("literal type mismatch")
        if isinstance(value, datetime):
            if value.replace(tzinfo=None) in {datetime.min, datetime.max}:
                raise ValueError("engine timestamp sentinel unsupported")
        elif isinstance(value, date) and value in {date.min, date.max}:
            raise ValueError("engine date sentinel unsupported")
        if self.type == "integer" and not -(2**63) <= value < 2**63:
            raise ValueError("integer literal outside supported range")
        if self.type == "decimal" and len(value.as_tuple().digits) > 38:
            raise ValueError("decimal literal outside supported precision")
        return value

    @model_validator(mode="after")
    def valid_value(self) -> Scalar:
        self.python_value()
        return self


class Predicate(Model):
    column: Identifier
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "is_null", "is_not_null"]
    value: Scalar | None = None

    @model_validator(mode="after")
    def valid_value(self) -> Predicate:
        if (self.op in {"is_null", "is_not_null"}) != (self.value is None):
            raise ValueError("only null predicates omit a literal")
        return self


class TimeRange(Model):
    column: Identifier
    start: Scalar
    end: Scalar

    @model_validator(mode="after")
    def ordered(self) -> TimeRange:
        if self.start.type not in {"timestamp_aware", "timestamp_naive"}:
            raise ValueError("time ranges require timestamps")
        if self.start.type != self.end.type:
            raise ValueError("time range awareness mismatch")
        if self.start.python_value() >= self.end.python_value():
            raise ValueError("time range must be nonempty")
        return self


class Aggregate(Model):
    op: Literal["count", "sum", "min", "max", "avg"]
    column: Identifier | None = None
    alias: Identifier

    @model_validator(mode="after")
    def has_column(self) -> Aggregate:
        if self.op != "count" and self.column is None:
            raise ValueError("aggregate requires a column")
        return self


class Tolerance(Model):
    # Applies only to binary floating point query outputs, never stored content.
    absolute: Decimal = Field(default=Decimal(0), ge=0, le=1)
    relative: Decimal = Field(default=Decimal(0), ge=0, le=1)


class Query(Model):
    id: Identifier
    kind: Literal["full_scan", "projection", "filter", "time_range", "grouped_aggregate"]
    columns: tuple[Identifier, ...] = Field(default=(), max_length=128)
    predicates: tuple[Predicate, ...] = Field(default=(), max_length=32)
    time_range: TimeRange | None = None
    group_by: tuple[Identifier, ...] = Field(default=(), max_length=16)
    aggregates: tuple[Aggregate, ...] = Field(default=(), max_length=16)
    order_by: tuple[Identifier, ...] = Field(default=(), max_length=128)
    frequency_per_day: int | None = Field(default=None, ge=0, le=10**12)
    freshness_seconds: int | None = Field(default=None, ge=0, le=10**12)
    target_latency_seconds: Decimal | None = Field(default=None, gt=0)
    tolerance: Tolerance = Tolerance()

    @model_validator(mode="after")
    def coherent(self) -> Query:
        for names in (self.columns, self.group_by, self.order_by):
            if len({n.casefold() for n in names}) != len(names):
                raise ValueError("duplicate column")
        if self.kind == "projection" and not self.columns:
            raise ValueError("projection requires columns")
        if self.kind == "filter" and not self.predicates:
            raise ValueError("filter requires predicates")
        if (self.kind == "time_range") != (self.time_range is not None):
            raise ValueError("time_range operation requires exactly one time range")
        if self.kind == "full_scan" and (self.columns or self.predicates):
            raise ValueError("full_scan cannot restrict rows or columns")
        if self.kind == "grouped_aggregate":
            if self.columns or not self.group_by or not self.aggregates:
                raise ValueError("grouped aggregate requires groups and aggregates")
            outputs = self.group_by + tuple(a.alias for a in self.aggregates)
            if len({n.casefold() for n in outputs}) != len(outputs):
                raise ValueError("duplicate output alias")
        elif self.group_by or self.aggregates:
            raise ValueError("aggregates require grouped_aggregate")
        return self


class Workload(Model):
    version: Literal[1] = 1
    dsl_version: Literal["s04.1"] = "s04.1"
    queries: tuple[Query, ...] = Field(default=(), max_length=32)
    concurrency: int | None = Field(default=None, ge=1, le=1024)
    concurrency_scope: Literal["unknown", "single_process", "production"] = "unknown"

    @model_validator(mode="after")
    def coherent(self) -> Workload:
        if len({q.id for q in self.queries}) != len(self.queries):
            raise ValueError("duplicate query id")
        if (self.concurrency is None) != (self.concurrency_scope == "unknown"):
            raise ValueError("concurrency requires an explicit scope")
        if self.concurrency_scope == "single_process" and self.concurrency != 1:
            raise ValueError("single_process scope requires concurrency=1")
        return self


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value):
        raise ValueError("unsupported_identifier")
    return '"' + value + '"'
