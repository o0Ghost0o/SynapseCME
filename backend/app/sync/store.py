"""Postgres-backed sync state: node identity + at-least-once outbox.

Every helper degrades to a no-op when the pool is None (Postgres unreachable),
matching the style of app/db/__init__.py. This module never raises.
"""

from __future__ import annotations

import json
import logging
import uuid

from app import db
from app.sync.schemas import SyncPayload

logger = logging.getLogger("synapse.sync.store")

MAX_ATTEMPTS = 8


async def ensure_schema() -> None:
    pool = db.pool()
    if pool is None:
        logger.debug("sync: sin pool Postgres; ensure_schema omitido")
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_meta (
                k text PRIMARY KEY,
                v text
            )
            """
        )
        await conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS sync_meta_k_key ON sync_meta (k)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_outbox (
                id bigserial PRIMARY KEY,
                payload jsonb NOT NULL,
                status text NOT NULL DEFAULT 'pending',
                attempts int NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL DEFAULT now(),
                sent_at timestamptz
            )
            """
        )
    logger.info("Esquema de sincronización verificado (sync_meta, sync_outbox)")


async def get_node_id() -> str:
    pool = db.pool()
    if pool is None:
        return ""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sync_meta (k, v) VALUES ('node_id', $1)
            ON CONFLICT (k) DO NOTHING
            """,
            str(uuid.uuid4()),
        )
        row = await conn.fetchrow(
            "SELECT v FROM sync_meta WHERE k = 'node_id'"
        )
    return row["v"] if row else ""


async def enqueue(payload: SyncPayload) -> bool:
    pool = db.pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sync_outbox (payload) VALUES ($1::jsonb)
                """,
                json.dumps(payload.model_dump(), ensure_ascii=False),
            )
        return True
    except Exception as exc:  # noqa: BLE001 - sync must never break the caller
        logger.warning("sync: no se pudo encolar el payload: %s", exc)
        return False


async def fetch_pending(limit: int = 20) -> list[dict]:
    pool = db.pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, payload
                FROM sync_outbox
                WHERE status = 'pending' AND attempts < $2
                ORDER BY id
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                limit,
                MAX_ATTEMPTS,
            )
    return [
        {"id": r["id"], "payload": json.loads(r["payload"])}
        for r in rows
    ]


async def mark_sent(row_id: int) -> None:
    pool = db.pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE sync_outbox
            SET status = 'sent', sent_at = now()
            WHERE id = $1
            """,
            row_id,
        )


async def mark_attempt(row_id: int) -> None:
    pool = db.pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE sync_outbox SET attempts = attempts + 1 WHERE id = $1
            """,
            row_id,
        )
