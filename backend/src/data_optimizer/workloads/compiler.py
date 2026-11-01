"""All identifiers validated, values bound, and relation name fixed by code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from data_optimizer.workloads.models import Query, identifier

TABLE = '"assessment_data"'
OPERATORS = {"eq": "=", "ne": "<>", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    parameters: tuple[Any, ...]
    outputs: tuple[str, ...]


def compile_query(query: Query, schema: dict[str, str]) -> CompiledQuery:
    # Revalidate to reject model_construct/model_copy mutations at the execution boundary.
    query = Query.model_validate(query.model_dump())
    for name in schema:
        identifier(name)
    if len({n.casefold() for n in schema}) != len(schema):
        raise ValueError("case_insensitive_identifier_collision")
    referenced = set(query.columns + query.group_by)
    referenced.update(p.column for p in query.predicates)
    referenced.update(a.column for a in query.aggregates if a.column is not None)
    if query.time_range:
        referenced.add(query.time_range.column)
    if not referenced.issubset(schema):
        raise ValueError("unknown_column")
    parameters: list[Any] = []
    clauses = []
    for predicate in query.predicates:
        col = identifier(predicate.column)
        if predicate.value is None:
            clauses.append(f"{col} IS {'NOT ' if predicate.op == 'is_not_null' else ''}NULL")
        else:
            if schema[predicate.column] != predicate.value.type:
                raise ValueError("predicate_type_mismatch")
            clauses.append(f"{col} {OPERATORS[predicate.op]} ?")
            parameters.append(predicate.value.python_value())
    if query.time_range:
        time = query.time_range
        if schema[time.column] != time.start.type:
            raise ValueError("time_column_type_mismatch")
        col = identifier(time.column)
        clauses.extend((f"{col} >= ?", f"{col} < ?"))
        parameters.extend((time.start.python_value(), time.end.python_value()))
    if query.kind == "grouped_aggregate":
        outputs = query.group_by + tuple(a.alias for a in query.aggregates)
        expressions = [identifier(c) for c in query.group_by]
        for aggregate in query.aggregates:
            if aggregate.op in {"sum", "avg"} and schema.get(aggregate.column or "") not in {
                "integer",
                "decimal",
                "float",
            }:
                raise ValueError("numeric_aggregate_requires_number")
            column = identifier(aggregate.column) if aggregate.column else "*"
            expressions.append(f"{aggregate.op.upper()}({column}) AS {identifier(aggregate.alias)}")
    else:
        outputs = query.columns or tuple(sorted(schema))
        expressions = [identifier(c) for c in outputs]
    if not outputs:
        raise ValueError("empty_schema_unsupported")
    if len({n.casefold() for n in outputs}) != len(outputs):
        raise ValueError("case_insensitive_output_collision")
    sql = f"SELECT {', '.join(expressions)} FROM {TABLE}"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    if query.group_by:
        sql += " GROUP BY " + ", ".join(identifier(c) for c in query.group_by)
    if query.order_by:
        if set(query.order_by) != set(outputs):
            raise ValueError("ordering_must_cover_all_outputs")
        sql += " ORDER BY " + ", ".join(identifier(c) + " NULLS FIRST" for c in query.order_by)
    return CompiledQuery(sql, tuple(parameters), outputs)
