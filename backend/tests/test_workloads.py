from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from data_optimizer.integrity.engine import verify
from data_optimizer.integrity.models import IntegrityOptions
from data_optimizer.readers.stream import ProfileError
from data_optimizer.workloads.compiler import compile_query
from data_optimizer.workloads.models import Query, Scalar, Workload
from data_optimizer.workloads.runner import compare_results, connection, execute_workload
from fixtures.integrity import generate, options, request, workload


def test_golden_queries_execute_real_duckdb(tmp_path: Path) -> None:
    files = generate(tmp_path)
    report = verify(files["events.csv"], files["events.parquet"], request("csv", "parquet"))
    assert report.status == "passed"
    assert report.workload_status == "passed"
    assert report.performance_status == "not_measured"
    baseline = report.baseline
    assert baseline is not None
    results = execute_workload(
        files["events.csv"], options("csv"), baseline, workload(), IntegrityOptions()
    )
    assert len(results["scan"]) == 3
    assert results["ids"].count(("0001",)) == 2
    assert results["filter"] == [("0002", Decimal("2.30"))]
    assert results["time"] == [("0001",), ("0001",)]
    assert results["nulls"] == [("0001",), ("0001",)]
    grouped = {r[0]: r[1:] for r in results["groups"]}
    assert grouped["a"] == (2, Decimal("2.40"), Decimal("1.20"), Decimal("1.20"), 1.2)
    assert grouped["b"] == (1, Decimal("2.30"), Decimal("2.30"), Decimal("2.30"), 2.3)


def test_high_precision_decimal_queries_remain_exact(tmp_path: Path) -> None:
    path = tmp_path / "exact.ndjson"
    value = "123456789012345678.123456789012345678"
    path.write_text('{"x":' + value + "}\n")
    from data_optimizer.integrity.models import VerificationRequest
    from data_optimizer.profiling.models import ProfileOptions

    opts = ProfileOptions(format="ndjson")
    query = Query(id="q", kind="full_scan")
    req = VerificationRequest(baseline=opts, candidate=opts, workload=Workload(queries=(query,)))
    report = verify(path, path, req)
    assert report.status == "passed"
    assert execute_workload(path, opts, report.baseline, req.workload, req.limits)["q"] == [
        (Decimal(value),)
    ]


@pytest.mark.parametrize(
    "name",
    [
        'id" FROM other; --',
        "../other",
        "other.id",
        "read_csv('/etc/passwd')",
        "id;DROP TABLE x",
    ],
)
def test_identifiers_are_not_expressions(name: str) -> None:
    with pytest.raises(ValidationError):
        Query(id="unsafe", kind="projection", columns=(name,))


def test_literals_are_bound_and_dataset_is_fixed() -> None:
    payload = "x'; SELECT * FROM read_csv('/etc/passwd'); --"
    query = Query.model_validate(
        {
            "id": "safe",
            "kind": "filter",
            "columns": ["id"],
            "predicates": [
                {"column": "id", "op": "eq", "value": {"type": "string", "value": payload}}
            ],
        }
    )
    compiled = compile_query(query, {"id": "string"})
    assert payload not in compiled.sql
    assert compiled.parameters == (payload,)
    assert compiled.sql == 'SELECT "id" FROM "assessment_data" WHERE "id" = ?'
    with connection(IntegrityOptions()) as db:
        db.execute("CREATE TABLE assessment_data(id VARCHAR)")
        db.execute("CREATE TABLE other(id VARCHAR)")
        db.execute("INSERT INTO other VALUES (?)", ["SECRET"])
        db.execute("INSERT INTO assessment_data VALUES (?)", [payload])
        assert db.execute(compiled.sql, compiled.parameters).fetchall() == [(payload,)]
    with pytest.raises(ValueError, match="unknown_column"):
        compile_query(Query(id="other", kind="projection", columns=("other",)), {"id": "string"})
    with pytest.raises(ValidationError):
        Workload.model_validate({"dataset": "other", "queries": []})
    with pytest.raises(ValidationError):
        Query.model_validate({"id": "path", "kind": "full_scan", "sql": "SELECT * FROM other"})


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_csv('https://example.com/private.csv')",
        "COPY (SELECT 1) TO '/tmp/data-optimizer-must-not-exist.csv'",
        "INSTALL httpfs",
        "LOAD httpfs",
        "SET enable_external_access=true",
        "SET threads=4",
    ],
)
def test_engine_external_access_is_disabled(sql: str) -> None:
    with connection(IntegrityOptions()) as db, pytest.raises(duckdb.Error):
        db.execute(sql)


