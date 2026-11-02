"""Real PostgreSQL/MinIO/worker evidence with synthetic manual observations."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from test_assessments import drain, submission, submit

from data_optimizer.economics.models import RECURRING
from data_optimizer.observations.models import ObservationInput

pytestmark = pytest.mark.integration


def observation(**changes):
    data = dict(
        period_start="2026-09-01T00:00:00Z",
        period_end="2026-10-01T00:00:00Z",
        currency="USD",
        logical_volume_bytes=100,
        retained_bytes=50,
        workload_replays="100",
        query_mix={
            q: "0.166666666667" for q in ["scan", "ids", "filter", "nulls", "time", "groups"]
        },
        access_quantities={c: "0" for c in RECURRING},
        itemized_costs={c: "0" for c in RECURRING},
        source="Synthetic bill",
        coverage="All eleven costs; identical boundary",
        note="Invented arithmetic",
    )
    data.update(changes)
    return ObservationInput.model_validate(data)


def adoption(client, assessment, **changes):
    data = dict(
        expected_version=0,
        state="proposed",
        reference_logical_bytes=287,
        source="Synthetic integration adoption",
        note="No real production switch",
    )
    data.update(changes)
    return client.post(f"/v1/assessments/{assessment}/migration-plan", json=data)


def deployed_plan(client, assessment):
    response = adoption(client, assessment)
    assert response.status_code == 200, response.text
    plan = response.json()["id"]
    assert adoption(client, assessment, expected_version=1, state="planned").status_code == 200
    response = adoption(
        client,
        assessment,
        expected_version=2,
        state="deployed",
        deployed_at="2026-08-01T00:00:00Z",
        actual_migration_cost="5",
    )
    assert response.status_code == 200, response.text
    return plan


def test_real_adoption_revisions_negative_costs_revert_and_immutability(services):
    config, client = services
    payload = submission(client, raw=True)
    assessment = submit(client, payload).json()["id"]
    drain(config)
    original = client.get(f"/v1/assessments/{assessment}/result").content
    plan = deployed_plan(client, assessment)
    url = f"/v1/migration-plans/{plan}/observations"
    obs = observation(
        logical_volume_bytes=287, itemized_costs={c: "1000" for c in RECURRING}
    ).model_dump(mode="json")
    saved = client.post(url, json=obs)
    assert saved.status_code == 200, saved.text
    entry = saved.json()
    history_url = f"/v1/migration-plans/{plan}/history"
    history = client.get(history_url).json()
    calculation = history["observations"][0]["calculation"]
    assert Decimal(calculation["actual_cost"]) == 11000
    assert Decimal(calculation["modeled_savings"]) < 0
    assert (
        Decimal(history["cumulative_modeled_benefit"])
        == Decimal(calculation["modeled_savings"]) - 5
    )
    second = {**obs, "period_start": "2026-10-01T00:00:00Z", "period_end": "2026-11-01T00:00:00Z"}
    assert client.post(url, json=second).status_code == 200
    history = client.get(history_url).json()
    expected_total = (
        sum(Decimal(r["calculation"]["modeled_savings"]) for r in history["observations"]) - 5
    )
    assert Decimal(history["cumulative_modeled_benefit"]) == expected_total
    assert history["plan"]["configuration"]
    assert history["plan"]["report_fingerprint"]
    assert client.post(url, json=obs).status_code == 409  # No duplicate/overlapping spend.
    edited = {
        **obs,
        "observation_id": entry["id"],
        "expected_version": 1,
        "itemized_costs": {"storage": "5"},
        "note": "Partial bill revision",
    }
    assert client.post(url, json=edited).status_code == 200
    assert client.post(url, json=edited).status_code == 409
    history = client.get(history_url).json()
    assert len(history["observation_revisions"]) == 3
    assert history["observations"][0]["version"] == 2
    assert history["observations"][0]["calculation"]["actual_cost"] is None
    assert history["cumulative_modeled_benefit"] is None
    # A revision can exclude a bad entry; prior payload remains retained.
    assert (
        client.post(url, json={**edited, "expected_version": 2, "excluded": True}).status_code
        == 200
    )
    assert (
        adoption(
            client,
            assessment,
            expected_version=3,
            state="reverted",
            deployed_at="2026-08-01T00:00:00Z",
            reverted_at="2026-09-15T00:00:00Z",
            actual_migration_cost="5",
        ).status_code
        == 200
    )
    assert (
        client.post(
            url,
            json={
                **obs,
                "period_start": "2026-10-01T00:00:00Z",
                "period_end": "2026-10-02T00:00:00Z",
            },
        ).status_code
        == 422
    )
    assert (
        adoption(
            client,
            assessment,
            expected_version=4,
            state="deployed",
            deployed_at="2026-08-01T00:00:00Z",
        ).status_code
        == 422
    )
    assert client.get(f"/v1/assessments/{assessment}/result").content == original
    with psycopg.connect(str(config.database_url)) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE resource_id=%s", (plan,)
            ).fetchone()[0]
            == 8
        )
    for table in ["migration_plans", "migration_plan_versions", "observations"]:
        with (
            pytest.raises(psycopg.errors.RaiseException),
            psycopg.connect(str(config.database_url)) as db,
        ):
            db.execute(f"UPDATE {table} SET tenant_id=tenant_id")
        with (
            pytest.raises(psycopg.errors.RaiseException),
            psycopg.connect(str(config.database_url)) as db,
        ):
            db.execute(f"DELETE FROM {table}")
    for method, path, body in [
        ("GET", history_url, None),
        ("POST", url, obs),
        ("GET", f"/v1/assessments/{assessment}/migration-plan", None),
        ("POST", f"/v1/assessments/{assessment}/migration-plan", {}),
    ]:
        assert (
            client.request(method, path, json=body, headers={"X-Local-Identity": "bob"}).status_code
            == 404
        )
    assert client.delete(f"/v1/datasets/{payload['dataset_id']}").status_code == 202
    assert client.get(history_url).status_code == 404


def test_reassessment_is_new_owned_idempotent_version_with_original_unchanged(services):
    config, client = services
    payload = submission(client)
    first = submit(client, payload).json()["id"]
    drain(config)
    original = client.get(f"/v1/assessments/{first}/result").content
    changed = {
        **payload,
        "reassessment_of": first,
        "reassessment_reason": "Changed price assumptions",
    }
    changed["request"]["policy"]["minimum_net_savings"] = "12"
    key = uuid4().hex
    response = submit(client, changed, key)
    assert response.status_code == 202, response.text
    second = response.json()["id"]
    assert first != second
    assert submit(client, changed, key).json()["id"] == second
    assert (
        submit(client, {**changed, "reassessment_reason": "Another reason"}, key).status_code == 409
    )
    drain(config)
    comparison = client.get(f"/v1/assessments/{second}/comparison").json()
    assert comparison["previous"]["id"] == first
    assert comparison["current"]["id"] == second
    assert comparison["current"]["decision"]["policy"]["minimum_net_savings"] == "12"
    assert (
        comparison["previous"]["request_fingerprint"]
        != comparison["current"]["request_fingerprint"]
    )
    assert client.get(f"/v1/assessments/{first}/result").content == original
    assert (
        client.get(
            f"/v1/assessments/{second}/comparison", headers={"X-Local-Identity": "bob"}
        ).status_code
        == 404
    )
    other = submission(client)
    assert (
        submit(
            client, {**other, "reassessment_of": first, "reassessment_reason": "Wrong project"}
        ).status_code
        == 422
    )
    assert (
        submit(
            client, {**payload, "reassessment_of": str(uuid4()), "reassessment_reason": "No owner"}
        ).status_code
        == 404
    )
    assert submit(client, {**payload, "reassessment_of": first}).status_code == 422
    assert adoption(client, first).status_code == 409
    with (
        pytest.raises(psycopg.errors.RaiseException),
        psycopg.connect(str(config.database_url)) as db,
    ):
        db.execute("UPDATE reassessment_links SET reason='mutated'")


def test_plan_conflict_and_bounded_entry(services):
    config, client = services
    payload = submission(client, raw=True)
    assessment = submit(client, payload).json()["id"]
    drain(config)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: adoption(client, assessment), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert (
        adoption(client, assessment, expected_version=1, reference_logical_bytes=100).status_code
        == 422
    )
    assert (
        adoption(
            client,
            assessment,
            expected_version=1,
            state="deployed",
            deployed_at="2026-08-01T00:00:00Z",
        ).status_code
        == 422
    )
    path = f"/v1/assessments/{assessment}/migration-plan"
    assert client.post(path, content=b"x" * 131073).status_code == 413
    plan = client.get(path).json()["plan"]["id"]
    assert (
        client.post(
            f"/v1/migration-plans/{plan}/observations", json=observation().model_dump(mode="json")
        ).status_code
        == 422
    )
    with psycopg.connect(str(config.database_url)) as db:
        db.execute(
            "UPDATE assessments SET expires_at=now()-interval '1 second' WHERE id=%s", (assessment,)
        )
    assert client.get(f"/v1/migration-plans/{plan}/history").status_code == 404
