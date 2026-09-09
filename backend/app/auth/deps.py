"""FastAPI auth dependencies: bearer token -> current user -> role gates."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import service

_bearer = HTTPBearer(auto_error=False)

# Role hierarchy: admin > capturer > viewer.
ROLES = ("admin", "capturer", "viewer")


def _forbidden() -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN, detail="Permisos insuficientes para esta operación"
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    """Resolve the Authorization header to a live user row (from the DB)."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Token de acceso requerido"
        )
    return await service.authenticate_access_token(credentials.credentials)


def require_role(*roles: str):
    """Dependency factory enforcing that the current user has one of `roles`."""

    async def checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user["role"] not in roles:
            raise _forbidden()
        return user

    return checker


require_viewer = require_role("admin", "capturer", "viewer")   # all reads
require_capturer = require_role("admin", "capturer")           # field capture
require_admin = require_role("admin")                          # user management
