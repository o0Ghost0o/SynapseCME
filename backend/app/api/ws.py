"""WS /ws/events — presence registry, heartbeat, live mutation feed."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import bus, presence

logger = logging.getLogger("synapse.api.ws")
router = APIRouter()


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket) -> None:
    await ws.accept()
    key = uuid.uuid4().hex[:8]
    out_q = bus.subscribe()
    registered = False

    async def send(message: dict) -> None:
        await ws.send_text(json.dumps(message, ensure_ascii=False))

    async def broadcast_presence() -> None:
        await bus.broadcast({"type": "presence", "clients": presence.snapshot()})

    try:
        # First message must be hello (with a small grace window).
        try:
            hello_raw = await asyncio.wait_for(ws.receive_text(), timeout=15.0)
            hello = json.loads(hello_raw)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            hello = {}

        if isinstance(hello, dict) and hello.get("type") == "hello":
            client_type = str(hello.get("client_type") or "dashboard")
            name = str(hello.get("name") or f"cliente-{key}")
            presence.register(key, client_type, name)
            registered = True
            await broadcast_presence()

        async def pump_inbound() -> None:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue
                presence.touch(key)
                if msg.get("type") == "ping":
                    await out_q.put({"type": "pong"})

        inbound = asyncio.create_task(pump_inbound())
        try:
            while True:
                message = await out_q.get()
                await send(message)
        finally:
            inbound.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await inbound
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("WS cerrado con error: %s", exc)
    finally:
        bus.unsubscribe(out_q)
        if registered:
            presence.mark_offline(key)
            await broadcast_presence()


async def prune_presence_loop(interval: float = 15.0) -> None:
    """Mark clients idle >60s as offline and rebroadcast presence."""
    while True:
        await asyncio.sleep(interval)
        newly_offline = presence.prune()
        if newly_offline:
            logger.info("Presencia actualizada: %d cliente(s) fuera de línea", len(newly_offline))
            await bus.broadcast({"type": "presence", "clients": presence.snapshot()})
