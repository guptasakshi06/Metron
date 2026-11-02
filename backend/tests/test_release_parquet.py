"""Actual bounded-worker regression for the S14 dictionary/Zstd Parquet crash."""

from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from data_optimizer.candidates.models import ConversionRequest
from data_optimizer.conversion.service import convert, list_candidates
from data_optimizer.integrity.models import IntegrityOptions
from data_optimizer.profiling.models import ProfileOptions
from data_optimizer.profiling.service import profile_file
from data_optimizer.storage.validation import ValidationLimits, validate_file
from data_optimizer.workloads.models import Query, Workload


def test_dictionary_zstd_parquet_under_address_space_limits(tmp_path: Path, monkeypatch) -> None:
    # Caller allocator settings cannot silently change a bounded worker's runtime policy.
    monkeypatch.setenv("ARROW_DEFAULT_MEMORY_POOL", "mimalloc")
    source = tmp_path / "dictionary.parquet"
    pq.write_table(
        pa.table(
            {
                "id": [f"{i:08}" for i in range(2048)],
                "category": ["one"] * 2048,
                "value": [i % 5 for i in range(2048)],
            }
        ),
        source,
        compression="zstd",
        compression_level=9,
        row_group_size=2048,
    )
    before = source.read_bytes()
    validated = validate_file(
        source,
        "parquet",
        ValidationLimits(raw_bytes=1_048_576, decompressed_bytes=4_194_304, memory_mib=512),
    )
    assert validated.physical_bytes == len(before)
    options = ProfileOptions(format="parquet")
    assert profile_file(source, options).row_count == 2048
    request = ConversionRequest(
        tenant_id=uuid4(),
        assessment_id=uuid4(),
        source=options,
        limits=IntegrityOptions(memory_mib=2048),
        max_candidates=4,
        workload=Workload(
            queries=(Query(id="ids", kind="projection", columns=("id",)),),
            concurrency=1,
            concurrency_scope="single_process",
        ),
    )
    candidates = list_candidates(source, request)
    assert len(candidates.candidates) == 4
    for candidate in candidates.candidates:
        result = convert(source, tmp_path / "outputs", request, candidate.configuration)
        assert result.status == "validated", result.reasons
        assert result.manifest.integrity.status == "passed"
        assert result.manifest.integrity.baseline.row_count == 2048
    assert source.read_bytes() == before
