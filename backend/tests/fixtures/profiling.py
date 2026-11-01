"""Deterministic synthetic fixtures, including deliberately duplicated observations."""

from __future__ import annotations

import gzip
import json
import random
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def generate(directory: Path, count: int = 120, seed: int = 7) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    ndjson = directory / "synthetic-events.ndjson"
    events = []
    for index in range(count):
        row = {
            "id": f"{index:08}",
            "category": rng.choice(["view", "click", "purchase"]),
            "source": "web" if index % 2 else "mobile",
            "timestamp": f"2026-01-{index % 3 + 1:02}T12:00:00+05:30",
            "text": f"SYNTHETIC_SECRET_{index:08}",
            "nested": {"items": [index, None], "precise": "0.00000000000000000001"},
            "amount": Decimal("123456789012345678.123456789012345678"),
        }
        if index % 2:
            row["optional"] = None
        if index % 7 == 0:
            row["drift"] = "text" if index % 14 else index
        events.append(row)
    events.append(events[0].copy())
    with ndjson.open("w") as output:
        for row in events:
            # Decimal inserted as a JSON number, with its exact digits preserved.
            amount = row["amount"]
            output.write(
                json.dumps({k: v for k, v in row.items() if k != "amount"})[:-1]
                + ', "amount": '
                + str(amount)
                + "}\n"
            )
    compressed = directory / "synthetic-events.ndjson.gz"
    compressed.write_bytes(gzip.compress(ndjson.read_bytes(), mtime=0))
    csv = directory / "synthetic-events.csv"
    csv.write_text(
        "id,amount,timestamp,optional\n"
        "0001,123456789.0000000000001,2026-01-01T12:00:00+05:30,\n"
        "0001,123456789.0000000000001,2026-01-01T12:00:00+05:30,\n"
        "0002,0.00000000000000000001,2026-01-02T06:30:00+00:00,NULL\n"
    )
    parquet = directory / "already-compressed.parquet"
    table = pa.table(
        {
            "id": pa.array(["0001", "0001", "0002"]),
            "amount": pa.array([Decimal("1.000000000000000001")] * 3, pa.decimal128(30, 18)),
            "timestamp": pa.array(
                [datetime(2026, 1, x, tzinfo=UTC) for x in (1, 1, 2)], pa.timestamp("ns", "UTC")
            ),
            "nested": pa.array([{"x": [1, None]}] * 3),
        }
    )
    pq.write_table(table, parquet, compression="zstd", row_group_size=2)
    return {"ndjson": ndjson, "gzip": compressed, "csv": csv, "parquet": parquet}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic S03 semantic fixtures")
    parser.add_argument("output", type=Path)
    parser.add_argument("--rows", type=int, default=120)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    for name, path in generate(args.output, args.rows, args.seed).items():
        print(f"{name}: {path}")
