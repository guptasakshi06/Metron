from __future__ import annotations

import gzip
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data_optimizer.cli import main
from data_optimizer.integrity.canonical import encode
from data_optimizer.integrity.engine import verify
from data_optimizer.integrity.models import IntegrityOptions, IntegrityReport, VerificationRequest
from data_optimizer.integrity.service import read_evidence, verify_files, write_evidence
from data_optimizer.profiling.models import ProfileOptions
from data_optimizer.readers.stream import ProfileError
from data_optimizer.workloads.models import Query, Workload
from fixtures.integrity import generate, options, request


@pytest.mark.parametrize(
    "fmt,name",
    [
        ("csv", "events.csv"),
        ("ndjson", "events.ndjson"),
        ("ndjson", "events.ndjson.gz"),
        ("parquet", "events.parquet"),
    ],
)
def test_cross_format_integrity(fmt: str, name: str, tmp_path: Path) -> None:
    files = generate(tmp_path)
    report = verify(files["events.ndjson"], files[name], request("ndjson", fmt))
    assert report.status == "passed"
    assert report.baseline.content_fingerprint == report.candidate.content_fingerprint
    assert report.baseline.row_count == 3
    assert report.baseline.columns["optional"].nulls == 2
    assert report.baseline.columns["amount"].decimal_scales == (2,)
    assert all(q.status == "passed" for q in report.queries)


@pytest.mark.parametrize(
    "name,reason",
    [
        ("lost.ndjson", "record_count_changed"),
        ("precision.ndjson", "decimal_scale_or_precision_changed"),
        ("duplicates.ndjson", "typed_content_or_duplicate_multiplicity_changed"),
        ("timestamp.ndjson", "typed_content_or_duplicate_multiplicity_changed"),
        ("identifier.ndjson", "field_or_logical_type_changed"),
        ("missing.ndjson", "null_or_missing_counts_changed"),
    ],
)
def test_mutations_fail_with_reasons(name: str, reason: str, tmp_path: Path) -> None:
    files = generate(tmp_path)
    report = verify(files["events.ndjson"], files[name], request())
    assert report.status == "failed"
    assert reason in {check.reason for check in report.checks if check.status == "failed"}
    if name in {"lost.ndjson", "duplicates.ndjson", "timestamp.ndjson"}:
        assert any(q.status == "failed" for q in report.queries)


def test_order_and_original_byte_retention_are_explicit(tmp_path: Path) -> None:
    files = generate(tmp_path)
    base, other = files["events.ndjson"], files["reordered.ndjson"]
    req = request(queries=False)
    assert verify(base, other, req).status == "passed"
    ordered = req.model_copy(update={"limits": IntegrityOptions(order_required=True)})
    assert "record_order_changed" in {c.reason for c in verify(base, other, ordered).checks}
    bytewise = req.model_copy(update={"limits": IntegrityOptions(original_bytes_required=True)})
    assert verify(base, files["events.ndjson.gz"], bytewise).status == "failed"
    assert verify(base, base, bytewise).status == "passed"


def test_nested_mixed_missing_preserved_or_excluded(tmp_path: Path) -> None:
    path = tmp_path / "nested.ndjson"
    text = (
        '{"id":"0001","x":{"a":[1,null,{"b":1.2300}]},"mixed":1}\n'
        '{"id":"0001","x":{"a":[1,null,{"b":1.2300}]},"mixed":"1","v":null}\n'
    )
    path.write_text(text)
    compressed = tmp_path / "nested.gz"
    compressed.write_bytes(gzip.compress(text.encode()))
    req = VerificationRequest(
        baseline=ProfileOptions(format="ndjson"), candidate=ProfileOptions(format="ndjson")
    )
    report = verify(path, compressed, req)
    assert report.status == "passed"
    assert report.workload_status == "not_checked" and report.workload_reason == "missing_workload"
    assert report.capabilities["ndjson"].supported
    assert not report.capabilities["parquet"].supported
    assert set(report.capabilities["parquet"].reasons) == {
        "missing_fields_require_presence_encoding",
        "mixed_types_require_tagged_encoding",
        "nested_conversion_requires_explicit_schema",
    }
    req = req.model_copy(update={"workload": Workload(queries=(Query(id="q", kind="full_scan"),))})
    incomplete = verify(path, compressed, req)
    assert incomplete.status == "not_checked"
    assert incomplete.queries[0].reason == "unsupported_workload_semantics"
    compressed.write_bytes(gzip.compress(text.replace('"b":1.2300', '"b":1.2301', 1).encode()))
    assert verify(path, compressed, req).status == "failed"


