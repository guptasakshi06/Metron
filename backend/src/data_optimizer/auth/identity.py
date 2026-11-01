"""Verified user identities; tenant ownership always comes from the database mapping."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

import jwt
import psycopg
from fastapi import HTTPException, Request, status

from data_optimizer.config import Settings


@dataclass(frozen=True, slots=True)
class Identity:
    principal_id: str
    tenant_id: str
    issuer: str
    subject: str


def _local_selector(request: Request, selector: str | None, config: Settings) -> tuple[str, str]:
    """Resolve a fixed demo identity only when the direct peer and bind are loopback."""
    client_host = request.client.host if request.client else ""
    try:
        is_loopback_peer = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_loopback_peer = False
    if config.auth_mode != "local" or config.app_env != "development" or not is_loopback_peer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    selected = selector or "alice"
    if selected not in {"alice", "bob"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid local identity"
        )
    return "local-demo", selected


def _jwt_subject(authorization: str | None, config: Settings) -> tuple[str, str]:
    """Validate a trusted RS256 token with required issuer/audience/expiry claims."""
    if config.auth_mode != "jwt" or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="bearer token required"
        )
    token = authorization.removeprefix("Bearer ").strip()
    if config.auth_public_key is None or config.auth_issuer is None or config.auth_audience is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="auth unavailable"
        )
    try:
        claims = jwt.decode(
            token,
            config.auth_public_key,
            algorithms=["RS256"],
            issuer=config.auth_issuer,
            audience=config.auth_audience,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token"
        ) from error
    issuer, subject = claims.get("iss"), claims.get("sub")
    if not isinstance(issuer, str) or not isinstance(subject, str) or not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
    return issuer, subject


def authenticate(
    request: Request,
    authorization: str | None,
    local_identity: str | None,
    config: Settings,
    database_url: str,
) -> Identity:
    """Verify caller and map its (issuer, subject) to an existing tenant principal."""
    if config.auth_mode == "local":
        issuer, subject = _local_selector(request, local_identity, config)
    else:
        issuer, subject = _jwt_subject(authorization, config)
    with psycopg.connect(database_url, connect_timeout=3) as connection:
        row = connection.execute(
            "SELECT id::text, tenant_id::text FROM principals WHERE issuer = %s AND subject = %s",
            (issuer, subject),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="identity is not provisioned"
        )
    return Identity(principal_id=row[0], tenant_id=row[1], issuer=issuer, subject=subject)
