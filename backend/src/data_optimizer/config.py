"""Local settings and explicit configurable processing bounds."""

from ipaddress import ip_address
from typing import Literal

from pydantic import (
    Field,
    HttpUrl,
    PostgresDsn,
    RedisDsn,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: PostgresDsn = Field(
        default_factory=lambda: PostgresDsn(
            "postgresql://data_optimizer:data_optimizer_dev_only@127.0.0.1:55432/data_optimizer"
        )
    )
    redis_url: RedisDsn = Field(default_factory=lambda: RedisDsn("redis://127.0.0.1:56379/0"))
    minio_health_url: HttpUrl = Field(default_factory=lambda: HttpUrl("http://127.0.0.1:59000"))
    app_env: Literal["development", "production"] = "development"
    auth_mode: Literal["local", "jwt"] = "local"
    api_host: str = "127.0.0.1"
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_public_key: str | None = None
    s3_endpoint_url: HttpUrl = Field(default_factory=lambda: HttpUrl("http://127.0.0.1:59000"))
    s3_access_key: str = "data_optimizer"
    s3_secret_key: str = "data_optimizer_dev_only"
    s3_bucket: str = "data-optimizer-local"
    upload_temp_dir: str = ".data-optimizer-tmp"
    max_concurrent_uploads: int = Field(default=4, ge=1, le=32)
    max_upload_temp_bytes: int = Field(default=1_073_741_824, ge=1)
    max_upload_seconds: int = Field(default=300, ge=1, le=3600)
    max_uploads_per_tenant: int = Field(default=3, ge=1, le=20)
    upload_session_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    default_retention_days: int = Field(default=7, ge=1, le=30)
    validation_timeout_seconds: int = Field(default=30, ge=1, le=300)
    validation_memory_mib: int = Field(default=512, ge=128, le=4096)
    max_raw_upload_bytes: int = Field(default=268_435_456, gt=0)
    max_decompressed_bytes: int = Field(default=1_073_741_824, gt=0)
    max_profiles_per_project: int = Field(default=100, ge=1, le=1000)
    max_candidates: int = Field(default=12, ge=1, le=12)
    max_timed_repeats: int = Field(default=5, ge=1, le=5)
    max_query_seconds: int = Field(default=60, gt=0, le=3600)
    max_assessment_seconds: int = Field(default=900, gt=0, le=7200)
    max_worker_memory_mib: int = Field(default=2048, gt=0)

    @field_validator("max_decompressed_bytes")
    @classmethod
    def decompressed_cap_covers_raw_cap(cls, value: int, info: ValidationInfo) -> int:
        raw_limit = info.data.get("max_raw_upload_bytes")
        if raw_limit is not None and value < raw_limit:
            raise ValueError("decompressed-byte limit must be at least the raw-upload limit")
        return value

    @model_validator(mode="after")
    def enforce_auth_boundary(self) -> "Settings":
        if self.auth_mode == "local":
            if self.app_env != "development":
                raise ValueError("local authentication is allowed only in development")
            try:
                loopback = ip_address(self.api_host).is_loopback
            except ValueError as error:
                raise ValueError("local authentication requires an IP loopback API_HOST") from error
            if not loopback:
                raise ValueError("local authentication requires an IP loopback API_HOST")
        elif not all((self.auth_issuer, self.auth_audience, self.auth_public_key)):
            raise ValueError("JWT mode requires AUTH_ISSUER, AUTH_AUDIENCE, and AUTH_PUBLIC_KEY")
        if not self.s3_bucket or "/" in self.s3_bucket:
            raise ValueError("S3_BUCKET must be a non-empty bucket name")
        return self


settings = Settings()
