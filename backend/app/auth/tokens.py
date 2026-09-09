"""JWT access tokens (HS256, 15 min). ``now`` is injectable for tests."""

from __future__ import annotations

import time
from typing import Any

import jwt

from app.core.config import settings

ALGORITHM = "HS256"
TOKEN_TYPE = "access"


def create_access_token(sub: str, now: float | None = None) -> str:
    issued = int(time.time() if now is None else now)
    payload = {
        "sub": sub,
        "iat": issued,
        "exp": issued + settings.access_token_ttl_seconds,
        "type": TOKEN_TYPE,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str, now: float | None = None) -> dict[str, Any]:
    """Decode and validate. Raises jwt.ExpiredSignatureError / jwt.InvalidTokenError.

    When ``now`` is given, pyjwt's own exp check is skipped and expiry is
    validated against ``now`` manually (deterministic tests).
    """
    if now is None:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        options={"verify_exp": False},
    )
    if int(now) >= int(payload.get("exp", 0)):
        raise jwt.ExpiredSignatureError("Token expirado")
    return payload
