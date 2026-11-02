"""S14 dataset-level holdout. Never imported by the optimizer or its tuning fixtures."""

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def generate(root: Path) -> list[dict]:
    root.mkdir(parents=True, exist_ok=True)
    cases = []

    def save(name, rows, *, unsupported=False):
        path = root / (name + ".ndjson")
        path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
        )
        cases.append(
            {
                "name": name,
                "path": path,
                "format": "ndjson",
                "rows": len(rows),
                "unsupported_workload": unsupported,
            }
        )

    # Repeated identical events are legitimate; equality must retain multiplicity.
    save(
        "categorical",
        [
            {
                "id": f"{i // 2:08}",
                "category": ["east", "west", "south"][(i // 2) % 3],
                "value": i // 2,
            }
            for i in range(768)
        ],
    )
    save(
        "high_cardinality",
        [
            {
                "id": f"{i:08}",
                "category": f"group_{i % 23}",
                "value": hashlib.sha256(f"s14-holdout-{i}".encode()).hexdigest(),
            }
            for i in range(512)
        ],
    )
    save(
        "nested",
        [
            {"id": f"{i:08}", "payload": {"tags": [i, None], "ok": True}}
            for i in range(64)
        ],
        unsupported=True,
    )
    save(
        "schema_drift",
        [
            {
                "id": f"{i:08}",
                **(
                    {"value": None}
                    if i % 3 == 0
                    else {"value": str(i)}
                    if i % 3 == 1
                    else {}
                ),
            }
            for i in range(96)
        ],
        unsupported=True,
    )
    save("tiny", [{"id": "00000001", "category": "unique", "value": 7}])
    path = root / "already_optimized.parquet"
    pq.write_table(
        pa.table(
            {
                "id": [f"{i:08}" for i in range(2048)],
                "category": ["one"] * 2048,
                "value": [i % 5 for i in range(2048)],
            }
        ),
        path,
        compression="zstd",
        compression_level=9,
        row_group_size=2048,
    )
    cases.append(
        {
            "name": "already_optimized",
            "path": path,
            "format": "parquet",
            "rows": 2048,
            "unsupported_workload": False,
        }
    )
    path = root / "malformed.ndjson"
    path.write_bytes(b'{"id":"a","id":"b"}\n')
    cases.append(
        {"name": "malformed", "path": path, "format": "ndjson", "reject": True}
    )
    return cases
