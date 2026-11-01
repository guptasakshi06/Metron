"""Bounded structural validation for uploaded analytical data files.

Untrusted parsers run in a fresh subprocess. The parent process receives only a
small machine-readable result or a stable error code; parser diagnostics and
input records are never returned to callers.

CSV requires a non-empty unique header and rectangular records. NDJSON requires
at least one complete JSON object per nonblank line; a final newline is optional,
but empty input, truncated objects and non-standard numbers such as NaN are
rejected. Parquet pages are decoded with PyArrow when that optional parser is
installed; the file's uncompressed column metadata is checked before decoding.
"""

from __future__ import annotations

import json
import math
import os
import select
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationLimits:
    raw_bytes: int
    decompressed_bytes: int
    timeout_seconds: float = 10.0
    memory_mib: int = 256
    output_bytes: int = 4096

    def __post_init__(self) -> None:
        for name in ("raw_bytes", "decompressed_bytes", "memory_mib", "output_bytes"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ValidationResult:
    detected_format: str
    compression: str | None
    physical_bytes: int
    decompressed_bytes: int


class ValidationError(ValueError):
    """A sanitized, stable validation failure suitable for API responses."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# The child speaks a tiny JSON protocol. Keep this self-contained so it can run
# with `-I`, independently of the caller's import path and application state.
_CHILD = r'''
import codecs, csv, gzip, json, os, resource, struct, sys

path, declared, raw_limit, expanded_limit, memory_mib, cpu_seconds = sys.argv[1:7]
raw_limit, expanded_limit = int(raw_limit), int(expanded_limit)
memory = int(memory_mib) * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
cpu_seconds = int(cpu_seconds)
resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

class Invalid(Exception):
    def __init__(self, code): self.code = code

def answer(code=None, fmt=None, compression=None, physical=0, expanded=0):
    print(json.dumps({"code": code, "format": fmt, "compression": compression,
                      "physical": physical, "expanded": expanded}, separators=(",", ":")))

def reject_nonstandard_number(_value):
    raise ValueError("non-standard JSON number")

def bounded_chunks(stream, limit, initial=0):
    total = initial
    while True:
        block = stream.read(65536)
        if not block: break
        total += len(block)
        if total > limit: raise Invalid("decompressed_too_large")
        yield block

def inspect_text(stream, fmt, physical, compression):
    expanded = 0
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    def lines():
        nonlocal expanded
        pending = ""
        try:
            for chunk in bounded_chunks(stream, expanded_limit):
                expanded += len(chunk)
                pending += decoder.decode(chunk)
                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    yield line + "\n"
            pending += decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            raise Invalid("invalid_encoding")
        if pending:
            yield pending
    if fmt == "ndjson":
        records = 0
        for line in lines():
            if not line.strip(): continue
            try: value = json.loads(line, parse_constant=reject_nonstandard_number)
            except (json.JSONDecodeError, ValueError): raise Invalid("invalid_structure")
            if not isinstance(value, dict): raise Invalid("invalid_structure")
            records += 1
        if not records: raise Invalid("empty_file")
    else:
        try:
            rows = csv.reader(lines(), strict=True)
            header = next(rows)
            if (
                not header
                or any(not name.strip() for name in header)
                or len(set(header)) != len(header)
            ):
                raise Invalid("invalid_structure")
            count = 0
            for row in rows:
                if len(row) != len(header): raise Invalid("invalid_structure")
                count += 1
        except StopIteration:
            raise Invalid("empty_file")
        except csv.Error:
            raise Invalid("invalid_structure")
    return physical, expanded

def main():
    try:
        with open(path, "rb") as source:
            physical = os.fstat(source.fileno()).st_size
            if physical > raw_limit: raise Invalid("raw_too_large")
            magic = source.read(4)
            source.seek(0)
            if magic.startswith(b"PK\x03\x04") or magic.startswith(b"PK\x05\x06"):
                raise Invalid("unsupported_archive")
            if physical >= 262:
                source.seek(257)
                if source.read(5) == b"ustar":
                    raise Invalid("unsupported_archive")
                source.seek(0)
            if magic[:2] == b"\x1f\x8b":
                if declared != "ndjson": raise Invalid("format_mismatch")
                try:
                    with gzip.GzipFile(fileobj=source, mode="rb") as stream:
                        p, e = inspect_text(stream, "ndjson", physical, "gzip")
                except (OSError, EOFError, struct.error):
                    raise Invalid("invalid_compression")
                answer(fmt="ndjson", compression="gzip", physical=p, expanded=e)
                return
            if magic == b"PAR1":
                if declared != "parquet": raise Invalid("format_mismatch")
                try:
                    import pyarrow.parquet as pq
                except ImportError:
                    raise Invalid("parquet_support_unavailable")
                try:
                    parquet = pq.ParquetFile(path)
                    metadata = parquet.metadata
                    expanded = 0
                    for group_index in range(metadata.num_row_groups):
                        group = metadata.row_group(group_index)
                        for column_index in range(group.num_columns):
                            column_size = group.column(column_index).total_uncompressed_size
                            if column_size < 0: raise Invalid("invalid_structure")
                            expanded += column_size
                            if expanded > expanded_limit: raise Invalid("decompressed_too_large")
                    if metadata.num_rows < 1: raise Invalid("empty_file")
                    # Decode bounded batches to force page/dictionary/codec validation.
                    for _batch in parquet.iter_batches(batch_size=128): pass
                except Invalid: raise
                except Exception: raise Invalid("invalid_structure")
                answer(fmt="parquet", compression=None, physical=physical, expanded=expanded)
                return
            if declared == "parquet": raise Invalid("format_mismatch")
            if declared not in ("csv", "ndjson"): raise Invalid("unsupported_format")
            physical, expanded = inspect_text(source, declared, physical, None)
            answer(fmt=declared, compression=None, physical=physical, expanded=expanded)
    except Invalid as error:
        answer(code=error.code)
    except (OSError, EOFError):
        answer(code="invalid_structure")
    except Exception:
        answer(code="invalid_structure")

main()
'''


def validate_file(path: Path, declared_format: str, limits: ValidationLimits) -> ValidationResult:
    """Validate actual file structure under explicit resource limits.

    Only ``csv``, ``ndjson`` and ``parquet`` are accepted. Raises
    :class:`ValidationError` with a stable code and no content-derived detail.
    """
    declared = str(declared_format).lower()
    if declared not in {"csv", "ndjson", "parquet"}:
        raise ValidationError("unsupported_format")
    try:
        file_path = Path(path)
        if not file_path.is_file():
            raise ValidationError("invalid_path")
        if file_path.stat().st_size > limits.raw_bytes:
            raise ValidationError("raw_too_large")
    except ValidationError:
        raise
    except OSError:
        raise ValidationError("invalid_path") from None

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                _CHILD,
                os.fspath(file_path),
                declared,
                str(limits.raw_bytes),
                str(limits.decompressed_bytes),
                str(limits.memory_mib),
                str(max(1, math.ceil(limits.timeout_seconds))),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except (OSError, ValueError):
        raise ValidationError("validator_unavailable") from None

    assert process.stdout is not None
    deadline = time.monotonic() + limits.timeout_seconds
    output = bytearray()
    try:
        descriptor = process.stdout.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise ValidationError("validation_timeout")
            ready, _, _ = select.select([descriptor], [], [], min(remaining, 0.1))
            if ready:
                chunk = os.read(descriptor, min(8192, limits.output_bytes + 1 - len(output)))
                if len(output) + len(chunk) > limits.output_bytes:
                    process.kill()
                    process.wait()
                    raise ValidationError("validator_output_limit")
                output.extend(chunk)
                if not chunk:
                    break
            if process.poll() is not None and not ready:
                break
        return_code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise ValidationError("validation_timeout") from None
    finally:
        process.stdout.close()

    if return_code != 0:
        # A resource-limit crash is indistinguishable from a worker failure, but
        # neither leaks stderr or data-dependent parser details.
        raise ValidationError("validation_resource_limit")
    try:
        payload: dict[str, Any] = json.loads(output)
        code = payload.get("code")
        if code is not None:
            raise ValidationError(str(code))
        fmt = payload["format"]
        if fmt != declared:
            raise ValidationError("format_mismatch")
        return ValidationResult(
            detected_format=fmt,
            compression=payload["compression"],
            physical_bytes=int(payload["physical"]),
            decompressed_bytes=int(payload["expanded"]),
        )
    except ValidationError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ValidationError("validator_failed") from None
