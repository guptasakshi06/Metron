from __future__ import annotations

import json
import socket
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from data_optimizer.cli import main
from data_optimizer.profiling.engine import profile
from data_optimizer.profiling.models import (
    ProfileOptions,
    ProfileReport,
    validate_report,
)
from data_optimizer.profiling.service import profile_file, read_report, write_report
from data_optimizer.readers.stream import Budget, ProfileError, canonical, rows
from fixtures.profiling import generate


@pytest.fixture
def fixtures(tmp_path: Path) -> dict[str, Path]:
    return generate(tmp_path / "fixtures")


def test_csv_is_text_and_overrides_are_explicit(fixtures: dict[str, Path]) -> None:
    path = fixtures["csv"]
    defaults = ProfileOptions(format="csv", include_field_names=True)
    raw_rows = list(rows(path, defaults, Budget(defaults.max_decoded_bytes)))
    assert raw_rows[0]["id"] == "0001"
    assert raw_rows[0]["optional"] == ""
    assert raw_rows[2]["optional"] == "NULL"
    options = defaults.model_copy(
        update={
            "schema_overrides": {"amount": "decimal", "timestamp": "timestamp"},
            "csv_null_tokens": ("NULL",),
        }
    )
    typed = list(rows(path, options, Budget(options.max_decoded_bytes)))
    assert typed[2]["amount"] == Decimal("0.00000000000000000001")
    report = profile_file(path, options)
    columns = {c.field: c for c in report.columns}
    assert report.row_count == 3  # duplicate observations retained
    assert columns["id"].cardinality.value == 2
    assert columns["timestamp"].temporal_span_seconds == 86400
    assert columns["optional"].nulls == 1
    assert columns["optional"].missing == 0
    assert columns["id"].schema_types == ("string",)


def test_json_missing_precision_nested_and_drift(fixtures: dict[str, Path]) -> None:
    options = ProfileOptions(format="ndjson", include_field_names=True)
    first = next(rows(fixtures["ndjson"], options, Budget(options.max_decoded_bytes)))
    assert first["amount"] == Decimal("123456789012345678.123456789012345678")
    report = profile_file(fixtures["ndjson"], options)
    columns = {c.field: c for c in report.columns}
    assert report.row_count == 121
    assert columns["optional"].missing == 61
    assert columns["optional"].nulls == 60
    assert columns["nested"].schema_types == ("object",)
    assert columns["drift"].schema_types == ("integer", "string")
    assert "mixed_types_require_schema_review" in report.warnings
    assert "nested_values_are_opaque" in report.warnings


@pytest.mark.parametrize("fmt", ["csv", "ndjson", "parquet", "gzip"])
def test_repeatable_and_no_raw_values(fixtures: dict[str, Path], fmt: str) -> None:
    options = ProfileOptions(format="ndjson" if fmt == "gzip" else fmt)
    one = profile_file(fixtures[fmt], options)
    two = profile_file(fixtures[fmt], options)
    assert one == two
    assert validate_report(one.model_dump_json().encode()) == one
    assert all(c.field == f"column_{i + 1}" for i, c in enumerate(one.columns))
    exported = one.model_dump_json()
    assert "SYNTHETIC_SECRET" not in exported
    assert "123456789012345678" not in exported
    assert "2026-01" not in exported
    assert str(fixtures[fmt]) not in exported
    assert 'id"' not in exported
    assert one.engine_versions["pyarrow"]
    if fmt == "parquet":
        assert one.row_count == 3
        assert any(c.schema_types == ("decimal",) for c in one.columns)
        assert any(c.schema_types == ("timestamp_aware",) for c in one.columns)


def test_sampling_covers_time_source_and_is_seeded(fixtures: dict[str, Path]) -> None:
    options = ProfileOptions(
        format="ndjson",
        schema_overrides={"timestamp": "timestamp"},
        sample_rows_per_stratum=3,
        source_column="source",
        time_column="timestamp",
        seed=42,
    )
    first = profile_file(fixtures["ndjson"], options)
    assert first == profile_file(fixtures["ndjson"], options)
    assert len(first.coverage) == 6
    assert all(c.profiled_rows == 3 for c in first.coverage)
    assert first.profiled_rows == 18
    assert first.row_count == 121
    assert first.sample_fraction == 18 / 121
    assert first.strata_by == ("time_day", "source")
    other = profile_file(fixtures["ndjson"], options.model_copy(update={"seed": 43}))
    assert first.profile_fingerprint != other.profile_fingerprint
    assert first.columns != other.columns


def test_sensitive_fields_do_not_expose_width_cardinality_or_names(
    fixtures: dict[str, Path],
) -> None:
    options = ProfileOptions(format="ndjson", redacted_fields=("text",), include_field_names=True)
    report = profile_file(fixtures["ndjson"], options)
    column = next(c for c in report.columns if c.sensitive)
    assert column.field.startswith("column_")
    assert column.widths is column.cardinality is column.temporal_span_seconds is None
    assert "SYNTHETIC_SECRET" not in report.model_dump_json()


