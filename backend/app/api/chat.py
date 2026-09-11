"""POST /api/chat — SSE stream of the agent pipeline."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app import db
from app.agent import service
from app.api.evidence import save_evidence_base64
from app.auth.deps import require_capturer
from app.models import ChatRequest

logger = logging.getLogger("synapse.api.chat")
router = APIRouter(tags=["chat"])


async def _resolve_conversation(request: ChatRequest, user: dict[str, Any]) -> str | None:
    """Validate/attach the requested conversation and persist the user message.

    - ``conversation_id`` given: must exist and belong to the caller (admin may
      use any); otherwise 404.
    - Missing: a new conversation is created server-side.
    - Postgres offline: None -> legacy behavior, nothing persisted.

    Returns the conversation id to thread into the SSE stream.
    """
    if db.pool() is None:
        return None
    if request.conversation_id:
        conv = await db.get_conversation(request.conversation_id)
        if conv is None or (conv["user_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        conversation_id: str | None = str(conv["id"])
    else:
        conv = await db.create_conversation(user["id"])
        conversation_id = str(conv["id"]) if conv else None
    if conversation_id is not None:
        try:
            if request.messages:
                for m in request.messages:
                    if m.strip():
                        await db.add_chat_message(conversation_id, "user", m.strip())
            elif request.message:
                await db.add_chat_message(conversation_id, "user", request.message)
        except Exception as exc:  # noqa: BLE001 - chat must not die on logging
            logger.warning("No se pudo persistir el mensaje del usuario: %s", exc)
    return conversation_id


@router.post("/api/chat")
async def chat(
    request: ChatRequest, user: dict[str, Any] = Depends(require_capturer)
) -> StreamingResponse:
    # Save evidence if provided as base64 data URL
    if request.evidence and request.evidence.startswith("data:"):
        filename = save_evidence_base64(request.evidence)
        request.evidence = filename

    # Pack multiple batched messages if needed
    if request.messages and not request.message:
        request.message = "\n".join(m.strip() for m in request.messages if m.strip())

    # `user` is the JWT identity; service.handle_chat ignores any
    # client-supplied contributor and uses this identity everywhere.
    conversation_id = await _resolve_conversation(request, user)
    return StreamingResponse(
        service.handle_chat(request, user, conversation_id=conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
