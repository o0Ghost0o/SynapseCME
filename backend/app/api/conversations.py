"""Conversation sessions: list, detail (messages), delete (capturer role and above).

Owners see/delete only their own conversations; admin can access any.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app import db
from app.auth.deps import require_capturer

logger = logging.getLogger("synapse.api.conversations")
router = APIRouter(tags=["conversations"])


def _db_or_503() -> None:
    if db.pool() is None:
        raise HTTPException(status_code=503, detail="PostgreSQL no disponible")


async def _get_owned_conversation(
    conversation_id: UUID, user: dict[str, Any]
) -> dict[str, Any]:
    conv = await db.get_conversation(str(conversation_id))
    if conv is None or (conv["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return conv


@router.get("/api/conversations")
async def list_conversations(
    user: dict[str, Any] = Depends(require_capturer),
) -> list[dict[str, Any]]:
    _db_or_503()
    try:
        return await db.list_conversations(user["id"])
    except Exception as exc:  # noqa: BLE001 - Postgres mid-request failure
        logger.warning("Listado de conversaciones falló: %s", exc)
        raise HTTPException(status_code=503, detail="PostgreSQL no disponible") from exc


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    user: dict[str, Any] = Depends(require_capturer),
) -> dict[str, Any]:
    _db_or_503()
    conv = await _get_owned_conversation(conversation_id, user)
    try:
        messages = await db.list_chat_messages(str(conversation_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lectura de mensajes falló: %s", exc)
        raise HTTPException(status_code=503, detail="PostgreSQL no disponible") from exc
    return {
        "id": conv["id"],
        "title": conv["title"],
        "created_at": conv["created_at"],
        "last_message_at": conv["last_message_at"],
        "messages": messages,
    }


@router.delete("/api/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: dict[str, Any] = Depends(require_capturer),
) -> None:
    _db_or_503()
    await _get_owned_conversation(conversation_id, user)
    try:
        deleted = await db.delete_conversation(str(conversation_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Borrado de conversación falló: %s", exc)
        raise HTTPException(status_code=503, detail="PostgreSQL no disponible") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
