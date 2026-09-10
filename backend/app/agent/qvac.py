"""QVAC HTTP client (async, OpenAI-compatible API: streaming chat + embeddings)."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger("synapse.qvac")


class QvacError(Exception):
    """Raised when the QVAC node is unreachable or returns garbage."""


def _normalize_base_url(base_url: str) -> str:
    """Ensure the API root carries a single ``/v1`` suffix."""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return root
    return root + "/v1"


class QvacClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        embed_model: str,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = _normalize_base_url(base_url)
        self.model = model
        self.embed_model = embed_model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_models(self) -> list[str]:
        """Model ids from GET /v1/models; [] when the node is down."""
        try:
            resp = await self._client.get("/models")
            resp.raise_for_status()
            data = resp.json()
            return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        except Exception as exc:  # noqa: BLE001
            logger.warning("QVAC /v1/models no disponible: %s", exc)
            return []

    async def is_up(self) -> bool:
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a chat completion (OpenAI SSE).

        Yields {"token": str} per chunk and finally, exactly once,
        {"done": True, "text": full_text, "usage": {...}|None}.
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": True,
        }
        full_text = ""
        usage: dict[str, Any] | None = None
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    line = line[len("data:"):].strip()
                    if not line or line == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    token = delta.get("content") or ""
                    if token:
                        full_text += token
                        yield {"token": token}
        except httpx.HTTPError as exc:
            raise QvacError(f"QVAC no disponible: {exc}") from exc
        yield {"done": True, "text": full_text, "usage": usage}

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str | None:
        """One-shot (non-streaming) chat completion; None when unavailable.

        Used for short auxiliary calls (e.g. conversation titles) where the
        caller does not want to consume an SSE stream.
        """
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            resp = await self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("QVAC chat (no stream) no disponible: %s", exc)
            return None
        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        text = message.get("content")
        return text if isinstance(text, str) and text.strip() else None

    async def embed(self, text: str, model: str | None = None) -> list[float] | None:
        """Embedding vector from POST /v1/embeddings; None when unavailable."""
        try:
            resp = await self._client.post(
                "/embeddings", json={"model": model or self.embed_model, "input": text}
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data") or []
            if not items:
                return None
            embedding = items[0].get("embedding")
            return embedding if isinstance(embedding, list) else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Embeddings no disponibles: %s", exc)
            return None
