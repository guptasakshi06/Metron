"""Run the real dashboard against isolated PostgreSQL/MinIO/RQ and Docker workers.

Requires local infrastructure and the benchmark image. Creates no customer data.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
import psycopg
import redis
from data_optimizer.config import Settings, settings
from data_optimizer.db.migrations import migrate
from data_optimizer.db.seed import seed_local
from data_optimizer.profiling.models import ProfileOptions
from data_optimizer.profiling.service import profile_file
from data_optimizer.storage.s3 import S3Storage

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    schema = "s10_" + uuid4().hex
    bucket = "s10-" + uuid4().hex[:16]
    parts = urlsplit(str(settings.database_url))
    query = dict(parse_qsl(parts.query))
    query["options"] = "-csearch_path=" + schema
    url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    with (
        tempfile.TemporaryDirectory(prefix="s10-browser-") as temp,
        ExitStack() as log_stack,
    ):
        config = Settings(
            database_url=url,
            s3_bucket=bucket,
            assessment_work_dir=temp + "/jobs",
            assessment_queue=schema,
            max_raw_upload_bytes=1048576,
            max_decompressed_bytes=4194304,
        )
        environment = dict(os.environ)
        environment.update(
            {
                k.upper(): str(v)
                for k, v in config.model_dump(mode="json").items()
                if v is not None
            }
        )
        environment.update(
            API_PORT="8010",
            FRONTEND_PORT="5174",
            BROWSER_BASE_URL="http://127.0.0.1:5174",
            S10_FIXTURE_DIR=temp,
            PATH=str(ROOT / ".tools/node24/bin") + ":" + os.environ["PATH"],
        )
        processes: list[subprocess.Popen] = []
        logs = []
        storage = S3Storage(config)
        with psycopg.connect(str(settings.database_url)) as db:
            db.execute(f'CREATE SCHEMA "{schema}"')
        try:
            migrate(url)
            seed_local(url)
            storage.ensure_bucket()
            raw = (ROOT / "examples/s04-events.ndjson").read_bytes()
            import gzip

            import pyarrow as pa
            import pyarrow.parquet as pq

            Path(temp, "events.ndjson").write_bytes(raw)
            Path(temp, "events.ndjson.gz").write_bytes(gzip.compress(raw, mtime=0))
            Path(temp, "events.csv").write_text("id,category\n001,a\n002,a\n003,b\n")
            pq.write_table(
                pa.table({"id": ["001", "002", "003"], "category": ["a", "a", "b"]}),
                Path(temp, "events.parquet"),
            )
            report = profile_file(
                Path(temp, "events.ndjson"), ProfileOptions(format="ndjson")
            )
            Path(temp, "profile.json").write_text(report.model_dump_json())
            for name, command in [
                ("dev", ["bash", "scripts/dev.sh"]),
                (
                    "dispatch",
                    [sys.executable, "-m", "data_optimizer.cli", "dispatch-jobs"],
                ),
                ("worker", [sys.executable, "-m", "data_optimizer.cli", "worker"]),
            ]:
                log = log_stack.enter_context(
                    (ROOT / f"docs/evidence/s10-{name}.log").open("w")
                )
                logs.append(log)
                processes.append(
                    subprocess.Popen(
                        command,
                        cwd=ROOT,
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                )
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    if httpx.get("http://127.0.0.1:5174/api/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Local browser stack not ready; see s10-dev.log")
            result = subprocess.run(
                ["npm", "exec", "--", "playwright", "test"],
                cwd=ROOT / "frontend",
                env=environment,
                check=False,
            )
            states = httpx.get("http://127.0.0.1:8010/v1/assessments").json()["items"]
            for state in states:
                response = httpx.get(
                    f"http://127.0.0.1:8010/v1/assessments/{state['id']}/result"
                )
                if response.status_code != 200:
                    continue
                report = response.json()
                if report["evidence"] == "scenario_guidance":
                    name = "metadata" if report["profile"] else "startup"
                elif (
                    report["request"]["conversion"]["source"]["format"] == "ndjson"
                    and state["status"] == "completed"
                ):
                    name = (
                        "measured-change"
                        if report["decision"]["outcome"] == "change"
                        else "keep-current"
                    )
                else:
                    continue
                (ROOT / f"docs/evidence/s10-{name}-report.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
            return result.returncode
        finally:
            for p in reversed(processes):
                if p.poll() is None:
                    os.killpg(p.pid, signal.SIGTERM)
            for p in reversed(processes):
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
            # Explicitly remove only this test's containers and queue records.
            with psycopg.connect(url) as db:
                ids = [
                    str(r[0])
                    for r in db.execute("SELECT id FROM assessments").fetchall()
                ]
            for assessment in ids:
                listing = subprocess.run(
                    [
                        "docker",
                        "ps",
                        "-aq",
                        "--filter",
                        f"label=data-optimizer.assessment={assessment}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if listing.stdout.split():
                    subprocess.run(
                        ["docker", "rm", "-f", *listing.stdout.split()],
                        check=True,
                        capture_output=True,
                    )
            client = redis.Redis.from_url(str(config.redis_url))
            keys = list(client.scan_iter(match=f"*{schema}*"))
            if keys:
                client.delete(*keys)
            # RQ job keys contain assessment UUIDs, not schema names.
            for assessment in ids:
                keys = list(client.scan_iter(match=f"*{assessment}*"))
                if keys:
                    client.delete(*keys)
            objects = storage.client.list_objects_v2(Bucket=bucket).get("Contents", [])
            if objects:
                storage.client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": x["Key"]} for x in objects]},
                )
            storage.client.delete_bucket(Bucket=bucket)
            with psycopg.connect(str(settings.database_url)) as db:
                db.execute(f'DROP SCHEMA "{schema}" CASCADE')
            for log in logs:
                log.close()


if __name__ == "__main__":
    exit_code = main()
    (ROOT / "docs/evidence/s10-run-status.json").write_text(
        json.dumps({"exit_code": exit_code, "isolated_resources_cleaned": True}) + "\n"
    )
    print(
        f"Browser verification exit={exit_code}; isolated stack/resources cleaned.",
        flush=True,
    )
    raise SystemExit(exit_code)
