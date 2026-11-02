"""Actual stored evidence, authenticated downloads, expiry, deletion and local replay."""

import json
import os
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import psycopg
import pytest
from test_assessments import drain, submission, submit

from data_optimizer.reports.service import read_bundle

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


def test_real_download_and_reproduction_with_confirmation(services, tmp_path):
    config, client = services
    payload = submission(client, raw=True)
    project = payload["project_id"]
    proposal = client.post(
        f"/v1/projects/{project}/intake",
        json={
            "description": "PRIVATE_DESCRIPTION_SECRET retention 7 days",
            "request": payload["request"],
        },
    ).json()
    confirmation = client.post(
        f"/v1/projects/{project}/intake/{proposal['id']}/confirm",
        json={"request": payload["request"]},
    ).json()
    payload["intake_confirmation_id"] = confirmation["id"]
    assessment = submit(client, payload).json()["id"]
    drain(config)
    raw = client.get(f"/v1/assessments/{assessment}/result")
    assert raw.status_code == 200
    response = client.post(f"/v1/assessments/{assessment}/handoff")
    assert response.status_code == 200, response.text
    grant = response.json()
    documents = {}
    for kind, link in grant["links"].items():
        exported = client.get(link)
        assert exported.status_code == 200, exported.text
        assert exported.headers["cache-control"] == "no-store"
        assert "attachment" in exported.headers["content-disposition"]
        documents[kind] = exported.content
        assert client.get(link, headers={"X-Local-Identity": "bob"}).status_code == 404
        assert b"PRIVATE_DESCRIPTION_SECRET" not in exported.content
    assert (
        client.post(
            f"/v1/assessments/{assessment}/handoff", headers={"X-Local-Identity": "bob"}
        ).status_code
        == 404
    )
    bundle = read_bundle(documents["json"])
    assert bundle.bundle_fingerprint == grant["bundle_fingerprint"]
    assert bundle.provenance.confirmation_id == confirmation["id"]
    assert bundle.provenance.confirmation_version == 1
    assert bundle.original_report_fingerprint == raw.json()["report_fingerprint"]
    assert bundle.decision.outcome == "change"
    assert client.get(f"/v1/assessments/{assessment}/result").content == raw.content
    destination = tmp_path / "export ' $() space"
    destination.mkdir()
    with zipfile.ZipFile(BytesIO(documents["zip"])) as z:
        z.extractall(destination)
    assert (destination / "bundle.json").read_bytes() == documents["json"]
    source = tmp_path / "local source ' $(touch BAD) `touch BAD` .ndjson"
    source.write_bytes((ROOT / "examples/s04-events.ndjson").read_bytes())
    environment = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + ":" + os.environ["PATH"],
    }
    migrated = subprocess.run(
        [
            "sh",
            str(destination / "migrate.sh"),
            str(source),
            str(tmp_path / "migration"),
            str(tmp_path / "migration.json"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=90,
    )
    assert migrated.returncode == 0, migrated.stderr
    migration = json.loads((tmp_path / "migration.json").read_bytes())
    assert migration["source_preserved"] is True
    assert migration["production_reader_switched"] is False
    assert migration["outcome"]["manifest"]["integrity"]["status"] == "passed"
    replayed = subprocess.run(
        [
            sys.executable,
            "-m",
            "data_optimizer.cli",
            "reproduce",
            str(destination / "bundle.json"),
            "--source",
            str(source),
            "--root",
            str(tmp_path / "replay"),
            "--output",
            str(tmp_path / "replayed.json"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
    )
    assert replayed.returncode == 0, replayed.stderr
    replay = json.loads((tmp_path / "replayed.json").read_bytes())
    assert replay["matches_original_decision"] and replay["source_preserved"]
    assert not (tmp_path / "BAD").exists()
    with psycopg.connect(str(config.database_url)) as db:
        db.execute(
            "UPDATE assessment_downloads SET created_at=now()-interval '2 hours', "
            "expires_at=now()-interval '1 hour'"
        )
    assert client.get(grant["links"]["json"]).status_code == 404
    fresh = client.post(f"/v1/assessments/{assessment}/handoff").json()
    assert client.get(fresh["links"]["json"]).content == documents["json"]
    assert client.get(grant["links"]["json"]).status_code == 404
    assert client.delete(f"/v1/datasets/{payload['dataset_id']}").status_code == 202
    assert client.get(fresh["links"]["json"]).status_code == 404


def test_guidance_export_and_unavailable_result(services):
    config, client = services
    assessment = submit(client, submission(client)).json()["id"]
    assert client.post(f"/v1/assessments/{assessment}/handoff").status_code == 409
    drain(config)
    grant = client.post(f"/v1/assessments/{assessment}/handoff").json()
    bundle = read_bundle(client.get(grant["links"]["json"]).content)
    assert bundle.evidence == "scenario_guidance"
    assert bundle.input_fingerprint is None
    assert bundle.decision.outcome == "insufficient_evidence"
    with psycopg.connect(str(config.database_url)) as db:
        db.execute(
            "UPDATE assessments SET expires_at=now()-interval '1 second' WHERE id=%s", (assessment,)
        )
    assert client.get(grant["links"]["zip"]).status_code == 404
    assert client.post(f"/v1/assessments/{assessment}/handoff").status_code == 404
