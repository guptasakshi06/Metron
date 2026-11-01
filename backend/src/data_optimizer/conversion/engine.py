"""Internal conversion worker; caller must enforce process limits and private scratch."""

from __future__ import annotations

import gzip
import json
import math
import resource
import shutil
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from data_optimizer.candidates.generator import exclusion, generate
from data_optimizer.candidates.models import CandidateConfig, ConversionRequest
from data_optimizer.conversion.models import Artifact, ConversionManifest
from data_optimizer.integrity.canonical import encode
from data_optimizer.integrity.engine import verify
from data_optimizer.integrity.models import Baseline, VerificationRequest
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import ProfileOptions, fingerprint
from data_optimizer.readers.stream import Budget, ProfileError, rows


def json_value(value: Any) -> str:
    if isinstance(value, Decimal):
        # Keep exponent/scale. Integer-looking decimals need a fractional/exponent marker.
        text = str(value)
        return text if "." in text or "E" in text or "e" in text else text + "e0"
    if isinstance(value, datetime):
        return json.dumps(value.isoformat())
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + ":" + json_value(v) for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(json_value(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=True, allow_nan=False)


def schema_for(path: Path, options: ProfileOptions, baseline: Baseline) -> Any:
    if options.format == "parquet" and not options.schema_overrides:
        return pq.ParquetFile(path, arrow_extensions_enabled=False).schema_arrow
    fields = []
    types = {
        "string": pa.string(),
        "integer": pa.int64(),
        "float": pa.float64(),
        "boolean": pa.bool_(),
        "null": pa.null(),
        "binary": pa.binary(),
        "date": pa.date32(),
        "timestamp_aware": pa.timestamp("us", tz="UTC"),
        "timestamp_naive": pa.timestamp("us"),
    }
    for name, column in baseline.columns.items():
        kinds = set(column.types) - {"null"}
        logical = next(iter(kinds)) if kinds else "null"
        if logical == "decimal":
            scale = column.decimal_scales[0]
            precision = max(1, column.decimal_integer_digits + max(0, scale), abs(scale))
            data_type = pa.decimal128(precision, scale)
        else:
            data_type = types[logical]
        fields.append(pa.field(name, data_type))
    return pa.schema(fields)


def output_options(request: ConversionRequest, config: CandidateConfig) -> ProfileOptions:
    if config.baseline:
        return request.source
    overrides = (
        {
            name: target
            for name, target in request.source.schema_overrides.items()
            if target == "timestamp"
        }
        if config.format == "ndjson"
        else {}
    )
    return request.source.model_copy(
        update={
            "format": config.format,
            "schema_overrides": overrides,
            "csv_null_tokens": (),
            "max_raw_bytes": request.max_output_bytes,
        }
    )


def check_disk(directory: Path, request: ConversionRequest) -> None:
    if sum(p.stat().st_size for p in directory.rglob("*") if p.is_file()) > (
        request.max_output_bytes
    ):
        raise ProfileError("conversion_output_byte_quota")


def materialize(
    path: Path,
    directory: Path,
    request: ConversionRequest,
    config: CandidateConfig,
    baseline: Baseline,
) -> tuple[list[Path], int]:
    if config.baseline:
        output = directory / "part-0000.original"
        shutil.copyfile(path, output)
        check_disk(directory, request)
        return [output], 1
    # Full layouts are deliberately memory-bounded by the worker address-space/row quotas.
    values: list[dict[str, Any]] = []
    for row in rows(path, request.source, Budget(request.source.max_decoded_bytes)):
        values.append(row)
        if len(values) > request.limits.max_rows:
            raise ProfileError("conversion_row_quota")
    groups: dict[bytes, list[dict[str, Any]]] = {}
    for row in values:
        key = encode({c: row[c] for c in config.partition_by}) if config.partition_by else b""
        if key not in groups:
            if len(groups) >= request.max_partitions:
                raise ProfileError("partition_count_quota")
            groups[key] = []
        groups[key].append(row)
    if config.partition_by and any(len(g) < request.min_partition_rows for g in groups.values()):
        raise ProfileError("partition_small_file_amplification")
    schema = schema_for(path, request.source, baseline) if config.format == "parquet" else None
    outputs: list[Path] = []
    for part, group in enumerate(groups.values()):
        subdir = directory / f"p{part:04d}" if config.partition_by else directory
        subdir.mkdir(exist_ok=True)
        if config.format == "parquet":
            table = pa.Table.from_pylist(group, schema=schema)
            if config.sort_by:
                table = table.sort_by([(c, "ascending") for c in config.sort_by])
            rows_per_file = max(
                1, int(len(group) * config.target_file_bytes / max(1, table.nbytes))
            )
        else:
            table = None
            average = sum(len(encode(r)) for r in group) / len(group)
            rows_per_file = max(1, int(config.target_file_bytes / max(1, average)))
        count = math.ceil(len(group) / rows_per_file)
        if len(outputs) + count > request.max_files:
            raise ProfileError("conversion_file_count_quota")
        for index, start in enumerate(range(0, len(group), rows_per_file)):
            suffix = "parquet" if table is not None else "ndjson.gz"
            output = subdir / f"part-{index:04d}.{suffix}"
            if table is not None:
                pq.write_table(
                    table.slice(start, rows_per_file),
                    output,
                    compression=config.codec,
                    compression_level=config.compression_level,
                    row_group_size=config.row_group_rows,
                    version="2.6",
                    allow_truncated_timestamps=False,
                )
            else:
                with (
                    output.open("wb") as raw,
                    gzip.GzipFile(
                        filename="",
                        fileobj=raw,
                        mode="wb",
                        mtime=0,
                        compresslevel=config.compression_level or 6,
                    ) as zipped,
                ):
                    for row in group[start : start + rows_per_file]:
                        zipped.write((json_value(row) + "\n").encode("utf-8"))
            outputs.append(output)
            check_disk(directory, request)
    return outputs, len(groups)


def concatenate(
    outputs: list[Path], combined: Path, config: CandidateConfig, request: ConversionRequest
) -> Path:
    if len(outputs) == 1:
        return outputs[0]
    if config.format == "ndjson":
        with combined.open("wb") as target:
            for output in outputs:
                with output.open("rb") as source:
                    shutil.copyfileobj(source, target)
    else:
        first = pq.ParquetFile(outputs[0], arrow_extensions_enabled=False)
        with pq.ParquetWriter(combined, first.schema_arrow, compression="zstd") as writer:
            for output in outputs:
                source = pq.ParquetFile(output, arrow_extensions_enabled=False)
                if source.schema_arrow != first.schema_arrow:
                    raise ProfileError("output_schema_mismatch")
                for batch in source.iter_batches(batch_size=128, use_threads=False):
                    writer.write_batch(batch)
    check_disk(combined.parent, request)
    return combined


def run(
    path: Path,
    directory: Path,
    request: ConversionRequest,
    config: CandidateConfig | None,
    key: str,
) -> dict[str, Any]:
    self_request = VerificationRequest(
        baseline=request.source,
        candidate=request.source,
        limits=request.limits,
        workload=request.workload,
    )
    evidence = verify(path, path, self_request, scratch_root=directory)
    if evidence.baseline is None or any(c.status != "passed" for c in evidence.checks):
        return {"status": "failed", "reasons": ["invalid_or_unsupported_source"]}
    if config is None:
        return generate(path, request, evidence).model_dump(mode="json")
    reasons = exclusion(config, request, evidence)
    if reasons:
        return {"status": "excluded", "reasons": reasons}
    started = time.perf_counter()
    assert evidence.baseline is not None
    outputs, partitions = materialize(path, directory, request, config, evidence.baseline)
    conversion_seconds = time.perf_counter() - started
    reader = output_options(request, config)
    validation_request = VerificationRequest(
        baseline=request.source, candidate=reader, limits=request.limits, workload=request.workload
    )
    combined = directory / ".combined"
    validation_path = concatenate(outputs, combined, config, request)
    validation_started = time.perf_counter()
    validation = verify(path, validation_path, validation_request, scratch_root=directory)
    if validation.status != "passed":
        return {
            "status": "failed",
            "reasons": ["integrity_" + validation.status]
            + [c.reason for c in validation.checks if c.status != "passed"]
            + [q.reason for q in validation.queries if q.status != "passed"],
        }
    combined.unlink(missing_ok=True)
    artifacts = tuple(
        Artifact(
            path=str(p.relative_to(directory)),
            sha256=input_digest(p, request.max_output_bytes),
            physical_bytes=p.stat().st_size,
        )
        for p in outputs
    )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    manifest = ConversionManifest(
        key=key,
        input_fingerprint=evidence.baseline.input_fingerprint,
        request_fingerprint=fingerprint(request.model_dump(mode="json")),
        manifest_fingerprint="0" * 64,
        configuration=config,
        reader=reader,
        verification_request=validation_request,
        artifacts=artifacts,
        physical_bytes=sum(a.physical_bytes for a in artifacts),
        file_count=len(artifacts),
        partition_count=partitions,
        conversion_seconds=conversion_seconds,
        verification_seconds=time.perf_counter() - validation_started,
        cpu_seconds=usage.ru_utime + usage.ru_stime,
        peak_rss_kib=usage.ru_maxrss,
        integrity=validation,
    )
    manifest = manifest.model_copy(
        update={
            "manifest_fingerprint": fingerprint(
                manifest.model_dump(mode="json", exclude={"manifest_fingerprint"})
            )
        }
    )
    (directory / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return {"status": "validated"}
