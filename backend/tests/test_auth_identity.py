from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from data_optimizer.auth.identity import Identity, authenticate
from data_optimizer.config import Settings

ISSUER = "https://identity.example.test"
AUDIENCE = "data-optimizer-api"


def request_from(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request(
        {
            "type": "http",
            "headers": headers,
            "client": (peer, 1234),
            "server": ("127.0.0.1", 80),
        }
    )


@pytest.fixture
def signing_material() -> tuple[Settings, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    config = Settings(
        auth_mode="jwt",
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
        auth_public_key=public_key,
    )
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return config, private_pem


def signed_token(private_key: str, **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "external-user-1",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


class PrincipalDatabase:
    def __init__(self, row: tuple[str, str] | None) -> None:
        self.row = row
        self.parameters: tuple[str, str] | None = None

    def __enter__(self) -> PrincipalDatabase:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, query: str, parameters: tuple[str, str]) -> PrincipalDatabase:
        assert "FROM principals" in query
        self.parameters = parameters
        return self

    def fetchone(self) -> tuple[str, str] | None:
        return self.row


def install_database_stub(
    monkeypatch: pytest.MonkeyPatch,
    row: tuple[str, str] | None,
) -> list[PrincipalDatabase]:
    import data_optimizer.auth.identity as identity_module

    connections: list[PrincipalDatabase] = []

    def connect(_database_url: str, *, connect_timeout: int) -> PrincipalDatabase:
        assert connect_timeout == 3
        connection = PrincipalDatabase(row)
        connections.append(connection)
        return connection

    monkeypatch.setattr(identity_module.psycopg, "connect", connect)
    return connections


def test_valid_rsa_token_maps_to_database_principal_and_tenant(
    signing_material: tuple[Settings, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, private_key = signing_material
    connections = install_database_stub(monkeypatch, ("principal-7", "tenant-2"))
    token = signed_token(private_key, tenant_id="untrusted-tenant-claim")

    result = authenticate(
        request_from("127.0.0.1"), f"Bearer {token}", None, config, "postgresql://stub"
    )

    assert result == Identity(
        principal_id="principal-7",
        tenant_id="tenant-2",
        issuer=ISSUER,
        subject="external-user-1",
    )
    assert connections[0].parameters == (ISSUER, "external-user-1")


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"iss": "https://untrusted.example.test"},
        {"aud": "another-api"},
        {"sub": ""},
    ],
)
def test_expired_or_wrong_trust_claims_are_rejected_before_database_lookup(
    signing_material: tuple[Settings, str],
    monkeypatch: pytest.MonkeyPatch,
    claims: dict[str, Any],
) -> None:
    config, private_key = signing_material
    connections = install_database_stub(monkeypatch, ("principal-7", "tenant-2"))

    with pytest.raises(HTTPException) as error:
        authenticate(
            request_from("127.0.0.1"),
            f"Bearer {signed_token(private_key, **claims)}",
            None,
            config,
            "postgresql://stub",
        )

    assert error.value.status_code == 401
    assert connections == []


def test_wrong_algorithm_is_rejected(
    signing_material: tuple[Settings, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _private_key = signing_material
    connections = install_database_stub(monkeypatch, ("principal-7", "tenant-2"))
    wrong_algorithm_token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "external-user-1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "untrusted-hmac-secret-at-least-32-bytes",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as error:
        authenticate(
            request_from("127.0.0.1"),
            f"Bearer {wrong_algorithm_token}",
            None,
            config,
            "postgresql://stub",
        )

    assert error.value.status_code == 401
    assert connections == []


def test_valid_but_unmapped_principal_is_rejected(
    signing_material: tuple[Settings, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config, private_key = signing_material
    connections = install_database_stub(monkeypatch, None)

    with pytest.raises(HTTPException) as error:
        authenticate(
            request_from("127.0.0.1"),
            f"Bearer {signed_token(private_key)}",
            None,
            config,
            "postgresql://stub",
        )

    assert error.value.status_code == 401
    assert error.value.detail == "identity is not provisioned"
    assert connections[0].parameters == (ISSUER, "external-user-1")


def test_local_demo_identities_map_alice_and_bob_to_database_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Settings()
    connections: list[PrincipalDatabase] = []

    def connect(_database_url: str, *, connect_timeout: int) -> PrincipalDatabase:
        assert connect_timeout == 3
        connection = PrincipalDatabase(
            ("principal-alice", "tenant-alice")
            if len(connections) == 0
            else ("principal-bob", "tenant-bob")
        )
        connections.append(connection)
        return connection

    import data_optimizer.auth.identity as identity_module

    monkeypatch.setattr(identity_module.psycopg, "connect", connect)
    alice = authenticate(request_from("127.0.0.1"), None, "alice", config, "postgresql://stub")
    bob = authenticate(request_from("::1"), None, "bob", config, "postgresql://stub")

    assert (alice.principal_id, alice.tenant_id, alice.subject) == (
        "principal-alice",
        "tenant-alice",
        "alice",
    )
    assert (bob.principal_id, bob.tenant_id, bob.subject) == (
        "principal-bob",
        "tenant-bob",
        "bob",
    )
    assert [connection.parameters for connection in connections] == [
        ("local-demo", "alice"),
        ("local-demo", "bob"),
    ]


def test_local_identity_rejects_arbitrary_tenant_selectors_without_database_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Settings()
    connections = install_database_stub(monkeypatch, ("principal", "tenant"))

    with pytest.raises(HTTPException) as error:
        authenticate(
            request_from("127.0.0.1"), None, "tenant-from-header", config, "postgresql://stub"
        )

    assert error.value.status_code == 401
    assert connections == []


def test_local_selector_uses_direct_peer_not_forwarded_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Settings()
    connections = install_database_stub(monkeypatch, ("principal", "tenant"))

    with pytest.raises(HTTPException) as error:
        authenticate(
            request_from("203.0.113.20", forwarded="127.0.0.1"),
            None,
            "alice",
            config,
            "postgresql://stub",
        )

    assert error.value.status_code == 401
    assert connections == []


def test_production_configuration_fails_closed_without_jwt_trust_settings() -> None:
    with pytest.raises(ValueError, match="only in development"):
        Settings(app_env="production")

    with pytest.raises(ValueError, match="AUTH_ISSUER, AUTH_AUDIENCE, and AUTH_PUBLIC_KEY"):
        Settings(app_env="production", auth_mode="jwt")


def test_production_jwt_configuration_requires_complete_trust_inputs() -> None:
    config = Settings(
        app_env="production",
        auth_mode="jwt",
        api_host="0.0.0.0",
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
        auth_public_key="configured-key",
    )

    assert config.auth_mode == "jwt"
