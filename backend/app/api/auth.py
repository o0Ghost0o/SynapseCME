"""Auth endpoints: login, refresh (rotated), logout, me, user management."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app import db
from app.auth import service
from app.auth.deps import require_admin, get_current_user
from app.auth.passwords import hash_password
from app.models import (
    CreateUserRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserOut,
    UsersResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest) -> TokenPair:
    return TokenPair(**await service.login(body.username, body.password))


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest) -> TokenPair:
    return TokenPair(**await service.rotate_refresh_token(body.refresh_token))


@router.post("/logout")
async def logout(body: LogoutRequest) -> dict[str, str]:
    await service.logout(body.refresh_token)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)) -> UserOut:
    return UserOut(**service.public_user(user))


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest, admin: dict = Depends(require_admin)
) -> UserOut:
    try:
        created = await db.create_user(
            username=body.username,
            full_name=body.full_name,
            role=body.role,
            password_hash=hash_password(body.password),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="El nombre de usuario ya existe"
        ) from None
    return UserOut(**created)


@router.get("/users", response_model=UsersResponse)
async def list_users(admin: dict = Depends(require_admin)) -> UsersResponse:
    return UsersResponse(entries=[UserOut(**u) for u in await db.list_users()])
