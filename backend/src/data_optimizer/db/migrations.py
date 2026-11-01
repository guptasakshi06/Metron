"""Transactional, checksummed SQL migrations shipped with the application."""

from __future__ import annotations

import hashlib
import re
from importlib.resources import files
from pathlib import Path

import psycopg

MIGRATION_NAME = re.compile(r"^[0-9]{4}_[a-z0-9_]+\.sql$")
LOCK_KEY = 7_043_211_902


def migration_files() -> list[tuple[str, str, str]]:
    """Return validated (name, content, sha256) migrations from source or installed wheel."""
    packaged = files("data_optimizer").joinpath("migrations")
    root = packaged if packaged.is_dir() else Path(__file__).resolve().parents[3] / "migrations"
    found: list[tuple[str, str, str]] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if not entry.name.endswith(".sql"):
            continue
        if not MIGRATION_NAME.fullmatch(entry.name):
            raise ValueError(f"invalid migration filename: {entry.name}")
        content = entry.read_text(encoding="utf-8")
        found.append((entry.name, content, hashlib.sha256(content.encode("utf-8")).hexdigest()))
    if not found:
        raise RuntimeError("no packaged SQL migrations were found")
    return found


def migrate(database_url: str) -> list[str]:
    """Apply pending migrations under an advisory lock; reject changed applied files."""
    applied_now: list[str] = []
    with psycopg.connect(database_url, autocommit=True, connect_timeout=5) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    name text PRIMARY KEY,
                    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
                    applied_at timestamptz NOT NULL DEFAULT now()
                )"""
            )
            for name, sql, checksum in migration_files():
                with connection.transaction():
                    existing = connection.execute(
                        "SELECT checksum FROM schema_migrations WHERE name = %s", (name,)
                    ).fetchone()
                    if existing is not None:
                        if existing[0] != checksum:
                            raise RuntimeError(f"applied migration checksum changed: {name}")
                        continue
                    connection.execute(sql)
                    connection.execute(
                        "INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)",
                        (name, checksum),
                    )
                    applied_now.append(name)
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return applied_now
