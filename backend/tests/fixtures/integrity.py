"""S04 golden analytical data and deliberately corrupted copies; entirely synthetic."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from data_optimizer.integrity.models import VerificationRequest
from data_optimizer.profiling.models import ProfileOptions
from data_optimizer.workloads.models import Workload

ONE = (
    '{"id":"0001","amount":1.20,"timestamp":"2026-01-01T00:00:00Z","category":"a","optional":null}'
)
TWO = (
    '{"id":"0002","amount":2.30,"timestamp":"2026-01-02T00:00:00Z",'
    '"category":"b","optional":"present"}'
)


def generate(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        name: directory / name
        for name in (
            "events.csv",
            "events.ndjson",
            "events.ndjson.gz",
            "events.parquet",
            "reordered.ndjson",
            "lost.ndjson",
            "precision.ndjson",
            "duplicates.ndjson",
            "timestamp.ndjson",
            "identifier.ndjson",
            "missing.ndjson",
        )
    }
    text = "\n".join((ONE, TWO, ONE)) + "\n"
    paths["events.ndjson"].write_text(text)
    paths["events.ndjson.gz"].write_bytes(gzip.compress(text.encode(), mtime=0))
    paths["reordered.ndjson"].write_text("\n".join((TWO, ONE, ONE)) + "\n")
    paths["lost.ndjson"].write_text("\n".join((ONE, TWO)) + "\n")
    paths["precision.ndjson"].write_text(text.replace("1.20", "1.2", 1))
    paths["duplicates.ndjson"].write_text("\n".join((ONE, TWO, TWO)) + "\n")
    paths["timestamp.ndjson"].write_text(text.replace("T00:00:00Z", "T01:00:00Z", 1))
    paths["identifier.ndjson"].write_text(text.replace('"0001"', "1", 1))
    paths["missing.ndjson"].write_text(text.replace(',"optional":null', "", 1))
    paths["events.csv"].write_text(
        "id,amount,timestamp,category,optional\n"
        "0001,1.20,2026-01-01T00:00:00Z,a,NULL\n"
        "0002,2.30,2026-01-02T00:00:00Z,b,present\n"
        "0001,1.20,2026-01-01T00:00:00Z,a,NULL\n"
    )
    first = {
        "id": "0001",
        "amount": Decimal("1.20"),
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "category": "a",
        "optional": None,
    }
    second = {
        "id": "0002",
        "amount": Decimal("2.30"),
        "timestamp": datetime(2026, 1, 2, tzinfo=UTC),
        "category": "b",
        "optional": "present",
    }
    schema = pa.schema(
        [
            ("id", pa.string()),
            ("amount", pa.decimal128(10, 2)),
            ("timestamp", pa.timestamp("us", tz="UTC")),
            ("category", pa.string()),
            ("optional", pa.string()),
        ]
    )
    pq.write_table(
        pa.Table.from_pylist([first, second, first], schema=schema), paths["events.parquet"]
    )
    return paths


def options(fmt: str) -> ProfileOptions:
    return ProfileOptions.model_validate(
        {
            "format": fmt,
            "schema_overrides": {"amount": "decimal", "timestamp": "timestamp"}
            if fmt == "csv"
            else {"timestamp": "timestamp"}
            if fmt == "ndjson"
            else {},
            "csv_null_tokens": ["NULL"] if fmt == "csv" else [],
        }
    )


def workload() -> Workload:
    return Workload.model_validate(
        {
            "concurrency": 1,
            "concurrency_scope": "single_process",
            "queries": [
                {"id": "scan", "kind": "full_scan"},
                {"id": "ids", "kind": "projection", "columns": ["id"]},
                {
                    "id": "filter",
                    "kind": "filter",
                    "columns": ["id", "amount"],
                    "predicates": [
                        {
                            "column": "amount",
                            "op": "ge",
                            "value": {"type": "decimal", "value": "2.00"},
                        }
                    ],
                },
                {
                    "id": "nulls",
                    "kind": "filter",
                    "columns": ["id"],
                    "predicates": [{"column": "optional", "op": "is_null"}],
                },
                {
                    "id": "time",
                    "kind": "time_range",
                    "columns": ["id"],
                    "time_range": {
                        "column": "timestamp",
                        "start": {"type": "timestamp_aware", "value": "2026-01-01T00:00:00Z"},
                        "end": {"type": "timestamp_aware", "value": "2026-01-02T00:00:00Z"},
                    },
                },
                {
                    "id": "groups",
                    "kind": "grouped_aggregate",
                    "group_by": ["category"],
                    "aggregates": [
                        {"op": "count", "alias": "n"},
                        {"op": "sum", "column": "amount", "alias": "total"},
                        {"op": "min", "column": "amount", "alias": "low"},
                        {"op": "max", "column": "amount", "alias": "high"},
                        {"op": "avg", "column": "amount", "alias": "mean"},
                    ],
                },
            ],
        }
    )


def request(
    left: str = "ndjson", right: str = "ndjson", queries: bool = True
) -> VerificationRequest:
    return VerificationRequest(
        baseline=options(left),
        candidate=options(right),
        workload=workload() if queries else Workload(),
    )
