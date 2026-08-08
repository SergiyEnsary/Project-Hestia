from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from hestia.config import HestiaConfig

_bearer = HTTPBearer(auto_error=False)


async def verify_token(
    request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> None:
    config: HestiaConfig = request.app.state.config
    if not config.security.require_auth:
        return

    if credentials is None:
        credentials = await _bearer(request)

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not config.api_token or not secrets.compare_digest(
        credentials.credentials,
        config.api_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
