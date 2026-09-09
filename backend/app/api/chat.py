"""POST /api/chat — SSE stream of the agent pipeline."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent import service
from app.models import ChatRequest

logger = logging.getLogger("synapse.api.chat")
router = APIRouter(tags=["chat"])


@router.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        service.handle_chat(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