def test_canonical_encoding_is_exact_and_type_distinct() -> None:
    values = [
        None,
        True,
        1,
        Decimal("1.0"),
        Decimal("1.00"),
        1.0,
        "1",
        b"1",
        {"x": None},
        {},
        [1, 2],
        [2, 1],
        {"x": [1]},
        {"x": "[1]"},
        -0.0,
        0.0,
    ]
    assert len({encode(v) for v in values}) == len(values)
    assert encode({"a": 1, "b": 2}) == encode({"b": 2, "a": 1})
    a = datetime(2026, 1, 1, tzinfo=UTC)
    b = a.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert encode(a) == encode(b)
    assert encode(a) != encode(a.replace(tzinfo=None))
    with localcontext() as context:
        context.prec = 2
        assert encode(Decimal("1234567890.12345678901234567890")) != encode(
            Decimal("1234567890.12")
        )
    with pytest.raises(ProfileError):
        encode(float("nan"))
    with pytest.raises(ProfileError):
        encode(Decimal("Infinity"))


def test_timestamp_awareness_and_equivalent_instants(tmp_path: Path) -> None:
    files = generate(tmp_path)
    path = tmp_path / "offset.ndjson"
    original = files["events.ndjson"].read_text()
    path.write_text(original.replace("T00:00:00Z", "T05:30:00+05:30"))
    assert verify(files["events.ndjson"], path, request()).status == "passed"
    path.write_text(original.replace("T00:00:00Z", "T00:00:00"))
    assert verify(files["events.ndjson"], path, request()).status == "failed"


def test_parquet_declared_schema_changes_are_detected(tmp_path: Path) -> None:
    files = generate(tmp_path)
    table = pq.read_table(files["events.parquet"])
    fields = [
        pa.field(f.name, pa.decimal128(12, 2) if f.name == "amount" else f.type)
        for f in table.schema
    ]
    target = tmp_path / "different.parquet"
    pq.write_table(table.cast(pa.schema(fields)), target)
    report = verify(files["events.parquet"], target, request("parquet", "parquet", False))
    assert report.status == "failed"
    assert "declared_parquet_schema_changed" in {c.reason for c in report.checks}


def test_parquet_schema_metadata_is_compared_in_full(tmp_path: Path) -> None:
    left, right = tmp_path / "left.parquet", tmp_path / "right.parquet"
    table = pa.Table.from_pylist([{"id": "0001"}])
    pq.write_table(table.replace_schema_metadata({b"annotation": b"x" * 1000 + b"a"}), left)
    pq.write_table(table.replace_schema_metadata({b"annotation": b"x" * 1000 + b"b"}), right)
    report = verify(left, right, request("parquet", "parquet", False))
    assert report.status == "failed"
    assert "declared_parquet_schema_changed" in {c.reason for c in report.checks}


def test_empty_objects_need_an_explicit_tabular_encoding(tmp_path: Path) -> None:
    path = tmp_path / "empty-objects.ndjson"
    path.write_text("{}\n{}\n")
    opts = ProfileOptions(format="ndjson")
    report = verify(path, path, VerificationRequest(baseline=opts, candidate=opts))
    assert report.status == "passed"
    assert report.baseline.row_count == 2
    assert not report.capabilities["parquet"].supported
    assert not report.capabilities["workload"].supported
    assert not report.capabilities["csv"].supported
    assert report.capabilities["ndjson"].supported


