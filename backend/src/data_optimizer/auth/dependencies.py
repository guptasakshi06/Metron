"""FastAPI dependency for the verified request principal."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from data_optimizer.auth.identity import Identity, authenticate
from data_optimizer.config import Settings, settings


def current_identity(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_local_identity: Annotated[str | None, Header()] = None,
) -> Identity:
    return authenticate(
        request, authorization, x_local_identity, settings, str(settings.database_url)
    )


CurrentIdentity = Annotated[Identity, Depends(current_identity)]


def identity_dependency(config: Settings) -> Callable[..., Identity]:
    """Build an auth dependency bound to the application's explicit configuration."""

    def dependency(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_local_identity: Annotated[str | None, Header()] = None,
    ) -> Identity:
        return authenticate(
            request, authorization, x_local_identity, config, str(config.database_url)
        )

    return dependency
