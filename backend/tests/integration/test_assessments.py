"""Real DB/storage/Redis/RQ/Docker acceptance flows; no fabricated measurements."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from test_ingestion import upload

from data_optimizer.config import Settings
from data_optimizer.jobs.service import cleanup, dispatch, queue
from data_optimizer.jobs.worker import execute
from data_optimizer.storage.s3 import S3Storage

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


def submission(client: TestClient, *, raw: bool = False) -> dict:
    project = client.post("/v1/projects", json={"name": "S09 actual integration"}).json()[
        "project_id"
    ]
    request = json.loads((ROOT / "examples/s08-assessment-request.json").read_text())
    # One actual baseline and three alternatives, with one timed repeat each.
    request["conversion"]["max_candidates"] = 4
    request["benchmark"]["repeats"] = 1
    request["search"]["max_trials"] = 4
    if raw:
        data = (ROOT / "examples/s04-events.ndjson").read_bytes()
        dataset = upload(client, project, "ndjson", "events.ndjson", data)
        return {"project_id": project, "dataset_id": dataset["dataset_id"], "request": request}
    request["conversion"] = None
    return {"project_id": project, "request": request}


def submit(client: TestClient, payload: dict, key: str | None = None):
    return client.post(
        "/v1/assessments", json=payload, headers={"Idempotency-Key": key or uuid4().hex}
    )


def worker(config: Settings) -> subprocess.Popen:
    environment = dict(os.environ)
    for key, value in config.model_dump(mode="json").items():
        if value is not None:
            environment[key.upper()] = str(value)
    return subprocess.Popen(
        [sys.executable, "-m", "data_optimizer.cli", "worker", "--once"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def drain(config: Settings) -> None:
    assert dispatch(config) >= 1
    process = worker(config)
    try:
        assert process.wait(timeout=120) == 0
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def status(client: TestClient, assessment: str) -> dict:
    response = client.get("/v1/assessments/" + assessment)
    assert response.status_code == 200, response.text
    return response.json()


def wait_for(check, timeout: float = 45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out waiting for actual worker state")


def test_submission_idempotency_quota_ownership_and_immutable_inputs(services):
    config, client = services
    payload = submission(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: submit(client, payload, "same-key"), range(4)))
    assert all(r.status_code == 202 for r in responses)
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1
    assessment = ids.pop()
    changed = {**payload, "request": {**payload["request"], "replays_per_month": "123"}}
    assert submit(client, changed, "same-key").status_code == 409
    assert submit(client, payload).status_code == 202
    assert submit(client, payload).status_code == 429
    for suffix in ("", "/result", "/recommendations"):
        assert (
            client.get(
                "/v1/assessments/" + assessment + suffix, headers={"X-Local-Identity": "bob"}
            ).status_code
            == 404
        )
    assert (
        client.post(
            "/v1/assessments/" + assessment + "/cancel", headers={"X-Local-Identity": "bob"}
        ).status_code
        == 404
    )
    assert submit(client, {**payload, "project_id": str(uuid4())}).status_code == 404
    with psycopg.connect(str(config.database_url)) as db:
        assert db.execute("SELECT count(*) FROM assessments").fetchone()[0] == 2
        with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
            with db.transaction():
                db.execute("UPDATE assessments SET request='{}' WHERE id=%s", (assessment,))
    assert client.post("/v1/assessments/" + assessment + "/cancel").status_code == 202
    assert status(client, assessment)["status"] == "cancelled"
    execute(assessment, config)
    assert status(client, assessment)["attempts"] == 0


def test_api_to_real_rq_worker_storage_and_recommendation(services):
    config, client = services
    payload = submission(client, raw=True)
    response = submit(client, payload, "real-pipeline")
    assert response.status_code == 202, response.text
    assessment = response.json()["id"]
    drain(config)
    state = status(client, assessment)
    assert state["status"] == "completed", state
    assert state["attempts"] == 1
    assert state["progress"]["completed_configurations"] == 4
    assert state["progress"]["passed_trials"] == 4
    result = client.get(f"/v1/assessments/{assessment}/result")
    assert result.status_code == 200, result.text
    report = result.json()
    assert report["decision"]["outcome"] == "change"
    assert report["profile"]["evidence"] == "server_profile"
    assert report["profile"]["raw_data_inspected_by_server"] is True
    assert len(report["benchmark"]["trials"]) == 4
    assert all(t["status"] == "passed" for t in report["benchmark"]["trials"])
    assert report["request"]["conversion"]["assessment_id"] == assessment
    assert (
        client.get(f"/v1/assessments/{assessment}/recommendations").json()["decision"]
        == (report["decision"])
    )
    assert submit(client, payload, "real-pipeline").json()["id"] == assessment
    execute(assessment, config)
    assert status(client, assessment)["attempts"] == 1
    with psycopg.connect(str(config.database_url)) as db:
        kinds = {
            r[0] for r in db.execute("SELECT DISTINCT kind FROM assessment_evidence").fetchall()
        }
        assert kinds == {"profile", "candidates", "experiment", "price_snapshot", "recommendation"}
    print(
        json.dumps(
            {
                "case": "api_rq_storage",
                "assessment_id": assessment,
                "status": state["status"],
                "trials": 4,
                "report_fingerprint": report["report_fingerprint"],
            }
        )
    )


def test_transient_storage_failure_retries_without_duplicate_assessment(services, monkeypatch):
    config, client = services
    assessment = submit(client, submission(client)).json()["id"]
    original = S3Storage.put_file

    def unavailable(*args, **kwargs):
        raise OSError("synthetic transient outage: must not leak into operational log")

    monkeypatch.setattr(S3Storage, "put_file", unavailable)
    execute(assessment, config)
    assert status(client, assessment)["status"] == "queued"
    assert status(client, assessment)["stop_reason"] == "dependency_unavailable"
    monkeypatch.setattr(S3Storage, "put_file", original)
    execute(assessment, config)
    assert status(client, assessment)["status"] == "needs_input"
    assert status(client, assessment)["attempts"] == 2
    assert (
        client.get(f"/v1/assessments/{assessment}/result").json()["evidence"] == "scenario_guidance"
    )


def test_queue_outage_intent_reconciliation_and_duplicate_delivery(services, monkeypatch):
    config, client = services
    payload = submission(client)
    assessment = submit(client, payload).json()["id"]
    import data_optimizer.jobs.service as service

    original = service.queue
    monkeypatch.setattr(service, "queue", lambda _: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(OSError):
        dispatch(config)
    assert status(client, assessment)["status"] == "queued"
    monkeypatch.setattr(service, "queue", original)
    assert dispatch(config) == 1
    # Reconciliation must not grow an unconsumed queue indefinitely.
    with psycopg.connect(str(config.database_url)) as db:
        db.execute("UPDATE assessments SET dispatch_after=now() WHERE id=%s", (assessment,))
    assert dispatch(config) == 0
    assert queue(config).count == 1
    # Reconcile even partial Redis loss: queued job hash survives, list disappears.
    queue(config).connection.delete(queue(config).key)
    with psycopg.connect(str(config.database_url)) as db:
        db.execute("UPDATE assessments SET dispatch_after=now() WHERE id=%s", (assessment,))
    assert dispatch(config) == 1
    assert queue(config).count == 1
    process = worker(config)
    assert process.wait(timeout=30) == 0
    assert status(client, assessment)["status"] == "needs_input"
    execute(assessment, config)
    assert status(client, assessment)["attempts"] == 1


def test_actual_worker_restart_reuses_published_trials(services):
    config, client = services
    payload = submission(client, raw=True)
    payload["request"]["benchmark"]["repeats"] = 3
    assessment = submit(client, payload).json()["id"]
    assert dispatch(config) == 1
    process = worker(config)
    try:
        wait_for(
            lambda: status(client, assessment)["progress"].get("completed_configurations", 0) >= 1
        )
        root = Path(config.assessment_work_dir)
        saved = list(root.rglob("*-benchmark.json"))
        assert saved
        hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in saved}
        # RQ intentionally gives its work horse a separate process group.
        horse = int(
            subprocess.check_output(["ps", "-o", "pid=", "--ppid", str(process.pid)])
            .strip()
            .split()[0]
        )
        os.killpg(horse, signal.SIGKILL)
        assert process.wait(timeout=10) == 0
        with psycopg.connect(str(config.database_url)) as db:
            db.execute(
                "UPDATE assessments SET lease_until=now()-interval '1 second',"
                "dispatch_after=now() WHERE id=%s",
                (assessment,),
            )
        drain(config)
        state = status(client, assessment)
        assert state["status"] == "completed", state
        assert state["attempts"] == 2
        assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in hashes.items())
        report = client.get(f"/v1/assessments/{assessment}/result").json()
        trials = report["benchmark"]["trials"]
        assert len(trials) == 12
        assert len({(t["candidate"], t["repeat"]) for t in trials}) == 12
        print(
            json.dumps(
                {
                    "case": "sigkill_restart",
                    "attempts": 2,
                    "unchanged_published_matrices": len(hashes),
                    "unique_trials": 12,
                }
            )
        )
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def test_active_cancellation_stops_real_sandbox_and_followups(services):
    config, client = services
    payload = submission(client, raw=True)
    payload["request"]["benchmark"]["repeats"] = 5
    assessment = submit(client, payload).json()["id"]
    assert dispatch(config) == 1
    process = worker(config)

    def running_container():
        return subprocess.check_output(
            ["docker", "ps", "-q", "--filter", "label=data-optimizer.job=" + assessment]
        ).strip()

    try:
        wait_for(running_container)
        assert client.post(f"/v1/assessments/{assessment}/cancel").status_code == 202
        assert process.wait(timeout=30) == 0
        state = status(client, assessment)
        assert state["status"] == "cancelled", state
        assert state["stop_reason"] == "user_cancelled"
        assert not running_container()
        assert state["progress"]["completed_configurations"] < 4
        assert dispatch(config) == 0
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def test_result_expiration_deletion_and_retryable_cleanup(services, monkeypatch):
    config, client = services
    payload = submission(client)
    assessment = submit(client, payload).json()["id"]
    execute(assessment, config)
    assert client.get(f"/v1/assessments/{assessment}/result").status_code == 200
    assert client.delete(f"/v1/projects/{payload['project_id']}").status_code == 202
    assert client.get(f"/v1/assessments/{assessment}/result").status_code == 404
    original = S3Storage.delete
    monkeypatch.setattr(S3Storage, "delete", lambda *a: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(OSError):
        cleanup(config)
    monkeypatch.setattr(S3Storage, "delete", original)
    assert cleanup(config) == 1
    assert cleanup(config) == 0
    assert not list(Path(config.assessment_work_dir).rglob("result.json"))
    with psycopg.connect(str(config.database_url)) as db:
        assert db.execute("SELECT count(*) FROM assessment_evidence").fetchone()[0] == 0
        assert db.execute("SELECT cleaned_at IS NOT NULL FROM assessments").fetchone()[0]


def test_cross_project_input_validation_and_bounded_retry_limit(services):
    config, client = services
    first = submission(client, raw=True)
    second = submission(client)
    assert submit(client, {**first, "project_id": second["project_id"]}).status_code == 404
    assert submit(client, {**first, "profile_id": str(uuid4())}).status_code == 422
    bad = {**first, "request": {**first["request"], "conversion": None}}
    assert submit(client, bad).status_code == 422
    assessment = submit(client, second).json()["id"]
    with psycopg.connect(str(config.database_url)) as db:
        db.execute(
            "UPDATE assessments SET attempts=%s WHERE id=%s", (config.max_job_attempts, assessment)
        )
    execute(assessment, config)
    assert status(client, assessment)["stop_reason"] == "attempts_exhausted"


def test_loopback_http_upload_rq_and_result_download(services):
    config, _ = services
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    environment = dict(os.environ)
    for key, value in config.model_dump(mode="json").items():
        if value is not None:
            environment[key.upper()] = str(value)
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "data_optimizer.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-proxy-headers",
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:

        def ready():
            try:
                return client.get("/health").status_code == 200
            except httpx.TransportError:
                return False

        try:
            wait_for(ready, timeout=15)
            payload = submission(client, raw=True)
            response = submit(client, payload, "actual-http")
            assert response.status_code == 202, response.text
            assessment = response.json()["id"]
            drain(config)
            assert status(client, assessment)["status"] == "completed"
            report = client.get(f"/v1/assessments/{assessment}/result").json()
            assert report["decision"]["outcome"] == "change"
            assert (
                client.get(
                    f"/v1/assessments/{assessment}/result", headers={"X-Local-Identity": "bob"}
                ).status_code
                == 404
            )
            print(
                json.dumps(
                    {
                        "case": "loopback_http_upload_rq_result",
                        "status": "completed",
                        "report_fingerprint": report["report_fingerprint"],
                    }
                )
            )
        finally:
            api.terminate()
            api.wait(timeout=10)


def test_reviewed_metadata_guidance_preserves_local_provenance(services):
    from data_optimizer.profiling.models import ProfileOptions
    from data_optimizer.profiling.service import profile_file

    config, client = services
    payload = submission(client)
    report = profile_file(ROOT / "examples/s04-events.ndjson", ProfileOptions(format="ndjson"))
    imported = client.post(
        f"/v1/projects/{payload['project_id']}/profiles",
        json={
            "report": report.model_dump(mode="json"),
            "reviewed_fingerprint": report.profile_fingerprint,
        },
    )
    assert imported.status_code == 201, imported.text
    payload["profile_id"] = imported.json()["profile_id"]
    from data_optimizer.profiling.models import server_profile

    forged = server_profile(report)
    assert (
        client.post(
            f"/v1/projects/{payload['project_id']}/profiles",
            json={
                "report": forged.model_dump(mode="json"),
                "reviewed_fingerprint": forged.profile_fingerprint,
            },
        ).status_code
        == 422
    )
    assessment = submit(client, payload).json()["id"]
    execute(assessment, config)
    assert status(client, assessment)["status"] == "needs_input"
    result = client.get(f"/v1/assessments/{assessment}/result").json()
    assert result["profile"] == report.model_dump(mode="json")
    assert result["benchmark"] is None and result["costs"] == {}
    assert result["decision"]["outcome"] == "insufficient_evidence"


def test_admission_serializes_running_jobs_per_tenant(services):
    config, client = services
    assessment = submit(client, submission(client)).json()["id"]
    with psycopg.connect(str(config.database_url), autocommit=True) as lock:
        tenant = lock.execute(
            "SELECT tenant_id FROM assessments WHERE id=%s", (assessment,)
        ).fetchone()[0]
        lock.execute("SELECT pg_advisory_lock(hashtextextended(%s, 10))", (str(tenant),))
        execute(assessment, config)
        assert status(client, assessment)["attempts"] == 0
        bob = {"X-Local-Identity": "bob"}
        project = client.post("/v1/projects", headers=bob, json={"name": "other tenant"}).json()
        other = client.post(
            "/v1/assessments",
            headers={**bob, "Idempotency-Key": uuid4().hex},
            json={"project_id": project["project_id"], "request": submission(client)["request"]},
        )
        assert other.status_code == 202
        execute(other.json()["id"], config)
        items = client.get("/v1/assessments", headers=bob).json()["items"]
        assert len(items) == 1 and items[0]["status"] == "needs_input"
        lock.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 10))", (str(tenant),))
    execute(assessment, config)
    assert status(client, assessment)["status"] == "needs_input"


def test_request_size_and_expired_result_access(services):
    config, client = services
    assert (
        client.post(
            "/v1/assessments", headers={"Idempotency-Key": "oversized"}, content=b"x" * 524_289
        ).status_code
        == 413
    )
    assessment = submit(client, submission(client)).json()["id"]
    with psycopg.connect(str(config.database_url)) as db:
        db.execute(
            "UPDATE assessments SET expires_at=now()-interval '1 second' WHERE id=%s", (assessment,)
        )
    assert client.get(f"/v1/assessments/{assessment}").status_code == 404
    assert client.get("/v1/assessments").json()["items"] == []
    assert cleanup(config) == 1


def test_reader_clarification_and_quota_failures_are_explicit(services):
    config, client = services
    payload = submission(client, raw=True)
    payload["request"]["conversion"]["source"]["schema_overrides"]["category"] = "decimal"
    assessment = submit(client, payload).json()["id"]
    execute(assessment, config)
    state = status(client, assessment)
    assert state["status"] == "needs_input"
    assert state["stop_reason"] == "schema_override_mismatch"
    del payload["request"]["conversion"]["source"]["schema_overrides"]["category"]
    payload["request"]["conversion"]["source"]["max_raw_bytes"] = 10
    assessment = submit(client, payload).json()["id"]
    execute(assessment, config)
    state = status(client, assessment)
    assert state["status"] == "failed" and state["stop_reason"] == "raw_byte_quota"


def test_operational_commands_report_real_state_and_cleanup(services, monkeypatch, capsys):
    from data_optimizer.cli import main
    from data_optimizer.jobs import commands

    config, client = services
    payload = submission(client)
    assessment = submit(client, payload).json()["id"]
    execute(assessment, config)
    monkeypatch.setattr(commands, "settings", config)
    main(["job-metrics"])
    metrics = json.loads(capsys.readouterr().out)
    assert metrics[0]["status"] == "needs_input" and metrics[0]["count"] == 1
    assert metrics[0]["oldest_age_seconds"] >= 0
    assert client.delete(f"/v1/projects/{payload['project_id']}").status_code == 202
    main(["cleanup-assessments"])
    assert "Cleaned 1 assessment" in capsys.readouterr().out
    main(["dispatch-jobs", "--once"])
    assert queue(config).count == 0