@pytest.mark.parametrize(
    "data",
    [
        {"id": "q", "kind": "projection"},
        {"id": "q", "kind": "filter"},
        {"id": "q", "kind": "full_scan", "predicates": [{"column": "id", "op": "is_null"}]},
        {"id": "q", "kind": "projection", "columns": ["id", "id"]},
        {
            "id": "q",
            "kind": "grouped_aggregate",
            "group_by": ["id"],
            "aggregates": [{"op": "count", "alias": "id"}],
        },
        {"id": "q", "kind": "projection", "columns": ["id"], "limit": 1},
        {
            "id": "q",
            "kind": "time_range",
            "time_range": {
                "column": "t",
                "start": {"type": "timestamp_aware", "value": "2026-01-02T00:00:00Z"},
                "end": {"type": "timestamp_aware", "value": "2026-01-01T00:00:00Z"},
            },
        },
    ],
)
def test_dsl_rejects_invalid_operations(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Query.model_validate(data)


@pytest.mark.parametrize(
    "typ,value",
    [
        ("decimal", "NaN"),
        ("float", "inf"),
        ("boolean", "1"),
        ("integer", str(2**80)),
        ("timestamp_naive", "2026-01-01T00:00:00Z"),
        ("timestamp_aware", "2026-01-01T00:00:00.1234567Z"),
    ],
)
def test_typed_literals_reject_coercion(typ: str, value: str) -> None:
    with pytest.raises(ValueError):
        Scalar.model_validate({"type": typ, "value": value})


def test_unknowns_and_concurrency_scope() -> None:
    q = Query(id="q", kind="full_scan")
    w = Workload(queries=(q,))
    assert Workload.model_validate_json(w.model_dump_json()).queries[0].frequency_per_day is None
    assert w.concurrency is None and q.freshness_seconds is None
    with pytest.raises(ValueError):
        Workload(concurrency=4)
    with pytest.raises(ValueError):
        Workload(concurrency=4, concurrency_scope="single_process")
    with pytest.raises(ValueError):
        Workload(queries=(q, q))


def test_compiler_types_and_total_order() -> None:
    with pytest.raises(ValueError, match="case_insensitive_identifier_collision"):
        compile_query(Query(id="q", kind="full_scan"), {"id": "string", "ID": "string"})
    q = Query.model_validate(
        {
            "id": "q",
            "kind": "filter",
            "predicates": [
                {"column": "id", "op": "eq", "value": {"type": "integer", "value": "1"}}
            ],
        }
    )
    with pytest.raises(ValueError, match="predicate_type_mismatch"):
        compile_query(q, {"id": "string"})
    q = Query(id="q", kind="projection", columns=("id", "x"), order_by=("id",))
    with pytest.raises(ValueError, match="ordering_must_cover_all_outputs"):
        compile_query(q, {"id": "string", "x": "integer"})


def test_output_order_multiplicity_and_float_policy() -> None:
    q = Query(id="q", kind="projection", columns=("x",))
    assert compare_results([(1,), (2,), (1,)], [(1,), (1,), (2,)], q)
    assert not compare_results([(1,), (2,), (1,)], [(1,), (2,), (2,)], q)
    assert not compare_results([(1.0,)], [(1.00001,)], q)
    ordered = q.model_copy(update={"order_by": ("x",)})
    assert not compare_results([(1,), (2,)], [(2,), (1,)], ordered)
    tolerant = Query.model_validate(
        {"id": "q", "kind": "projection", "columns": ["x"], "tolerance": {"absolute": "0.11"}}
    )
    # Needs reassignment: 0.1 can match either, 0.0 can match only 0.0.
    assert compare_results([(0.1,), (0.0,)], [(0.0,), (0.2,)], tolerant)
    assert not compare_results([(0.1,), (0.0,)], [(0.2,), (0.2,)], tolerant)
    assert not compare_results([(Decimal("1.00"),)], [(Decimal("1.01"),)], tolerant)
    assert not compare_results([(1,)], [(1.0,)], tolerant)
    assert not compare_results([(None,)], [(0.0,)], tolerant)
    with pytest.raises(ProfileError, match="tolerant_result_matching_quota"):
        compare_results([(0.0,)] * 257, [(0.0,)] * 257, tolerant)
