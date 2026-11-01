from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from data_optimizer.storage.validation import (
    ValidationError,
    ValidationLimits,
    validate_file,
)

LIMITS = ValidationLimits(raw_bytes=1024 * 1024, decompressed_bytes=2 * 1024 * 1024)


def test_valid_csv_is_structurally_validated(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    path.write_text("id,name\n1,Ada\n2,Lin\n", encoding="utf-8")

    result = validate_file(path, "csv", LIMITS)

    assert (result.detected_format, result.compression) == ("csv", None)
    assert result.physical_bytes == path.stat().st_size
    assert result.decompressed_bytes == path.stat().st_size


def test_valid_ndjson_is_structurally_validated(tmp_path: Path) -> None:
    path = tmp_path / "records.ndjson"
    path.write_text('{"id":1}\n{"id":2,"name":"Ada"}\n', encoding="utf-8")

    result = validate_file(path, "ndjson", LIMITS)

    assert (result.detected_format, result.compression) == ("ndjson", None)
    assert result.physical_bytes == path.stat().st_size
    assert result.decompressed_bytes == path.stat().st_size


def test_valid_gzip_ndjson_reports_both_sizes(tmp_path: Path) -> None:
    path = tmp_path / "records.ndjson.gz"
    source = b'{"event":"a"}\n{"event":"b"}\n'
    path.write_bytes(gzip.compress(source))

    result = validate_file(path, "ndjson", LIMITS)

    assert (result.detected_format, result.compression) == ("ndjson", "gzip")
    assert result.physical_bytes == path.stat().st_size
    assert result.decompressed_bytes == len(source)


def test_valid_parquet_is_structurally_decoded(tmp_path: Path) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    import pyarrow.parquet as parquet

    path = tmp_path / "records.parquet"
    parquet.write_table(pyarrow.table({"id": [1, 2], "name": ["Ada", "Lin"]}), path)

    result = validate_file(path, "parquet", LIMITS)

    assert (result.detected_format, result.compression) == ("parquet", None)
    assert result.physical_bytes == path.stat().st_size
    assert result.decompressed_bytes > 0


def test_parquet_uncompressed_metadata_is_bounded_before_decode(tmp_path: Path) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    import pyarrow.parquet as parquet

    path = tmp_path / "expanded.parquet"
    values = [f"{'x' * 2048}{index:04d}" for index in range(1024)]
    parquet.write_table(pyarrow.table({"payload": values}), path, compression="zstd")
    metadata = parquet.ParquetFile(path).metadata
    uncompressed_column_bytes = metadata.row_group(0).column(0).total_uncompressed_size
    limits = ValidationLimits(raw_bytes=1024 * 1024, decompressed_bytes=1024 * 1024)

    assert path.stat().st_size < limits.decompressed_bytes
    assert uncompressed_column_bytes > limits.decompressed_bytes
    with pytest.raises(ValidationError) as error:
        validate_file(path, "parquet", limits)

    assert error.value.code == "decompressed_too_large"


@pytest.mark.parametrize(
    ("contents", "declared", "expected"),
    [
        (b"a,b\n1\n", "csv", "invalid_structure"),
        (b'{"id":}\n', "ndjson", "invalid_structure"),
        (b'{"id":1}\n{"id":', "ndjson", "invalid_structure"),
        (b'{"id":NaN}\n', "ndjson", "invalid_structure"),
        (b"not json\n", "ndjson", "invalid_structure"),
        (b"", "csv", "empty_file"),
        (b" \n", "ndjson", "empty_file"),
        (b"id,id\n1,2\n", "csv", "invalid_structure"),
        (b"a,b\n1,2,3\n", "csv", "invalid_structure"),
        (b"a,b\n1,2\n", "parquet", "format_mismatch"),
    ],
)
def test_invalid_or_mismatched_file_is_rejected(
    tmp_path: Path, contents: bytes, declared: str, expected: str
) -> None:
    path = tmp_path / "input"
    path.write_bytes(contents)

    with pytest.raises(ValidationError) as error:
        validate_file(path, declared, LIMITS)

    assert error.value.code == expected
    assert str(error.value) == expected


def test_gzip_expansion_limit_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "bomb.ndjson.gz"
    path.write_bytes(gzip.compress((b'{"x":"' + b"a" * 4096 + b'"}\n') * 16))
    limits = ValidationLimits(raw_bytes=1024 * 1024, decompressed_bytes=8192)

    with pytest.raises(ValidationError) as error:
        validate_file(path, "ndjson", limits)

    assert error.value.code == "decompressed_too_large"


def test_raw_upload_limit_is_enforced_before_parser_starts(tmp_path: Path) -> None:
    path = tmp_path / "large.csv"
    path.write_bytes(b"a\n" + b"1\n" * 100)
    limits = ValidationLimits(raw_bytes=20, decompressed_bytes=1000)

    with pytest.raises(ValidationError) as error:
        validate_file(path, "csv", limits)

    assert error.value.code == "raw_too_large"


def test_malformed_gzip_is_rejected_without_exposing_details(tmp_path: Path) -> None:
    path = tmp_path / "broken.gz"
    path.write_bytes(b"\x1f\x8b\x08\x00broken")

    with pytest.raises(ValidationError) as error:
        validate_file(path, "ndjson", LIMITS)

    assert error.value.code == "invalid_compression"
    assert "broken" not in str(error.value)


def test_timeout_is_a_stable_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import data_optimizer.storage.validation as validation

    path = tmp_path / "records.csv"
    path.write_text("id\n1\n", encoding="utf-8")
    monkeypatch.setattr(validation, "_CHILD", "import time; time.sleep(1)")
    limits = ValidationLimits(
        raw_bytes=1024, decompressed_bytes=2048, timeout_seconds=0.05
    )

    with pytest.raises(ValidationError) as error:
        validation.validate_file(path, "csv", limits)

    assert error.value.code == "validation_timeout"


def test_child_memory_limit_is_a_stable_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import data_optimizer.storage.validation as validation

    path = tmp_path / "records.csv"
    path.write_text("id\n1\n", encoding="utf-8")
    monkeypatch.setattr(
        validation,
        "_CHILD",
        "import resource; resource.setrlimit(resource.RLIMIT_AS, (32 * 1024 * 1024,) * 2); "
        "value = bytearray(128 * 1024 * 1024)",
    )
    limits = ValidationLimits(
        raw_bytes=1024,
        decompressed_bytes=2048,
        timeout_seconds=2,
        memory_mib=32,
    )

    with pytest.raises(ValidationError) as error:
        validation.validate_file(path, "csv", limits)

    assert error.value.code == "validation_resource_limit"


def test_child_output_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import data_optimizer.storage.validation as validation

    path = tmp_path / "records.csv"
    path.write_text("id\n1\n", encoding="utf-8")
    monkeypatch.setattr(validation, "_CHILD", "print('x' * 10000)")
    limits = ValidationLimits(
        raw_bytes=1024, decompressed_bytes=2048, output_bytes=128
    )

    with pytest.raises(ValidationError) as error:
        validation.validate_file(path, "csv", limits)

    assert error.value.code == "validator_output_limit"