def test_cache_requires_input_and_settings_and_engine_match(
    fixtures: dict[str, Path],
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    path = fixtures["csv"]
    options = ProfileOptions(format="csv")
    first = profile_file(path, options, cache)
    with patch(
        "data_optimizer.profiling.service.subprocess.run", side_effect=AssertionError("rerun")
    ):
        assert profile_file(path, options, cache) == first
    second = profile_file(path, options.model_copy(update={"seed": 1}), cache)
    assert first.settings_fingerprint != second.settings_fingerprint
    path.write_text(path.read_text() + "0003,1,2026-01-03T00:00:00+00:00,\n")
    third = profile_file(path, options, cache)
    assert third.row_count == 4
    assert len(list(cache.glob("*.json"))) == 3
    cached = next(cache.glob("*.json"))
    cached.write_text('{"raw":"secret"}')
    with pytest.raises(ProfileError, match="invalid_metadata_report"):
        read_report(cached)


@pytest.mark.parametrize(
    "data,code",
    [
        ('{"x":1,"x":2}\n', "duplicate_json_key"),
        ('{"x":NaN}\n', "nonfinite_number_unsupported"),
        ("[]\n", "json_object_required"),
        ("{bad}\n", "invalid_structure_or_unsupported_type"),
        ("", "empty_dataset"),
    ],
)
def test_invalid_inputs_are_sanitized(tmp_path: Path, data: str, code: str) -> None:
    source = tmp_path / "bad.ndjson"
    source.write_text(data)
    with pytest.raises(ProfileError, match=code):
        profile_file(source, ProfileOptions(format="ndjson"))


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"max_raw_bytes": 10}, "raw_byte_quota"),
        ({"max_decoded_bytes": 100}, "decoded_byte_quota"),
        ({"max_record_bytes": 64}, "record_byte_quota"),
        ({"max_columns": 2}, "column_quota"),
        ({"max_strata": 1, "source_column": "source"}, "strata_quota"),
        ({"schema_overrides": {"id": "boolean"}}, "schema_override_mismatch"),
        ({"time_column": "timestamp"}, "time_column_requires_timestamp_override"),
        ({"schema_overrides": {"not_a_field": "string"}}, "unknown_configured_field"),
    ],
)
def test_quotas_and_unsupported_settings(
    fixtures: dict[str, Path], changes: dict, code: str
) -> None:
    options = ProfileOptions.model_validate({"format": "ndjson", **changes})
    with pytest.raises(ProfileError, match=code):
        profile_file(fixtures["ndjson"], options)


def test_cardinality_is_bounded_and_labeled(fixtures: dict[str, Path]) -> None:
    report = profile_file(
        fixtures["ndjson"],
        ProfileOptions(
            format="ndjson",
            cardinality_capacity=16,
            include_field_names=True,
        ),
    )
    columns = {c.field: c for c in report.columns}
    assert columns["text"].cardinality.method == "kmv_estimate"
    assert columns["text"].cardinality.value <= report.row_count
    assert columns["category"].cardinality.method == "exact"
    assert columns["category"].cardinality.value == 3


def test_mixed_timestamp_awareness_has_no_false_span(tmp_path: Path) -> None:
    source = tmp_path / "timestamps.ndjson"
    source.write_text('{"t":"2026-01-01T00:00:00"}\n{"t":"2026-01-01T00:00:00+05:30"}\n')
    report = profile_file(
        source, ProfileOptions(format="ndjson", schema_overrides={"t": "timestamp"})
    )
    assert report.columns[0].temporal_span_seconds is None
    assert "timestamps_have_mixed_awareness" in report.warnings


def test_report_import_rejects_inconsistent_or_tampered_metadata(fixtures: dict[str, Path]) -> None:
    report = profile_file(fixtures["csv"], ProfileOptions(format="csv"))
    data = report.model_dump(mode="json")
    data["row_count"] = 1
    with pytest.raises(ValueError):
        validate_report(json.dumps(data).encode())
    data = report.model_dump(mode="json")
    data["seed"] = 42
    with pytest.raises(ValueError, match="fingerprint"):
        validate_report(json.dumps(data).encode())
    data["raw_records"] = [{"private": "secret"}]
    with pytest.raises(ValidationError):
        ProfileReport.model_validate(data)


