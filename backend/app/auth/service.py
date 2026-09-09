"""Auth business logic: login, refresh rotation, logout, bootstrap admin."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

from app import db
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import create_access_token, decode_access_token
from app.core.config import settings

logger = logging.getLogger("synapse.auth")

DEFAULT_JWT_SECRET = "synapse-dev-jwt-secret-cambiame-2026"
DEFAULT_ADMIN_PASSWORD = "synapse-admin"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
    }


async def issue_token_pair(user: dict[str, Any]) -> dict[str, Any]:
    """Create access + refresh tokens and persist the refresh hash."""
    access_token = create_access_token(user["username"])
    refresh_token = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_ttl_days
    )
    await db.insert_refresh_token(user["id"], hash_refresh_token(refresh_token), expires_at)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_seconds,
        "user": public_user(user),
    }


async def login(username: str, password: str) -> dict[str, Any]:
    user = await db.get_user_by_username(username)
    if user is None or not verify_password(password, user["password_hash"]):
        raise _unauthorized("Credenciales inválidas")
    if user["disabled"]:
        raise _unauthorized("Usuario deshabilitado")
    return await issue_token_pair(user)


async def rotate_refresh_token(raw_token: str) -> dict[str, Any]:
    """Refresh rotation: the presented token is revoked and a new pair issued."""
    row = await db.get_refresh_token(hash_refresh_token(raw_token))
    now = datetime.now(timezone.utc)
    if (
        row is None
        or row["revoked"]
        or row["expires_at"] <= now
        or row["disabled"]
    ):
        raise _unauthorized("Refresh token inválido o expirado")
    await db.revoke_refresh_token(row["id"])
    user = {
        "id": row["user_id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
    }
    return await issue_token_pair(user)


async def logout(raw_token: str) -> None:
    """Revoke a refresh token; idempotent (unknown tokens are a no-op)."""
    row = await db.get_refresh_token(hash_refresh_token(raw_token))
    if row is not None and not row["revoked"]:
        await db.revoke_refresh_token(row["id"])


async def authenticate_access_token(token: str) -> dict[str, Any]:
    """Validate an access token and load the user (disable takes effect now).

    Used by the REST dependency and the WS handshake. Raises HTTPException
    with a Spanish message on any failure.
    """
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expirado, inicia sesión de nuevo") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Token inválido") from None
    username = payload.get("sub")
    if not username:
        raise _unauthorized("Token inválido")
    user = await db.get_user_by_username(username)
    if user is None:
        raise _unauthorized("Usuario no encontrado")
    if user["disabled"]:
        raise _unauthorized("Usuario deshabilitado")
    return user


async def ensure_bootstrap_admin() -> bool:
    """Create the admin user when the users table is empty."""
    if db.pool() is None:
        return False
    if await db.count_users() > 0:
        return False
    if settings.admin_password == DEFAULT_ADMIN_PASSWORD:
        logger.warning(
            "ADMIN_PASSWORD no configurado: usando la contraseña de "
            "DESARROLLO (%r). Cámbiala inmediatamente.", DEFAULT_ADMIN_PASSWORD
        )
    user = await db.create_user(
        username=settings.admin_user,
        full_name="Administrador SynapseCME",
        role="admin",
        password_hash=hash_password(settings.admin_password),
    )
    logger.info("Usuario administrador inicial creado: %s", user["username"])
    return True


async def ensure_user(
    username: str, full_name: str, role: str, password: str
) -> tuple[dict[str, Any], bool]:
    """Create a user if missing (idempotent). Returns (user, created)."""
    existing = await db.get_user_by_username(username)
    if existing is not None:
        return existing, False
    user = await db.create_user(username, full_name, role, hash_password(password))
    logger.info("Usuario creado: %s (%s)", username, role)
    return user, True
