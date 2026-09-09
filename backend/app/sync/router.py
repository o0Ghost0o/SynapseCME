"""POST /api/sync/ingest — receive a peer's extraction and apply it locally.

Closed by default: without a configured SYNC_TOKEN the endpoint answers 404.
A peer's garbage never becomes our 500; engine failures map to 422.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.graph import engine
from app.sync import store
from app.sync.schemas import SyncAck, SyncPayload

logger = logging.getLogger("synapse.sync.router")

router = APIRouter(tags=["sync"])


@router.post("/api/sync/ingest", response_model=SyncAck)
async def sync_ingest(request: Request) -> SyncAck:
    if not settings.sync_token:
        raise HTTPException(status_code=404, detail="Not Found")

    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {settings.sync_token}"
    if not hmac.compare_digest(auth, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = SyncPayload.model_validate(await request.json())

    node_id = await store.get_node_id()
    if body.node_id and node_id and body.node_id == node_id:
        return SyncAck(ignored=True)

    try:
        ingest = await engine.ingest_extraction(
            body.extraction, body.contributor, body.client_type
        )
    except Exception as exc:  # noqa: BLE001 - peer garbage must not 500 us
        logger.warning("sync: extracción rechazada del peer %s: %s", body.node_id, exc)
        raise HTTPException(status_code=422, detail="Unprocessable extraction")

    return SyncAck(
        ignored=False,
        facility_id=ingest.facility_id,
        transactions=len(ingest.transaction_ids),
    )
