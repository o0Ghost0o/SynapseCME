"""QVAC/Ollama HTTP client (async, streaming chat completions + embeddings)."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger("synapse.qvac")


class QvacError(Exception):
    """Raised when the QVAC node is unreachable or returns garbage."""


class QvacClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        embed_model: str,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
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
        """Model tags from /api/tags; [] when the node is down."""
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception as exc:  # noqa: BLE001
            logger.warning("QVAC /api/tags no disponible: %s", exc)
            return []

    async def is_up(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def is_model_loaded(self, model: str | None = None) -> bool:
        """True when the model is already resident in VRAM (/api/ps)."""
        try:
            resp = await self._client.get("/api/ps")
            resp.raise_for_status()
            names = [m.get("name", "") for m in resp.json().get("models", [])]
            return (model or self.model) in names
        except Exception:  # noqa: BLE001
            return False

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream an /api/chat completion.

        Yields {"token": str} per chunk and finally
        {"done": True, "text": full_text, "usage": {...}|None}.
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": True,
        }
        try:
            async with self._client.stream(
                "POST", "/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("done"):
                        yield {
                            "done": True,
                            "text": chunk.get("message", {}).get("content", ""),
                            "usage": {
                                k: chunk.get(k)
                                for k in (
                                    "prompt_eval_count",
                                    "eval_count",
                                    "eval_duration",
                                    "load_duration",
                                )
                                if chunk.get(k) is not None
                            }
                            or None,
                        }
                    else:
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield {"token": token}
        except httpx.HTTPError as exc:
            raise QvacError(f"QVAC no disponible: {exc}") from exc

    async def embed(self, text: str, model: str | None = None) -> list[float] | None:
        """Embedding vector from /api/embed; None when unavailable (optional)."""
        try:
            resp = await self._client.post(
                "/api/embed", json={"model": model or self.embed_model, "input": text}
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings") or []
            return embeddings[0] if embeddings else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Embeddings no disponibles: %s", exc)
            return None
