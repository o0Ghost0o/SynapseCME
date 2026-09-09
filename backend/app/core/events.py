"""In-process event bus + WS presence registry (no external broker needed)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


class EventBus:
    """Fan-out broadcast to asyncio queues, one per connected WS client."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def broadcast(self, message: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:  # slow consumer: drop oldest, keep latest
                try:
                    q.get_nowait()
                    q.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    self._subscribers.discard(q)


@dataclass
class PresenceClient:
    client_type: str
    name: str
    connected_at: float
    last_seen: float
    online: bool = True
    username: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "client_type": self.client_type,
            "name": self.name,
            "username": self.username,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "online": self.online,
        }


class PresenceRegistry:
    """Tracks connected WS clients; stale ones (> ``stale_after`` s) go offline."""

    def __init__(self, stale_after: float = 60.0) -> None:
        self.stale_after = stale_after
        self._clients: dict[str, PresenceClient] = {}

    def register(
        self, key: str, client_type: str, name: str, username: str | None = None
    ) -> PresenceClient:
        now = time.time()
        client = self._clients.get(key)
        if client is None:
            client = PresenceClient(
                client_type=client_type, name=name, connected_at=now, last_seen=now,
                username=username,
            )
            self._clients[key] = client
        else:
            client.online = True
            client.last_seen = now
            client.client_type = client_type
            client.name = name
            client.username = username
        return client

    def touch(self, key: str) -> None:
        client = self._clients.get(key)
        if client is not None:
            client.last_seen = time.time()

    def mark_offline(self, key: str) -> None:
        client = self._clients.get(key)
        if client is not None:
            client.online = False

    def prune(self) -> list[PresenceClient]:
        """Mark clients idle for more than ``stale_after`` as offline."""
        now = time.time()
        newly_offline = [
            c
            for c in self._clients.values()
            if c.online and now - c.last_seen > self.stale_after
        ]
        for c in newly_offline:
            c.online = False
        return newly_offline

    def snapshot(self) -> list[dict[str, Any]]:
        return [c.as_dict() for c in self._clients.values()]


bus = EventBus()
presence = PresenceRegistry(stale_after=60.0)
