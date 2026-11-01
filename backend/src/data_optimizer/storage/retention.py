"""Retryable expiration/deletion of app-owned original dataset copies."""

from __future__ import annotations

from uuid import uuid4

import psycopg

from data_optimizer.config import Settings
from data_optimizer.storage.s3 import S3Storage


def cleanup_expired(config: Settings, batch_size: int = 100) -> tuple[int, int]:
    """Delete expired/tombstoned objects, preserving tombstones until S3 confirms delete."""
    with psycopg.connect(str(config.database_url)) as connection:
        with connection.transaction():
            rows = connection.execute(
                """SELECT u.tenant_id::text, u.dataset_id::text, u.id::text, u.object_key
                   FROM upload_sessions u JOIN datasets d
                     ON d.tenant_id = u.tenant_id AND d.id = u.dataset_id
                   WHERE u.state <> 'deleted' AND
                     ((u.state <> 'complete' AND u.expires_at <= now()) OR d.expires_at <= now()
                      OR u.state IN ('failed','delete_pending') OR d.state = 'delete_pending')
                   ORDER BY u.created_at LIMIT %s FOR UPDATE OF d SKIP LOCKED""",
                (batch_size,),
            ).fetchall()
            for tenant_id, dataset_id, session_id, _object_key in rows:
                connection.execute(
                    """UPDATE upload_sessions SET state = 'delete_pending', updated_at = now()
                       WHERE tenant_id = %s AND id = %s AND state <> 'deleted'""",
                    (tenant_id, session_id),
                )
                connection.execute(
                    """UPDATE datasets SET state = 'delete_pending',
                       deleted_at = COALESCE(deleted_at, now())
                       WHERE tenant_id = %s AND id = %s AND state <> 'deleted'""",
                    (tenant_id, dataset_id),
                )
                connection.execute(
                    """UPDATE artifacts SET state = 'delete_pending'
                       WHERE tenant_id = %s AND dataset_id = %s AND state <> 'deleted'""",
                    (tenant_id, dataset_id),
                )

    deleted = 0
    failed = 0
    storage = S3Storage(config)
    for tenant_id, dataset_id, session_id, object_key in rows:
        expected_key = f"tenants/{tenant_id}/datasets/{dataset_id}/uploads/{session_id}/original"
        if object_key != expected_key:
            failed += 1
            continue
        try:
            storage.delete(object_key)
        except Exception:
            failed += 1
            continue
        with psycopg.connect(str(config.database_url)) as connection:
            with connection.transaction():
                connection.execute(
                    """UPDATE upload_sessions SET state = 'deleted', updated_at = now()
                       WHERE tenant_id = %s AND id = %s AND state = 'delete_pending'""",
                    (tenant_id, session_id),
                )
                connection.execute(
                    """UPDATE artifacts SET state = 'deleted', deleted_at = now()
                       WHERE tenant_id = %s AND dataset_id = %s AND state = 'delete_pending'""",
                    (tenant_id, dataset_id),
                )
                connection.execute(
                    """UPDATE datasets SET state = 'deleted'
                       WHERE tenant_id = %s AND id = %s AND state = 'delete_pending'""",
                    (tenant_id, dataset_id),
                )
                connection.execute(
                    """INSERT INTO audit_events
                       (id, tenant_id, resource_type, resource_id, action, details)
                       VALUES (%s,%s,'dataset',%s,'copy_deleted',
                               '{"scope":"stored assessment copy only"}'::jsonb)""",
                    (uuid4(), tenant_id, dataset_id),
                )
        deleted += 1
    return deleted, failed
