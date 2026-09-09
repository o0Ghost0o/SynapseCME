"""Enqueue a local extraction into the sync outbox.

Called from the chat stream after a successful local ingestion. Never raises:
sync is opportunistic and must not break the SSE pipeline.
"""

from __future__ import annotations

import logging

from app import db
from app.core.config import settings
from app.models import ExtractionResult
from app.sync import store
from app.sync.schemas import SyncPayload

logger = logging.getLogger("synapse.sync.service")


async def enqueue_extraction(
    ext: ExtractionResult,
    contributor: str,
    client_type: str | None,
) -> None:
    if not settings.sync_peers:
        return
    if db.pool() is None:
        logger.debug("sync: sin pool Postgres; extracción no encolada")
        return
    try:
        payload = SyncPayload(
            node_id=await store.get_node_id(),
            contributor=contributor,
            client_type=client_type,
            extraction=ext,
        )
        await store.enqueue(payload)
    except Exception as exc:  # noqa: BLE001 - hard rule: never break the stream
        logger.warning("sync: no se pudo encolar la extracción: %s", exc)
