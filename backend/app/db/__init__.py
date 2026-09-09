"""PostgreSQL access layer (asyncpg pool + query helpers).

The pool is optional at runtime: if Postgres is unreachable at startup the
app still boots (graph + demos keep working) and every helper degrades to a
no-op that logs a warning. This keeps tests and local demos free of a live DB.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from app.core.metrics import InferenceMetrics

logger = logging.getLogger("synapse.db")

_pool: asyncpg.Pool | None = None


async def init_pool(dsn: str) -> bool:
    global _pool
    try:
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
        logger.info("Conexión a PostgreSQL establecida")
        return True
    except Exception as exc:  # noqa: BLE001 - startup must not crash
        logger.warning("PostgreSQL no disponible (%s); métricas y transacciones desactivadas", exc)
        _pool = None
        return False


def pool() -> asyncpg.Pool | None:
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def log_transaction(
    actor: str,
    action: str,
    client_type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    target_name: str | None = None,
    state_transition: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Insert a transaction_log row; returns the row (incl. id) or None."""
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO transaction_log
                (actor, client_type, action, target_type, target_id,
                 target_name, state_transition, payload)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            RETURNING id, actor, client_type, action, target_type, target_id,
                      target_name, state_transition,
                      to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SSZ') AS created_at
            """,
            actor,
            client_type,
            action,
            target_type,
            target_id,
            target_name,
            state_transition,
            json.dumps(payload or {}, ensure_ascii=False),
        )
        return dict(row) if row else None


async def log_perf(request_id: str, metrics: InferenceMetrics) -> None:
    if _pool is None:
        return
    row = metrics.as_perf_row(request_id)
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO perf_log
                (request_id, model, model_load_ms, prompt_tokens,
                 generation_tokens, ttft_ms, total_ms, throughput_tps, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            """,
            row["request_id"],
            row["model"],
            row["model_load_ms"],
            row["prompt_tokens"],
            row["generation_tokens"],
            row["ttft_ms"],
            row["total_ms"],
            row["throughput_tps"],
            row["created_at"],
        )


async def log_state_transition(
    equipment_id: str,
    field: str,
    old_state: str | None,
    new_state: str,
    confidence: float | None,
    observation_id: str | None,
) -> None:
    if _pool is None:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO equipment_state_log
                (equipment_id, field, old_state, new_state, confidence, observation_id)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            equipment_id,
            field,
            old_state,
            new_state,
            confidence,
            observation_id,
        )


async def recent_transactions(
    action: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    if _pool is None:
        return []
    limit = min(max(limit, 1), 500)
    async with _pool.acquire() as conn:
        if action:
            rows = await conn.fetch(
                """
                SELECT id, actor, client_type, action, target_type, target_id,
                       target_name, state_transition,
                       to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SSZ') AS created_at,
                       coalesce(payload::text, '{}') AS payload
                FROM transaction_log WHERE action = $1
                ORDER BY id DESC LIMIT $2
                """,
                action,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, actor, client_type, action, target_type, target_id,
                       target_name, state_transition,
                       to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SSZ') AS created_at,
                       coalesce(payload::text, '{}') AS payload
                FROM transaction_log
                ORDER BY id DESC LIMIT $1
                """,
                limit,
            )
    return [_tx_row_to_dict(r) for r in rows]


async def all_transactions_for_export() -> list[dict[str, Any]]:
    if _pool is None:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, actor, client_type, action, target_type, target_id,
                   target_name, state_transition,
                   to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SSZ') AS created_at,
                   coalesce(payload::text, '{}') AS payload
            FROM transaction_log ORDER BY id DESC
            """
        )
    return [_tx_row_to_dict(r) for r in rows]


def _tx_row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    try:
        d["payload"] = json.loads(d.get("payload") or "{}")
    except (ValueError, TypeError):
        d["payload"] = {}
    return d


async def recent_perf(limit: int = 100) -> list[dict[str, Any]]:
    if _pool is None:
        return []
    limit = min(max(limit, 1), 500)
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT model, model_load_ms, prompt_tokens, generation_tokens,
                   ttft_ms, total_ms, throughput_tps,
                   to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SSZ') AS created_at
            FROM perf_log ORDER BY id DESC LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]
