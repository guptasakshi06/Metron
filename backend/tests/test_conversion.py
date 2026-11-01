"""Actual local conversion/integrity round trips and publication recovery boundaries."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from data_optimizer.candidates.generator import context
from data_optimizer.candidates.models import CandidateConfig, ConversionRequest
from data_optimizer.conversion.service import convert, list_candidates, read_manifest
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import ProfileOptions, fingerprint
from data_optimizer.readers.stream import ProfileError
from data_optimizer.workloads.models import Workload

REPO = Path(__file__).resolve().parents[2]


def request(**updates: object) -> ConversionRequest:
    raw = json.loads((REPO / "examples/s05-conversion-request.json").read_text())
    raw.update(updates)
    return ConversionRequest.model_validate(raw)


def config(**updates: object) -> CandidateConfig:
    raw = CandidateConfig(
        format="parquet", codec="zstd", compression_level=3, context=context()
    ).model_dump()
    raw.update(updates)
    return CandidateConfig.model_validate(raw)


@pytest.fixture
def event(tmp_path: Path) -> Path:
    path = tmp_path / "source.ndjson"
    path.write_bytes((REPO / "examples/s04-events.ndjson").read_bytes())
    return path


def test_primary_matrix_has_baseline_and_three_verified_alternatives(
    event: Path, tmp_path: Path
) -> None:
    req = request()
    before = event.read_bytes()
    listed = list_candidates(event, req)
    assert listed == list_candidates(event, req)
    assert len(listed.candidates) <= req.max_candidates
    manifests = []
    for candidate in listed.candidates:
        out = convert(event, tmp_path / "artifacts", req, candidate.configuration)
        if out.status == "excluded":
            assert out.reasons == ("partition_small_file_amplification",)
            continue
        assert out.status == "validated", out.reasons
        assert out.manifest is not None and out.artifact_prefix is not None
        m = out.manifest
        manifests.append(m)
        assert m.integrity.status == "passed"
        assert m.integrity.workload_status == "passed"
        assert all(q.status == "passed" for q in m.integrity.queries)
        assert m.physical_bytes == sum(
            (Path(out.artifact_prefix) / a.path).stat().st_size for a in m.artifacts
        )
        assert m.conversion_seconds > 0 and m.cpu_seconds > 0 and m.peak_rss_kib > 0
        assert m.performance_status == "not_measured"
    assert {(m.configuration.format, m.configuration.codec) for m in manifests} >= {
        ("ndjson", "original"),
        ("ndjson", "gzip"),
        ("parquet", "snappy"),
        ("parquet", "zstd"),
    }
    assert event.read_bytes() == before
    assert not list((tmp_path / "artifacts").rglob(".partial-*"))


def test_hash_covers_configuration_and_context() -> None:
    c = config()
    changes = [
        dict(codec="snappy"),
        dict(compression_level=9),
        dict(row_group_rows=7),
        dict(target_file_bytes=4096),
        dict(partition_by=("category",)),
        dict(sort_by=("timestamp",)),
        dict(format="ndjson"),
        dict(baseline=True),
        dict(context=context().model_copy(update={"engine_versions": {"pyarrow": "other"}})),
    ]
    assert all(c.fingerprint != c.model_copy(update=v).fingerprint for v in changes)
    assert c.fingerprint == CandidateConfig.model_validate_json(c.model_dump_json()).fingerprint


def test_verified_reuse_and_corruption_refused(event: Path, tmp_path: Path) -> None:
    req, c = request(), config()
    first = convert(event, tmp_path / "store", req, c)
    assert first.manifest and first.artifact_prefix
    m = first.manifest
    artifact = Path(first.artifact_prefix) / m.artifacts[0].path
    stamp = artifact.stat().st_mtime_ns
    reused = convert(event, tmp_path / "store", req, c)
    assert reused.status == "reused" and reused.manifest == m
    assert artifact.stat().st_mtime_ns == stamp
    artifact.write_bytes(b"corrupted")
    with pytest.raises(ProfileError, match="invalid_conversion_manifest"):
        convert(event, tmp_path / "store", req, c)
    assert event.read_bytes() == (REPO / "examples/s04-events.ndjson").read_bytes()


def test_changed_inputs_and_requirements_do_not_reuse(event: Path, tmp_path: Path) -> None:
    first = convert(event, tmp_path / "store", request(), config())
    event.write_bytes(event.read_bytes() * 2)
    second = convert(event, tmp_path / "store", request(), config())
    third = convert(event, tmp_path / "store", request(workload={}), config())
    assert first.status == second.status == third.status == "validated"
    assert len({first.artifact_prefix, second.artifact_prefix, third.artifact_prefix}) == 3


def test_recovery_removes_orphaned_partial_only(event: Path, tmp_path: Path) -> None:
    req, c = request(), config()
    key = fingerprint(
        {
            "input": input_digest(event, req.source.max_raw_bytes),
            "request": req.model_dump(mode="json"),
            "configuration": c.model_dump(mode="json"),
        }
    )
    prefix = tmp_path / str(req.tenant_id) / "assessments" / str(req.assessment_id)
    partial = prefix / (".partial-" + key)
    partial.mkdir(parents=True)
    (partial / "truncated.parquet").write_bytes(b"PAR1")
    unrelated = prefix / ".partial-unrelated"
    unrelated.mkdir()
    (unrelated / "marker").touch()
    out = convert(event, tmp_path, req, c)
    assert out.status == "validated" and not partial.exists()
    assert (unrelated / "marker").exists()


def test_actual_worker_cancellation_cleans_unpublished_files(event: Path, tmp_path: Path) -> None:
    deadline = time.monotonic() + 0.15
    out = convert(
        event,
        tmp_path / "store",
        request(),
        config(),
        cancelled=lambda: time.monotonic() >= deadline,
    )
    assert out.status == "cancelled"
    assert not list((tmp_path / "store").rglob("manifest.json"))
    assert not list((tmp_path / "store").rglob(".partial-*"))
    assert event.read_bytes() == (REPO / "examples/s04-events.ndjson").read_bytes()
    assert convert(event, tmp_path / "store", request(), config()).status == "validated"


def test_same_request_concurrently_publishes_one_copy(event: Path, tmp_path: Path) -> None:
    req, c = request(), config()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(convert, event, tmp_path / "store", req, c) for _ in range(2)]
        results = [f.result() for f in futures]
    assert sorted(o.status for o in results) == ["reused", "validated"]
    assert len(list((tmp_path / "store").rglob("manifest.json"))) == 1


@pytest.mark.parametrize(
    "data,reason",
    [
        ('{"a":1}\n{"a":2,"b":null}\n', "missing_fields_require_presence_encoding"),
        ('{"a":1}\n{"a":"1"}\n', "mixed_types_require_tagged_encoding"),
        ('{"a":{"nested":[1,null]}}\n', "nested_conversion_requires_explicit_schema"),
        ('{"a":1.2}\n{"a":1.20}\n', "varying_decimal_scale_requires_encoding"),
    ],
)
def test_unsupported_parquet_has_explicit_exclusion(data: str, reason: str, tmp_path: Path) -> None:
    path = tmp_path / "input.ndjson"
    path.write_text(data)
    req = request(source={"format": "ndjson"}, workload={})
    before = path.read_bytes()
    listed = list_candidates(path, req)
    assert reason in next(c.reasons for c in listed.candidates if c.configuration.codec == "snappy")
    rejected = convert(path, tmp_path / "store", req, config())
    assert rejected.status == "excluded" and reason in rejected.reasons
    gzip = convert(
        path, tmp_path / "store", req, config(format="ndjson", codec="gzip", compression_level=6)
    )
    assert gzip.status == "validated", gzip.reasons
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"codec": "brotli"}, "unsupported_format_codec_or_level"),
        ({"sort_by": ("unknown",)}, "unknown_layout_column"),
        (
            {"context": context().model_copy(update={"engine_versions": {"pyarrow": "old"}})},
            "execution_context_mismatch",
        ),
    ],
)
def test_invalid_config_excluded(
    event: Path, tmp_path: Path, changes: dict[str, object], reason: str
) -> None:
    out = convert(event, tmp_path / "store", request(), config(**changes))
    assert out.status == "excluded" and reason in out.reasons
    assert not list((tmp_path / "store").rglob("manifest.json"))


def test_byte_and_order_requirements(event: Path, tmp_path: Path) -> None:
    req = request(limits={"original_bytes_required": True})
    assert convert(event, tmp_path / "store", req, config()).reasons == (
        "original_byte_retention_required",
    )
    base = config(baseline=True, format="ndjson", codec="original", compression_level=None)
    assert convert(event, tmp_path / "store", req, base).status == "validated"
    req = request(limits={"order_required": True})
    assert (
        "layout_conflicts_with_record_order"
        in convert(event, tmp_path / "store", req, config(sort_by=("category",))).reasons
    )
    assert convert(event, tmp_path / "store", req, config()).status == "validated"


def test_partitioned_multifile_outputs_are_all_validated(tmp_path: Path) -> None:
    path = tmp_path / "events.ndjson"
    path.write_text(
        "".join(
            json.dumps({"category": str(i % 2), "n": i, "payload": "x" * 100}) + "\n"
            for i in range(40)
        )
    )
    req = request(source={"format": "ndjson"}, workload={}, min_partition_rows=2)
    out = convert(
        path,
        tmp_path / "store",
        req,
        config(partition_by=("category",), target_file_bytes=1024, row_group_rows=4),
    )
    assert out.status == "validated", out.reasons
    assert out.manifest and out.artifact_prefix
    m = out.manifest
    assert m.partition_count == 2 and m.file_count > 2
    assert m.integrity.baseline and m.integrity.candidate
    assert m.integrity.baseline.row_count == m.integrity.candidate.row_count == 40
    assert read_manifest(Path(out.artifact_prefix)) == m
    assert not (Path(out.artifact_prefix) / ".combined").exists()
    for a in m.artifacts:
        p = pq.ParquetFile(Path(out.artifact_prefix) / a.path)
        assert "category" in p.schema_arrow.names  # partition fields retained
        assert all(p.metadata.row_group(i).num_rows <= 4 for i in range(p.metadata.num_row_groups))


def test_partition_and_file_quotas(tmp_path: Path) -> None:
    path = tmp_path / "events.ndjson"
    path.write_text(
        "".join(json.dumps({"category": str(i), "s": "x" * 600}) + "\n" for i in range(10))
    )
    req = request(source={"format": "ndjson"}, workload={}, max_partitions=2, min_partition_rows=1)
    out = convert(path, tmp_path / "store", req, config(partition_by=("category",)))
    assert out.status == "excluded" and out.reasons == ("partition_count_quota",)
    req = request(source={"format": "ndjson"}, workload={}, max_files=1)
    out = convert(path, tmp_path / "store", req, config(target_file_bytes=1024))
    assert out.reasons == ("conversion_file_count_quota",)
    assert not list((tmp_path / "store").rglob(".partial-*"))


def test_csv_roundtrip_and_already_optimized_parquet(tmp_path: Path) -> None:
    csv = tmp_path / "input.csv"
    csv.write_text("id,amount\n0001,1.20\n0001,1.20\n0002,2.30\n")
    req = request(source={"format": "csv", "schema_overrides": {"amount": "decimal"}}, workload={})
    for c in (
        config(),
        config(codec="snappy", compression_level=None),
        config(format="ndjson", codec="gzip", compression_level=6),
    ):
        out = convert(csv, tmp_path / "store", req, c)
        assert out.status == "validated", out.reasons
    parquet = tmp_path / "optimized.parquet"
    schema = pa.schema(
        [pa.field("id", pa.string()), pa.field("amount", pa.decimal128(12, 2))],
        metadata={b"contract": b"preserve me"},
    )
    table = pa.Table.from_pylist([{"id": "0001", "amount": Decimal("1.20")}] * 2, schema=schema)
    pq.write_table(table, parquet, compression="zstd")
    before = parquet.read_bytes()
    req = request(source={"format": "parquet"}, workload={})
    out = convert(parquet, tmp_path / "store", req, config())
    assert out.status == "validated" and out.manifest
    assert any(
        c.name == "declared_parquet_schema" and c.status == "passed"
        for c in out.manifest.integrity.checks
    )
    assert parquet.read_bytes() == before


def test_failed_integrity_never_publishes(tmp_path: Path) -> None:
    path = tmp_path / "negative-zero.ndjson"
    path.write_text('{"value":-0.00}\n')
    # Arrow decimal cannot retain a negative zero; exact canonical integrity rejects it.
    out = convert(
        path, tmp_path / "store", request(source={"format": "ndjson"}, workload={}), config()
    )
    assert out.status == "failed" and "integrity_failed" in out.reasons
    assert not list((tmp_path / "store").rglob("manifest.json"))
    assert path.read_text() == '{"value":-0.00}\n'


def test_missing_workload_is_not_a_performance_claim(event: Path, tmp_path: Path) -> None:
    out = convert(event, tmp_path / "store", request(workload={}), config())
    assert out.status == "validated" and out.manifest
    assert out.manifest.integrity.workload_status == "not_checked"
    assert out.manifest.integrity.workload_reason == "missing_workload"


def test_schema_and_budget_validation() -> None:
    with pytest.raises(ValidationError):
        request(source=ProfileOptions(format="ndjson", sample_rows_per_stratum=1).model_dump())
    with pytest.raises(ValidationError):
        config(partition_by=("../../source",))
    with pytest.raises(ValidationError):
        request(max_candidates=100)
    assert request().tenant_id == UUID("10000000-0000-0000-0000-000000000001")
    assert Workload().queries == ()
