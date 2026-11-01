"""Idempotent local-only identities with no customer records."""

from uuid import UUID

import psycopg

DEMO_IDENTITIES = (
    (
        UUID("11111111-1111-4111-8111-111111111111"),
        "Local demo Alice",
        UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        "alice",
    ),
    (
        UUID("22222222-2222-4222-8222-222222222222"),
        "Local demo Bob",
        UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        "bob",
    ),
)


def seed_local(database_url: str) -> None:
    """Insert fixed demo tenants/principals; never overwrite existing mappings."""
    with psycopg.connect(database_url) as connection:
        for tenant_id, tenant_name, principal_id, selector in DEMO_IDENTITIES:
            connection.execute(
                "INSERT INTO tenants (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                (tenant_id, tenant_name),
            )
            connection.execute(
                """INSERT INTO principals (id, tenant_id, issuer, subject)
                   VALUES (%s, %s, 'local-demo', %s)
                   ON CONFLICT (issuer, subject) DO NOTHING""",
                (principal_id, tenant_id, selector),
            )
