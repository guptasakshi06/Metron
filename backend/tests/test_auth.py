from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from data_optimizer.auth.identity import _jwt_subject, _local_selector
from data_optimizer.config import Settings


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


def test_local_identity_is_fixed_and_uses_direct_peer() -> None:
    config = Settings()
    assert _local_selector(request_from("127.0.0.1", "203.0.113.10"), "bob", config) == (
        "local-demo",
        "bob",
    )
    with pytest.raises(HTTPException):
        _local_selector(request_from("203.0.113.10"), "alice", config)
    with pytest.raises(HTTPException):
        _local_selector(request_from("127.0.0.1"), "other-tenant", config)


def test_local_mode_cannot_bind_externally_or_run_in_production() -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(api_host="0.0.0.0")
    with pytest.raises(ValueError, match="only in development"):
        Settings(app_env="production")


@pytest.fixture
def jwt_material() -> tuple[Settings, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    config = Settings(
        auth_mode="jwt",
        auth_issuer="https://identity.example.test",
        auth_audience="data-optimizer-api",
        auth_public_key=public_key,
    )
    return config, private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def token(private_key: str, **changes: object) -> str:
    claims: dict[str, object] = {
        "iss": "https://identity.example.test",
        "aud": "data-optimizer-api",
        "sub": "external-user-1",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    claims.update(changes)
    return jwt.encode(claims, private_key, algorithm="RS256")


def test_jwt_requires_signature_and_exact_trust_claims(jwt_material: tuple[Settings, str]) -> None:
    config, private_key = jwt_material
    valid = token(private_key)
    assert _jwt_subject(f"Bearer {valid}", config) == (
        "https://identity.example.test",
        "external-user-1",
    )
    for claims in (
        {"iss": "https://other.example.test"},
        {"aud": "other-api"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
    ):
        with pytest.raises(HTTPException):
            _jwt_subject(f"Bearer {token(private_key, **claims)}", config)
    unsigned = jwt.encode(
        {
            "iss": "https://identity.example.test",
            "aud": "data-optimizer-api",
            "sub": "x",
            "exp": 9_999_999_999,
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(HTTPException):
        _jwt_subject(f"Bearer {unsigned}", config)
