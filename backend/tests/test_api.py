import asyncio

import httpx
from fastapi import FastAPI

from data_optimizer.api import main
from data_optimizer.api.probes import Probe
from data_optimizer.config import Settings


async def _request(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path)


def request(path: str, app: FastAPI = main.app) -> httpx.Response:
    return asyncio.run(_request(app, path))


def test_health_is_live_without_readiness_dependencies() -> None:
    response = request("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_reports_real_dependency_failures() -> None:
    async def unavailable_probe(_config: Settings) -> None:
        raise ConnectionError("mocked dependency outage")

    mocked_probes: dict[str, Probe] = {
        name: unavailable_probe for name in ("postgres", "redis", "minio")
    }
    isolated_app = main.create_app(probes=mocked_probes)
    response = request("/ready", isolated_app)

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert set(response.json()["dependencies"]) == {"postgres", "redis", "minio"}


def test_ready_accepts_injected_healthy_probes() -> None:
    async def healthy_probe(_config: Settings) -> None:
        return None

    mocked_probes: dict[str, Probe] = {
        name: healthy_probe for name in ("postgres", "redis", "minio")
    }
    isolated_app = main.create_app(probes=mocked_probes)
    response = request("/ready", isolated_app)

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert all(item["status"] == "up" for item in response.json()["dependencies"].values())


def test_contract_endpoint_exposes_provisional_limits() -> None:
    response = request("/v1/contracts")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["processing_limits"]["max_raw_upload_bytes"] == 268_435_456
    assert "not a measured capacity claim" in body["processing_limits"]["status"]
