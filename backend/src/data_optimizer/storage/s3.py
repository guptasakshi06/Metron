"""Private, bounded S3-compatible object storage adapter for MinIO and S3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from data_optimizer.config import Settings, settings


class S3Storage:
    def __init__(self, config: Settings = settings) -> None:
        self.bucket = config.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=str(config.s3_endpoint_url),
            aws_access_key_id=config.s3_access_key,
            aws_secret_access_key=config.s3_secret_key,
            region_name="us-east-1",
            config=BotoConfig(
                connect_timeout=3,
                read_timeout=20,
                retries={"max_attempts": 2, "mode": "standard"},
                max_pool_connections=config.max_concurrent_uploads + 4,
                s3={"addressing_style": "path"},
            ),
        )

    def ensure_bucket(self) -> None:
        """Create only this configured bucket, leaving all other MinIO data untouched."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
                raise
            self.client.create_bucket(Bucket=self.bucket)

    def put_file(self, object_key: str, path: Path, byte_count: int) -> None:
        with path.open("rb") as source:
            self.client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=source,
                ContentLength=byte_count,
                ContentType="application/octet-stream",
            )

    def head(self, object_key: str) -> int:
        response = self.client.head_object(Bucket=self.bucket, Key=object_key)
        return int(response["ContentLength"])

    def get(self, object_key: str) -> Any:
        return self.client.get_object(Bucket=self.bucket, Key=object_key)["Body"]

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)
