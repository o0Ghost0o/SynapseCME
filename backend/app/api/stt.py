"""POST /api/stt — proxy multipart audio to the local faster-whisper service."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.agent import stt as stt_client
from app.auth.deps import require_capturer
from app.core.config import settings

logger = logging.getLogger("synapse.api.stt")
router = APIRouter(tags=["stt"])

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB safety cap for field dictation clips


@router.post("/api/stt")
async def transcribe_audio(
    file: UploadFile,
    user: dict[str, Any] = Depends(require_capturer),
) -> dict[str, str]:
    audio = await file.read(MAX_AUDIO_BYTES + 1)
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, detail="Audio demasiado grande (máx. 25 MB)")
    if not audio:
        raise HTTPException(400, detail="Archivo de audio vacío")
    async with stt_client.make_client(settings.stt_base_url) as client:
        try:
            text = await stt_client.transcribe(
                client,
                audio,
                filename=file.filename or "audio.wav",
                content_type=file.content_type or "application/octet-stream",
                model=settings.stt_model,
            )
        except stt_client.SttUnavailable as exc:
            raise HTTPException(
                503, detail=f"Dictado no disponible: {exc}"
            ) from exc
    return {"text": text}
