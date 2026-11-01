"""Real, bounded dependency checks used only by readiness."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping

import httpx
import psycopg
from redis.asyncio import Redis

from data_optimizer.config import Settings, settings
from data_optimizer.domain.contracts import ReadinessDependency

Probe = Callable[[Settings], Awaitable[None]]


async def postgres_probe(config: Settings) -> None:
    async with await psycopg.AsyncConnection.connect(
        str(config.database_url), connect_timeout=2, options="-c statement_timeout=1000"
    ) as connection:
        await connection.execute("SELECT 1")


async def redis_probe(config: Settings) -> None:
    client = Redis.from_url(str(config.redis_url), socket_connect_timeout=2, socket_timeout=2)
    try:
        if await client.ping() is not True:
            raise ConnectionError("Redis did not return PONG")
    finally:
        await client.aclose()


async def minio_probe(config: Settings) -> None:
    base_url = str(config.minio_health_url).rstrip("/")
    async with httpx.AsyncClient(timeout=2) as client:
        response = await client.get(f"{base_url}/minio/health/ready")
        response.raise_for_status()


async def check_dependency(probe: Probe, config: Settings) -> ReadinessDependency:
    try:
        await asyncio.wait_for(probe(config), timeout=3)
    except Exception:
        return ReadinessDependency(status="down", detail="probe failed or timed out")
    return ReadinessDependency(status="up")


async def dependency_report(
    config: Settings = settings,
    probes: Mapping[str, Probe] | None = None,
) -> dict[str, ReadinessDependency]:
    names_and_probes: tuple[tuple[str, Probe], ...] = (
        ("postgres", postgres_probe),
        ("redis", redis_probe),
        ("minio", minio_probe),
    )
    if probes is not None:
        unknown = set(probes) - {name for name, _ in names_and_probes}
        if unknown:
            raise ValueError(f"unknown readiness probe names: {', '.join(sorted(unknown))}")
        names_and_probes = tuple(
            (name, probes.get(name, probe)) for name, probe in names_and_probes
        )
    statuses = await asyncio.gather(
        *(check_dependency(probe, config) for _, probe in names_and_probes)
    )
    return {name: status for (name, _), status in zip(names_and_probes, statuses, strict=True)}
