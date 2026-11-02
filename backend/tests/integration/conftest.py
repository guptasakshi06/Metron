from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from data_optimizer.api.main import create_app
from data_optimizer.config import Settings, settings
from data_optimizer.db.migrations import migrate
from data_optimizer.db.seed import seed_local
from data_optimizer.storage.s3 import S3Storage


@pytest.fixture
def services(tmp_path: Path) -> Iterator[tuple[Settings, TestClient]]:
    schema = f"s02_{uuid.uuid4().hex}"
    bucket = f"data-optimizer-test-{uuid.uuid4().hex[:16]}"
    parts = urlsplit(str(settings.database_url))
    query = dict(parse_qsl(parts.query))
    query["options"] = f"-csearch_path={schema}"
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    config = Settings(
        database_url=url,
        assessment_work_dir=str(tmp_path / "jobs"),
        assessment_queue="test-" + uuid.uuid4().hex,
        s3_bucket=bucket,
        max_raw_upload_bytes=4096,
        max_decompressed_bytes=16384,
        validation_memory_mib=768,
        max_uploads_per_tenant=2,
    )
    with psycopg.connect(str(settings.database_url)) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')
    storage = S3Storage(config)
    try:
        migrate(str(config.database_url))
        assert migrate(str(config.database_url)) == []
        seed_local(str(config.database_url))
        storage.ensure_bucket()
        client = TestClient(create_app(config), client=("127.0.0.1", 12345))
        yield config, client
    finally:
        try:
            objects = storage.client.list_objects_v2(Bucket=bucket).get("Contents", [])
            if objects:
                storage.client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": item["Key"]} for item in objects]},
                )
            storage.client.delete_bucket(Bucket=bucket)
        finally:
            with psycopg.connect(str(settings.database_url)) as connection:
                connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
