"""POST /api/chat — SSE stream of the agent pipeline."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent import service
from app.auth.deps import require_capturer
from app.models import ChatRequest

logger = logging.getLogger("synapse.api.chat")
router = APIRouter(tags=["chat"])


@router.post("/api/chat")
async def chat(
    request: ChatRequest, user: dict[str, Any] = Depends(require_capturer)
) -> StreamingResponse:
    # `user` is the JWT identity; service.handle_chat ignores any
    # client-supplied contributor and uses this identity everywhere.
    return StreamingResponse(
        service.handle_chat(request, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