@pytest.mark.parametrize(
    "limits,reason",
    [
        (IntegrityOptions(max_rows=2), "integrity_row_quota"),
        (IntegrityOptions(max_spill_bytes=32768), "integrity_spill_quota"),
    ],
)
def test_real_input_quotas_fail_closed(
    limits: IntegrityOptions, reason: str, tmp_path: Path
) -> None:
    path = tmp_path / "rows.ndjson"
    path.write_text("\n".join(json.dumps({"id": i, "data": str(i) * 3000}) for i in range(100)))
    opts = ProfileOptions(format="ndjson")
    report = verify(path, path, VerificationRequest(baseline=opts, candidate=opts, limits=limits))
    assert report.status == "failed"
    assert report.checks[-1].reason == reason


def test_missing_invalid_and_large_result_evidence(tmp_path: Path) -> None:
    files = generate(tmp_path)
    req = request(queries=False)
    report = verify(files["events.ndjson"], files["events.ndjson"], req)
    assert report.status == "passed" and report.workload_status == "not_checked"
    assert report.performance_status == "not_measured"
    req = req.model_copy(
        update={
            "workload": Workload(
                queries=(Query(id="unknown", kind="projection", columns=("not_present",)),)
            )
        }
    )
    assert verify(files["events.ndjson"], files["events.ndjson"], req).status == "not_checked"
    req = request().model_copy(update={"limits": IntegrityOptions(max_result_rows=1)})
    report = verify(files["events.ndjson"], files["events.ndjson"], req)
    assert report.status == "not_checked"
    assert all(q.reason == "workload_result_row_quota" for q in report.queries)
    empty = tmp_path / "empty.ndjson"
    empty.write_text("")
    assert verify(empty, empty, request()).status == "failed"


def test_sampled_data_never_proves_full_integrity(tmp_path: Path) -> None:
    files = generate(tmp_path)
    req = request().model_copy(
        update={"baseline": options("ndjson").model_copy(update={"sample_rows_per_stratum": 1})}
    )
    report = verify(files["events.ndjson"], files["events.ndjson"], req)
    assert report.status == "failed" and report.checks[-1].reason == "integrity_requires_full_scan"


def test_subprocess_evidence_persistence_and_tamper_rejection(tmp_path: Path) -> None:
    files = generate(tmp_path / "data")
    baseline, candidate = files["events.csv"], files["events.parquet"]
    report = verify_files(baseline, candidate, request("csv", "parquet"))
    assert report.status == "passed"
    assert report.engine_versions["duckdb"]
    destination = tmp_path / "evidence.json"
    write_evidence(destination, report, (baseline, candidate))
    assert read_evidence(destination) == report
    text = destination.read_text()
    assert "0001" not in text and str(baseline) not in text and "2026-01" not in text
    with pytest.raises(ProfileError, match="output_must_preserve_source"):
        write_evidence(baseline, report, (baseline, candidate))
    link = tmp_path / "hardlink"
    os.link(baseline, link)
    with pytest.raises(ProfileError, match="output_must_preserve_source"):
        write_evidence(link, report, (baseline,))
    destination.write_text(text.replace('"row_count": 3', '"row_count": 4', 1))
    with pytest.raises(ProfileError, match="invalid_integrity_evidence"):
        read_evidence(destination)
    data = report.model_dump()
    data["checks"] = data["checks"][:1]
    with pytest.raises(ValueError):
        IntegrityReport.model_validate(data)


def test_worker_timeout_never_returns_a_pass(tmp_path: Path) -> None:
    files = generate(tmp_path)
    scratch: list[Path] = []

    def timeout(command: list[str], **kwargs: object) -> None:
        parent = Path(command[-1]).parent
        scratch.append(parent)
        nested = parent / "data-optimizer-content-test"
        nested.mkdir()
        (nested / "raw-content.sqlite").write_bytes(b"SYNTHETIC_PRIVATE_ROWS")
        raise subprocess.TimeoutExpired("worker", 1)

    with patch(
        "data_optimizer.integrity.service.subprocess.run",
        side_effect=timeout,
    ):
        with pytest.raises(ProfileError, match="integrity_time_quota"):
            verify_files(files["events.ndjson"], files["events.ndjson"], request())
    assert scratch and all(not path.exists() for path in scratch)


