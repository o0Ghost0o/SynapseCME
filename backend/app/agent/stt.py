"""Speech-to-text proxy to the local speaches/faster-whisper service.

STT is a read-only transform: no transaction_log rows, no perf_log metrics
(Track 02 covers language-model inference only).
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("synapse.stt")

TIMEOUT_SECONDS = 15.0


class SttUnavailable(Exception):
    """The STT service is down, timed out, or returned garbage."""


async def transcribe(
    client: httpx.AsyncClient,
    audio: bytes,
    filename: str,
    content_type: str,
    model: str,
) -> str:
    """Forward an audio blob to /v1/audio/transcriptions and return the text.

    Raises SttUnavailable on any transport error, timeout, or non-2xx —
    callers translate that into a clean 503.
    """
    form = {
        "file": (filename, audio, content_type or "application/octet-stream"),
        "model": (None, model),
        # soft hint only; the server also has DEFAULT_LANGUAGE=es
        "language": (None, "es"),
    }
    try:
        resp = await client.post("/v1/audio/transcriptions", files=form)
    except httpx.HTTPError as exc:
        logger.warning("STT no responde: %s", exc)
        raise SttUnavailable("servicio de voz no responde") from exc
    if resp.status_code != 200:
        logger.warning("STT devolvió %s: %s", resp.status_code, resp.text[:200])
        raise SttUnavailable(f"servicio de voz devolvió {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise SttUnavailable("respuesta de voz inválida") from exc
    text = (data.get("text") or "").strip()
    if not text:
        raise SttUnavailable("no se detectó voz en el audio")
    return text


def make_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=3.0),
    )
