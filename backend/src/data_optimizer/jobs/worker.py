"""RQ entry point. Only this process needs Docker and private workspace access."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from data_optimizer.config import Settings, settings
from data_optimizer.jobs.service import remove_orphan_containers, work_directory
from data_optimizer.optimization.assessment import (
    AssessmentReport,
    AssessmentRequest,
    Session,
    assess,
)
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import fingerprint
from data_optimizer.readers.stream import ProfileError
from data_optimizer.storage.s3 import S3Storage

logger = logging.getLogger(__name__)
CLARIFICATION_REASONS = {
    "schema_override_mismatch",
    "time_column_requires_timestamp_override",
    "unknown_configured_field",
    "strata_quota_choose_coarser_or_full_scan",
}
QUOTA_REASONS = {
    "raw_byte_quota",
    "decoded_byte_quota",
    "record_byte_quota",
    "column_quota",
    "profile_time_quota",
    "profile_memory_quota",
    "profile_resource_quota",
    "conversion_output_byte_quota",
    "conversion_row_quota",
    "conversion_file_count_quota",
    "result_byte_quota",
}


def evidence(db: psycopg.Connection[Any], row: dict[str, Any], kind: str, payload: Any) -> None:
    if payload is None:
        return
    data = payload.model_dump(mode="json")
    db.execute(
        "INSERT INTO assessment_evidence (tenant_id,assessment_id,kind,fingerprint,payload) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (row["tenant_id"], row["id"], kind, fingerprint(data), Jsonb(data)),
    )


def workspace_bytes(directory: Path) -> int:
    size = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                size += path.stat().st_size
        except FileNotFoundError:
            continue  # Concurrent temporary-file cleanup is expected.
    return size


def execute(assessment_id: str, config: Settings | None = None) -> None:
    config = config or settings
    assessment = UUID(assessment_id)
    # Session advisory locks survive commits and fence concurrent/stale deliveries.
    with psycopg.connect(
        str(config.database_url), row_factory=dict_row, autocommit=True, connect_timeout=5
    ) as db:
        lock = db.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 9)) AS ok", (str(assessment),)
        ).fetchone()
        assert lock
        if not lock["ok"]:
            return
        row = db.execute("SELECT * FROM assessments WHERE id=%s", (assessment,)).fetchone()
        if row is None or row["status"] not in ("queued", "profiling", "benchmarking", "scoring"):
            return
        # One running assessment per tenant; bounded FIFO admission across tenants.
        lock = db.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 10)) AS ok", (str(row["tenant_id"]),)
        ).fetchone()
        assert lock
        if not lock["ok"]:
            return
        token = uuid4()
        if row["attempts"] >= config.max_job_attempts:
            db.execute(
                "UPDATE assessments SET status='failed',stop_reason='attempts_exhausted',"
                "updated_at=now() WHERE id=%s",
                (assessment,),
            )
            return
        row = db.execute(
            """UPDATE assessments SET status='profiling',attempts=attempts+1,lease_token=%s,
            lease_until=now()+(%s * interval '1 second'),updated_at=now(),stop_reason=NULL
            WHERE id=%s RETURNING *""",
            (token, config.job_lease_seconds, assessment),
        ).fetchone()
        assert row
        directory = work_directory(config, row)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        stopped, done = threading.Event(), threading.Event()
        stop_reason = ["user_cancelled"]
        started = time.monotonic()

        def pulse() -> None:
            try:
                with psycopg.connect(
                    str(config.database_url), row_factory=dict_row, connect_timeout=3
                ) as heart:
                    live = heart.execute(
                        """SELECT a.cancel_requested,a.expires_at<=now() AS expired,
                        p.deleted_at IS NOT NULL AS project_deleted,
                        (d.id IS NOT NULL AND (d.state<>'ready' OR d.expires_at<=now()))
                        AS data_gone,
                        (f.id IS NOT NULL AND f.deleted_at IS NOT NULL) AS profile_gone
                        FROM assessments a JOIN projects p ON p.id=a.project_id
                        LEFT JOIN datasets d ON d.id=a.dataset_id
                        LEFT JOIN profiles f ON f.id=a.profile_id
                        WHERE a.id=%s AND lease_token=%s""",
                        (assessment, token),
                    ).fetchone()
                    if live is None or any(live.values()):
                        stopped.set()
                    elif time.monotonic() - started >= config.max_assessment_seconds:
                        stop_reason[0] = "assessment_time_quota"
                        stopped.set()
                    elif workspace_bytes(directory) > (config.max_job_workspace_bytes):
                        stop_reason[0] = "workspace_byte_quota"
                        stopped.set()
                    heart.execute(
                        "UPDATE assessments SET lease_until=now()+(%s * interval '1 second') "
                        "WHERE id=%s AND lease_token=%s",
                        (config.job_lease_seconds, assessment, token),
                    )
            except (psycopg.Error, OSError):
                stop_reason[0] = "dependency_unavailable"
                stopped.set()  # Fail closed if cancellation/ownership cannot be checked.

        def heartbeat() -> None:
            while not done.wait(1):
                pulse()

        def progress(stage: str, session: Session | None) -> None:
            pulse()
            counts: dict[str, Any] = {
                "stage": stage,
                "completed_configurations": 0,
                "completed_trials": 0,
                "passed_trials": 0,
            }
            if session:
                counts["completed_configurations"] = len(session.search.history)
                counts["proposed_configurations"] = len(session.search.configurations)
                counts["search_stop_reason"] = session.search.stop_reason
                if session.benchmark:
                    counts["completed_trials"] = len(session.benchmark.trials)
                    counts["passed_trials"] = sum(
                        t.status == "passed" for t in session.benchmark.trials
                    )
            with db.transaction():
                db.execute(
                    "UPDATE assessments SET status=%s,progress=%s,updated_at=now() "
                    "WHERE id=%s AND lease_token=%s",
                    (stage, Jsonb(counts), assessment, token),
                )
                if session:
                    evidence(db, row, "profile", session.profile)
                    evidence(db, row, "candidates", session.candidates)
                    evidence(db, row, "experiment", session.benchmark)
            logger.info(
                "assessment_stage id=%s stage=%s trials=%s",
                assessment,
                stage,
                counts["completed_trials"],
            )

        thread = threading.Thread(target=heartbeat, daemon=True)
        previous_scope = os.environ.get("DATA_OPTIMIZER_JOB_SCOPE")
        previous_tmp = os.environ.get("TMPDIR")
        previous_tempdir = tempfile.tempdir
        temporary_root = directory / "temporary"
        temporary_root.mkdir(exist_ok=True, mode=0o700)
        os.environ["TMPDIR"] = str(temporary_root)
        tempfile.tempdir = str(temporary_root)
        os.environ["DATA_OPTIMIZER_JOB_SCOPE"] = str(assessment)
        report: AssessmentReport | None = None
        try:
            pulse()
            thread.start()
            request = AssessmentRequest.model_validate(row["request"])
            if row["dataset_id"]:
                remove_orphan_containers(str(assessment))
            source = metadata = None
            if not stopped.is_set() and row["dataset_id"]:
                artifact = db.execute(
                    "SELECT object_key,byte_count,sha256 FROM artifacts WHERE tenant_id=%s "
                    "AND dataset_id=%s AND state='ready'",
                    (row["tenant_id"], row["dataset_id"]),
                ).fetchone()
                if not artifact:
                    raise ProfileError("dataset_unavailable")
                source = directory / "source"
                if (
                    not source.exists()
                    or input_digest(source, config.max_raw_upload_bytes)
                    != (row["input_fingerprint"])
                ):
                    temporary = directory / ".source"
                    body = S3Storage(config).get(artifact["object_key"])
                    try:
                        with temporary.open("wb") as download:
                            size = 0
                            while chunk := body.read(65536):
                                size += len(chunk)
                                if size > config.max_raw_upload_bytes or stopped.is_set():
                                    raise ProfileError("download_stopped")
                                download.write(chunk)
                        if (
                            size != artifact["byte_count"]
                            or input_digest(temporary, config.max_raw_upload_bytes)
                            != row["input_fingerprint"]
                        ):
                            raise ProfileError("input_fingerprint_mismatch")
                        temporary.replace(source)
                    finally:
                        body.close()
                        temporary.unlink(missing_ok=True)
            elif not stopped.is_set() and row["profile_id"]:
                profile = db.execute(
                    "SELECT payload FROM profiles WHERE tenant_id=%s AND id=%s",
                    (row["tenant_id"], row["profile_id"]),
                ).fetchone()
                assert profile
                metadata = directory / "metadata.json"
                import json

                if profile["payload"].get("profile_fingerprint") != row["input_fingerprint"]:
                    raise ProfileError("metadata_fingerprint_mismatch")
                metadata.write_text(json.dumps(profile["payload"]))
            if not stopped.is_set():
                report = assess(
                    source,
                    directory / "pipeline",
                    request,
                    metadata=metadata,
                    cancelled=stopped.is_set,
                    progress=progress,
                    server_execution=True,
                )
            pulse()  # Recheck cancellation/retention immediately before publishing.
            if stopped.is_set() and stop_reason[0] == "dependency_unavailable":
                raise OSError("heartbeat_dependency_unavailable")
            if report:
                output = directory / "result.json"
                output.write_text(report.model_dump_json())
                if output.stat().st_size > 67_108_864:
                    raise ProfileError("result_byte_quota")
                key = f"tenants/{row['tenant_id']}/assessments/{assessment}/result.json"
                S3Storage(config).put_file(key, output, output.stat().st_size)
                with db.transaction():
                    # Row lock gives cancel and publication a defined ordering.
                    live = db.execute(
                        "SELECT cancel_requested FROM assessments WHERE id=%s "
                        "AND lease_token=%s FOR UPDATE",
                        (assessment, token),
                    ).fetchone()
                    assert live
                    cancelled = stopped.is_set() or live["cancel_requested"]
                    status = (
                        "cancelled"
                        if cancelled
                        else (
                            "needs_input"
                            if report.decision.outcome == "insufficient_evidence"
                            else "completed"
                        )
                    )
                    reason = (
                        stop_reason[0]
                        if cancelled
                        else (report.search.stop_reason if report.search else "scenario_guidance")
                    )
                    evidence(db, row, "profile", report.profile)
                    evidence(db, row, "recommendation", report.decision)
                    if request.cost_template:
                        for scenario in request.cost_template.scenarios:
                            evidence(db, row, "price_snapshot", scenario.prices)
                    db.execute(
                        """UPDATE assessments SET status=%s,stop_reason=%s,result_key=%s,
                        result_sha256=%s,result_bytes=%s,lease_until=NULL,updated_at=now()
                        WHERE id=%s AND lease_token=%s""",
                        (
                            status,
                            reason,
                            key,
                            hashlib.sha256(output.read_bytes()).hexdigest(),
                            output.stat().st_size,
                            assessment,
                            token,
                        ),
                    )
            else:
                db.execute(
                    "UPDATE assessments SET status='cancelled',stop_reason=%s,"
                    "lease_until=NULL,updated_at=now() WHERE id=%s AND lease_token=%s",
                    (stop_reason[0], assessment, token),
                )
        except Exception as error:
            transient = isinstance(error, (psycopg.Error, BotoCoreError, ClientError, OSError))
            retry = transient and row["attempts"] < config.max_job_attempts
            reason = "dependency_unavailable" if transient else "invalid_input_or_pipeline_failure"
            if isinstance(error, ProfileError) and str(error) in (
                CLARIFICATION_REASONS | QUOTA_REASONS
            ):
                reason = str(error)
            if stopped.is_set() and stop_reason[0] != "dependency_unavailable":
                status, reason = "cancelled", stop_reason[0]
            else:
                status = (
                    "needs_input"
                    if reason in CLARIFICATION_REASONS
                    else ("queued" if retry else "failed")
                )
            db.execute(
                "UPDATE assessments SET status=%s,stop_reason=%s,lease_until=NULL,"
                "dispatch_after=now()+(%s * interval '1 second'),updated_at=now() "
                "WHERE id=%s AND lease_token=%s",
                (status, reason, min(60, 2 ** row["attempts"]), assessment, token),
            )
            logger.warning(
                "assessment_stopped id=%s status=%s reason=%s", assessment, status, reason
            )
        finally:
            done.set()
            if thread.is_alive():
                thread.join(timeout=5)
            tempfile.tempdir = previous_tempdir
            if previous_tmp is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = previous_tmp
            if previous_scope is None:
                os.environ.pop("DATA_OPTIMIZER_JOB_SCOPE", None)
            else:
                os.environ["DATA_OPTIMIZER_JOB_SCOPE"] = previous_scope