def test_ordered_workload_results_compare_in_total_order(tmp_path: Path) -> None:
    files = generate(tmp_path)
    query = Query(
        id="ordered", kind="projection", columns=("id", "amount"), order_by=("id", "amount")
    )
    req = request().model_copy(update={"workload": Workload(queries=(query,))})
    report = verify(files["events.ndjson"], files["reordered.ndjson"], req)
    assert report.status == "passed"
    assert report.queries[0].ordered


def test_public_verifier_retains_real_quota_failure_evidence(tmp_path: Path) -> None:
    files = generate(tmp_path)
    req = request().model_copy(update={"limits": IntegrityOptions(max_rows=2)})
    report = verify_files(files["events.ndjson"], files["events.ndjson"], req)
    assert report.status == "failed"
    assert report.checks[-1].reason == "integrity_row_quota"


def test_float_query_tolerance_cannot_mask_content_corruption(tmp_path: Path) -> None:
    left, right = tmp_path / "left.parquet", tmp_path / "right.parquet"
    pq.write_table(pa.Table.from_pylist([{"x": 1.0}]), left)
    pq.write_table(pa.Table.from_pylist([{"x": 1.00001}]), right)
    query = Query.model_validate(
        {"id": "q", "kind": "projection", "columns": ["x"], "tolerance": {"absolute": "0.001"}}
    )
    opts = ProfileOptions(format="parquet")
    req = VerificationRequest(baseline=opts, candidate=opts, workload=Workload(queries=(query,)))
    report = verify(left, right, req)
    assert report.status == "failed" and report.queries[0].status == "passed"
    assert report.queries[0].tolerance.absolute == Decimal("0.001")


def test_capabilities_exclude_large_integers_and_opaque_parquet_values(tmp_path: Path) -> None:
    big = tmp_path / "big.ndjson"
    big.write_text(json.dumps({"id": 2**80}) + "\n")
    opts = ProfileOptions(format="ndjson")
    report = verify(big, big, VerificationRequest(baseline=opts, candidate=opts))
    assert report.status == "passed"
    assert "integer_exceeds_int64" in report.capabilities["parquet"].reasons
    assert not report.capabilities["workload"].supported
    path = tmp_path / "nested.parquet"
    pq.write_table(pa.Table.from_pylist([{"nested": {"binary": b"secret"}}]), path)
    opts = ProfileOptions(format="parquet")
    report = verify(path, path, VerificationRequest(baseline=opts, candidate=opts))
    assert report.status == "passed"
    assert "nested_ndjson_requires_encoding_contract" in report.capabilities["ndjson"].reasons


def test_engine_date_sentinels_are_not_silently_queried(tmp_path: Path) -> None:
    path = tmp_path / "sentinel.ndjson"
    path.write_text('{"time":"0001-01-01T00:00:00"}\n')
    opts = ProfileOptions(format="ndjson", schema_overrides={"time": "timestamp"})
    req = VerificationRequest(
        baseline=opts, candidate=opts, workload=Workload(queries=(Query(id="q", kind="full_scan"),))
    )
    report = verify(path, path, req)
    assert report.status == "not_checked"
    assert report.queries[0].reason == "workload_timestamp_sentinel_unsupported"


def test_cli_success_and_rejection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = generate(tmp_path / "fixtures")
    req = tmp_path / "request.json"
    req.write_text(request().model_dump_json())
    out = tmp_path / "evidence.json"
    arguments = [
        "integrity-check",
        str(files["events.ndjson"]),
        str(files["reordered.ndjson"]),
        "--request",
        str(req),
        "--output",
        str(out),
    ]
    main(arguments)
    assert "Integrity passed; performance not measured" in capsys.readouterr().out
    assert read_evidence(out).status == "passed"
    arguments[2] = str(files["duplicates.ndjson"])
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 1
    assert read_evidence(out).status == "failed"
