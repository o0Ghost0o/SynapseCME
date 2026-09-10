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


async def init_pool(dsn: str, retries: int = 5, delay: float = 2.0) -> bool:
    """Create the pool, retrying briefly (compose services boot in parallel)."""
    global _pool
    for attempt in range(1, retries + 1):
        try:
            _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
            logger.info("Conexión a PostgreSQL establecida")
            return True
        except Exception as exc:  # noqa: BLE001 - startup must not crash
            logger.warning(
                "PostgreSQL no disponible (intento %d/%d): %s", attempt, retries, exc
            )
            _pool = None
            if attempt < retries:
                import asyncio

                await asyncio.sleep(delay)
    logger.warning("PostgreSQL no disponible; métricas y transacciones desactivadas")
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


# ---------------------------------------------------------------------------
# Auth schema + helpers (users, refresh tokens)
# ---------------------------------------------------------------------------
#
# ``ensure_schema`` runs at every startup so existing deployments (whose
# PostgreSQL data dir is already initialized and will not re-run init.sql)
# get the auth tables created idempotently.

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'capturer', 'viewer')),
        password_hash TEXT NOT NULL,
        disabled BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS refresh_tokens (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens (user_id)",
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_message_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_conversations_user "
    "ON conversations (user_id, last_message_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id BIGSERIAL PRIMARY KEY,
        conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content TEXT NOT NULL DEFAULT '',
        extraction JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_conv "
    "ON chat_messages (conversation_id, created_at)",
]


async def ensure_schema() -> bool:
    """Create any missing table (idempotent). True when a pool is available."""
    if _pool is None:
        logger.warning("PostgreSQL no disponible; esquema de auth no garantizado")
        return False
    async with _pool.acquire() as conn:
        for stmt in SCHEMA_STATEMENTS:
            await conn.execute(stmt)
    logger.info("Esquema PostgreSQL verificado (users, refresh_tokens, conversations)")
    return True


async def count_users() -> int:
    if _pool is None:
        return 0
    async with _pool.acquire() as conn:
        return int(await conn.fetchval("SELECT count(*) FROM users"))


_USER_COLUMNS = (
    "id, username, full_name, role, disabled, "
    "to_char(created_at, 'YYYY-MM-DD\"T\"HH24:MI:SSZ') AS created_at"
)


async def get_user_by_username(username: str) -> dict[str, Any] | None:
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_USER_COLUMNS}, password_hash FROM users WHERE username = $1",
            username,
        )
        return dict(row) if row else None


async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_USER_COLUMNS}, password_hash FROM users WHERE id = $1",
            user_id,
        )
        return dict(row) if row else None


async def create_user(
    username: str, full_name: str, role: str, password_hash: str
) -> dict[str, Any]:
    """Insert a user; raises asyncpg.UniqueViolationError on duplicate."""
    if _pool is None:
        raise RuntimeError("PostgreSQL no disponible")
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO users (username, full_name, role, password_hash) "
            f"VALUES ($1, $2, $3, $4) RETURNING {_USER_COLUMNS}",
            username,
            full_name,
            role,
            password_hash,
        )
        return dict(row)


async def list_users() -> list[dict[str, Any]]:
    if _pool is None:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {_USER_COLUMNS} FROM users ORDER BY id"
        )
        return [dict(r) for r in rows]


async def set_user_disabled(username: str, disabled: bool) -> bool:
    if _pool is None:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET disabled = $2 WHERE username = $1", username, disabled
        )
        return result == "UPDATE 1"


async def insert_refresh_token(
    user_id: int, token_hash: str, expires_at: Any
) -> int | None:
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        return int(
            await conn.fetchval(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) "
                "VALUES ($1, $2, $3) RETURNING id",
                user_id,
                token_hash,
                expires_at,
            )
        )


async def get_refresh_token(token_hash: str) -> dict[str, Any] | None:
    """Fetch a refresh token row joined with its user (for validation)."""
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT rt.id, rt.user_id, rt.expires_at, rt.revoked, rt.created_at, "
            "       u.username, u.full_name, u.role, u.disabled "
            "FROM refresh_tokens rt JOIN users u ON u.id = rt.user_id "
            "WHERE rt.token_hash = $1",
            token_hash,
        )
        return dict(row) if row else None


async def revoke_refresh_token(token_id: int) -> None:
    if _pool is None:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE id = $1", token_id
        )


# ---------------------------------------------------------------------------
# Conversations + chat messages (Fase 4: sesiones de chat múltiples)
# ---------------------------------------------------------------------------

_TS = "YYYY-MM-DD\"T\"HH24:MI:SSZ"


def _conv_row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    d["id"] = str(d["id"])
    return d


async def create_conversation(user_id: int) -> dict[str, Any] | None:
    """New empty conversation owned by `user_id`; None when Postgres is off."""
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO conversations (user_id) VALUES ($1) "
            f"RETURNING id, user_id, title, "
            f"to_char(created_at, '{_TS}') AS created_at, "
            f"to_char(last_message_at, '{_TS}') AS last_message_at",
            user_id,
        )
        return _conv_row_to_dict(row) if row else None


async def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    """Conversation row regardless of owner; None when missing or DB off."""
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT id, user_id, title, "
            f"to_char(created_at, '{_TS}') AS created_at, "
            f"to_char(last_message_at, '{_TS}') AS last_message_at "
            f"FROM conversations WHERE id = $1",
            conversation_id,
        )
        return _conv_row_to_dict(row) if row else None


async def list_conversations(user_id: int) -> list[dict[str, Any]]:
    """Owner's conversations, most recent activity first."""
    if _pool is None:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT id, title, to_char(last_message_at, '{_TS}') AS last_message_at "
            f"FROM conversations WHERE user_id = $1 "
            f"ORDER BY last_message_at DESC",
            user_id,
        )
        return [_conv_row_to_dict(r) for r in rows]


async def delete_conversation(conversation_id: str) -> bool:
    """True when a row was actually deleted (cascades to chat_messages)."""
    if _pool is None:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM conversations WHERE id = $1", conversation_id
        )
        return result == "DELETE 1"


async def add_chat_message(
    conversation_id: str,
    role: str,
    content: str,
    extraction: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Append a message and bump the conversation's last_message_at."""
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO chat_messages (conversation_id, role, content, extraction) "
            f"VALUES ($1, $2, $3, $4::jsonb) RETURNING id, role, content, "
            f"extraction::text AS extraction, to_char(created_at, '{_TS}') AS created_at",
            conversation_id,
            role,
            content,
            json.dumps(extraction, ensure_ascii=False) if extraction else None,
        )
        await conn.execute(
            "UPDATE conversations SET last_message_at = now() WHERE id = $1",
            conversation_id,
        )
        return dict(row) if row else None


def _msg_row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    try:
        d["extraction"] = json.loads(d["extraction"]) if d.get("extraction") else None
    except (ValueError, TypeError):
        d["extraction"] = None
    return d


async def list_chat_messages(conversation_id: str) -> list[dict[str, Any]]:
    if _pool is None:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT id, role, content, extraction::text AS extraction, "
            f"to_char(created_at, '{_TS}') AS created_at "
            f"FROM chat_messages WHERE conversation_id = $1 ORDER BY id",
            conversation_id,
        )
        return [_msg_row_to_dict(r) for r in rows]


async def set_conversation_title(conversation_id: str, title: str) -> bool:
    """True when the title was updated (conversation still exists)."""
    if _pool is None:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE conversations SET title = $2 WHERE id = $1",
            conversation_id,
            title,
        )
        return result == "UPDATE 1"
