"""PostgreSQL dispatch outbox, bounded recovery and tenant fair admission."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.serializers import JSONSerializer

from data_optimizer.config import Settings
from data_optimizer.sandbox.docker import control
from data_optimizer.storage.s3 import S3Storage

logger = logging.getLogger(__name__)
ACTIVE = "('queued','profiling','benchmarking','scoring')"


def queue(config: Settings) -> Queue:
    return Queue(
        config.assessment_queue,
        connection=Redis.from_url(str(config.redis_url)),
        serializer=JSONSerializer,
    )


def dispatch(config: Settings) -> int:
    """Commit enqueue after durable intent. Lost/duplicate deliveries are harmless.

    Reconcile periodically even after successful dispatch: Redis may lose a queued job.
    One oldest due row per tenant, ordered by last delivery, bounds queue dominance.
    """
    delivered = 0
    with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
        rows = db.execute(
            f"""SELECT DISTINCT ON (tenant_id) id,tenant_id,dispatched_at,created_at
            FROM assessments WHERE status IN {ACTIVE} AND dispatch_after<=now()
            AND (lease_until IS NULL OR lease_until<now()) AND expires_at>now()
            ORDER BY tenant_id,created_at"""
        ).fetchall()
        rows.sort(key=lambda r: r["dispatched_at"] or r["created_at"])
        for row in rows:
            # A per-row transactional lock serializes concurrent dispatchers.
            locked = db.execute(
                "SELECT id FROM assessments WHERE id=%s AND dispatch_after<=now() "
                "FOR UPDATE SKIP LOCKED",
                (row["id"],),
            ).fetchone()
            if not locked:
                continue
            target = queue(config)
            job_id = "assessment-" + str(row["id"])
            try:
                job = Job.fetch(job_id, connection=target.connection, serializer=JSONSerializer)
                if job.get_status() in ("queued", "started"):
                    # A stale started RQ record after SIGKILL must not suppress durable recovery.
                    if job.get_status() == "queued" and target.get_job_position(job_id) is not None:
                        db.execute(
                            "UPDATE assessments SET dispatch_after=now()+"
                            "(%s * interval '1 second') WHERE id=%s",
                            (config.job_lease_seconds, row["id"]),
                        )
                        continue
                job.delete()
            except NoSuchJobError:
                pass
            target.enqueue(
                "data_optimizer.jobs.worker.execute",
                str(row["id"]),
                job_id=job_id,
                job_timeout=config.max_assessment_seconds + 60,
                result_ttl=0,
                failure_ttl=3600,
                description="assessment " + str(row["id"]),
            )
            db.execute(
                "UPDATE assessments SET dispatched_at=now(),dispatch_after=now()+"
                "(%s * interval '1 second') WHERE id=%s",
                (config.job_lease_seconds, row["id"]),
            )
            delivered += 1
    logger.info("dispatch completed count=%s", delivered)
    return delivered


def work_directory(config: Settings, row: dict[str, Any]) -> Path:
    return Path(config.assessment_work_dir).resolve() / str(row["tenant_id"]) / str(row["id"])


def remove_orphan_containers(scope: str) -> None:
    """Run only while holding the assessment lock, never remove unrelated containers."""
    found = control(["ps", "-aq", "--filter", "label=data-optimizer.job=" + scope])
    for container in found.split():
        control(["rm", "--force", container])


def cleanup(config: Settings) -> int:
    """Retry private result/workspace deletion after expiration or source tombstones."""
    cleaned = 0
    with psycopg.connect(str(config.database_url), row_factory=dict_row) as db:
        rows = db.execute(
            """SELECT a.* FROM assessments a JOIN projects p ON p.id=a.project_id
            LEFT JOIN datasets d ON d.id=a.dataset_id LEFT JOIN profiles f ON f.id=a.profile_id
            WHERE a.cleaned_at IS NULL AND (a.expires_at<=now() OR p.deleted_at IS NOT NULL
            OR d.state IN ('delete_pending','deleted') OR d.expires_at<=now()
            OR f.deleted_at IS NOT NULL)"""
        ).fetchall()
        for row in rows:
            db.execute(
                "UPDATE assessments SET cancel_requested=true, status=CASE WHEN status='queued' "
                "THEN 'cancelled' ELSE status END WHERE id=%s",
                (row["id"],),
            )
        db.commit()
        for row in rows:
            # Same lock as the worker: never remove an active process's files.
            lock = db.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 9)) AS ok", (str(row["id"]),)
            ).fetchone()
            assert lock
            if not lock["ok"]:
                continue
            try:
                if row["dataset_id"]:
                    remove_orphan_containers(str(row["id"]))
                # Deterministic result key also removes uploads orphaned before DB publication.
                S3Storage(config).delete(
                    f"tenants/{row['tenant_id']}/assessments/{row['id']}/result.json"
                )
                directory = work_directory(config, row)
                if directory.exists():
                    shutil.rmtree(directory)
                db.execute("DELETE FROM assessment_evidence WHERE assessment_id=%s", (row["id"],))
                db.execute(
                    "UPDATE assessments SET cleaned_at=now(),result_key=NULL,result_sha256=NULL,"
                    "result_bytes=NULL,status=CASE WHEN status IN "
                    + ACTIVE
                    + " THEN 'cancelled' ELSE status END,"
                    "stop_reason='retention_cleanup' WHERE id=%s",
                    (row["id"],),
                )
                db.commit()
                cleaned += 1
            finally:
                db.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 9))", (str(row["id"]),))
    return cleaned