def test_local_cli_export_review_import_never_calls_network(
    fixtures: dict[str, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "report.json"
    with (
        patch.object(socket, "create_connection", side_effect=AssertionError("network")),
        patch("httpx.post", side_effect=AssertionError("network")),
    ):
        main(["profile", str(fixtures["csv"]), "--format", "csv", "--output", str(output)])
        main(["profile-review", str(output)])
        main(["profile-import", str(output), "--store", str(tmp_path / "imported")])
    report = read_report(output)
    assert read_report(tmp_path / "imported" / f"{report.profile_fingerprint}.json") == report
    assert "no network transfer" in capsys.readouterr().out
    with patch("httpx.post", side_effect=AssertionError("network")), pytest.raises(SystemExit):
        main(["profile-import", str(output), "--api-url", "http://127.0.0.1:8000"])
    assert "matching_review_fingerprint" in capsys.readouterr().err


def test_output_cannot_replace_original(fixtures: dict[str, Path]) -> None:
    original = fixtures["csv"].read_bytes()
    with pytest.raises(SystemExit):
        main(["profile", str(fixtures["csv"]), "--format", "csv", "--output", str(fixtures["csv"])])
    assert fixtures["csv"].read_bytes() == original


def test_input_change_is_detected(fixtures: dict[str, Path]) -> None:
    from data_optimizer.profiling import engine

    original = engine.rows
    calls = 0

    def mutate(path: Path, options: ProfileOptions, budget: Budget):
        nonlocal calls
        calls += 1
        yield from original(path, options, budget)
        if calls == 1:
            path.write_text(path.read_text().replace("0002", "0009"))

    with patch.object(engine, "rows", mutate), pytest.raises(ProfileError, match="input_changed"):
        profile(fixtures["csv"], ProfileOptions(format="csv"))


def test_nested_canonical_boundaries() -> None:
    assert canonical({"a": {"b": 1}, "c": 2}) != canonical({"a": {"b": 1, "c": 2}})


def test_report_file_size_bound(tmp_path: Path) -> None:
    huge = tmp_path / "huge.json"
    huge.write_bytes(b" " * 2_097_153)
    with pytest.raises(ProfileError, match="report_byte_quota"):
        read_report(huge)


def test_gzip_and_plain_have_equivalent_logical_profiles(fixtures: dict[str, Path]) -> None:
    options = ProfileOptions(format="ndjson")
    plain = profile_file(fixtures["ndjson"], options)
    zipped = profile_file(fixtures["gzip"], options)
    assert plain.schema_fingerprint == zipped.schema_fingerprint
    assert plain.row_count == zipped.row_count
    assert plain.columns == zipped.columns
    assert plain.row_widths == zipped.row_widths
    assert zipped.physical_bytes < plain.physical_bytes


def test_submicrosecond_timestamps_are_rejected_without_truncation(tmp_path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    parquet = tmp_path / "ns.parquet"
    pq.write_table(pa.table({"t": pa.array([1, 2], pa.timestamp("ns", "UTC"))}), parquet)
    with pytest.raises(ProfileError, match="parquet_precision_or_type_unsupported"):
        profile_file(parquet, ProfileOptions(format="parquet"))
    text = tmp_path / "ns.ndjson"
    text.write_text('{"t":"2026-01-01T00:00:00.000000001+00:00"}\n')
    with pytest.raises(ProfileError, match="timestamp_precision_unsupported"):
        profile_file(text, ProfileOptions(format="ndjson", schema_overrides={"t": "timestamp"}))


def test_worker_timeout_is_a_quota_failure(fixtures: dict[str, Path]) -> None:
    import subprocess

    with patch(
        "data_optimizer.profiling.service.subprocess.run",
        side_effect=subprocess.TimeoutExpired("worker", 1),
    ):
        with pytest.raises(ProfileError, match="profile_time_quota"):
            profile_file(fixtures["csv"], ProfileOptions(format="csv"))


def test_low_memory_worker_is_a_quota_failure(fixtures: dict[str, Path]) -> None:
    with pytest.raises(ProfileError, match="profile_(memory|resource)_quota"):
        profile_file(fixtures["ndjson"], ProfileOptions(format="ndjson", memory_mib=128))


def test_cli_import_connection_failure_is_sanitized(
    fixtures: dict[str, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import httpx

    report = profile_file(fixtures["csv"], ProfileOptions(format="csv"))
    output = tmp_path / "report.json"
    write_report(output, report)
    with patch("httpx.post", side_effect=httpx.ConnectError("SENSITIVE_TRANSPORT_DETAIL")):
        with pytest.raises(SystemExit):
            main(
                [
                    "profile-import",
                    str(output),
                    "--api-url",
                    "http://127.0.0.1:8000",
                    "--project-id",
                    "00000000-0000-0000-0000-000000000001",
                    "--reviewed-fingerprint",
                    report.profile_fingerprint,
                ]
            )
    message = capsys.readouterr().err
    assert "metadata_api_unreachable" in message
    assert "SENSITIVE_TRANSPORT_DETAIL" not in message
