"""Background pusher: drains the outbox to the static peer list over HTTP.

Delivery is at-least-once: a row is marked sent only when every peer answers
2xx. Per-peer failures are logged and bump the attempts counter, so the row
is retried on the next cycle (until MAX_ATTEMPTS in store.fetch_pending).
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import settings
from app.sync import store

logger = logging.getLogger("synapse.sync.pusher")

REQUEST_TIMEOUT = 15.0


def _parse_peers(peers: str) -> list[str]:
    return [p.strip().rstrip("/") for p in peers.split(",") if p.strip()]


async def push_once(
    http: httpx.AsyncClient,
    peers: list[str],
    token: str,
) -> None:
    rows = await store.fetch_pending()
    if not rows:
        return
    base_peers = [p.rstrip("/") for p in peers]
    for row in rows:
        payload = row["payload"]
        all_ok = True
        for peer in base_peers:
            url = f"{peer}/api/sync/ingest"
            try:
                resp = await http.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code < 200 or resp.status_code >= 300:
                    all_ok = False
                    logger.warning(
                        "sync: peer %s respondió %s para outbox #%s",
                        peer, resp.status_code, row["id"],
                    )
            except Exception as exc:  # noqa: BLE001 - per-peer failure must not stop the rest
                all_ok = False
                logger.warning(
                    "sync: fallo al contactar peer %s para outbox #%s: %s",
                    peer, row["id"], exc,
                )
        if all_ok:
            await store.mark_sent(row["id"])
        else:
            await store.mark_attempt(row["id"])


async def pusher_loop(stop: asyncio.Event) -> None:
    peers = _parse_peers(settings.sync_peers)
    if not peers:
        return
    async with httpx.AsyncClient() as http:
        while not stop.is_set():
            try:
                await push_once(http, peers, settings.sync_token)
            except Exception as exc:  # noqa: BLE001 - the loop must survive anything
                logger.warning("sync: ciclo del pusher falló: %s", exc)
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.sync_interval_s)
            except asyncio.TimeoutError:
                pass
