"""GraphRAG retrieval: embeddings + LanceDB index over observation texts.

Observations (raw extraction texts) are embedded with bge-m3 via the QVAC
OpenAI-compatible server and upserted into a LanceDB table. At chat time the
message is embedded and top-k similar past observations (plus the graph
neighborhood when a facility is detectable) are injected into the system
prompt. Everything is best-effort: failures degrade to no context.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import lancedb
import pyarrow as pa

from app.agent.extractor import detect_facility
from app.agent.qvac import QvacClient
from app.graph.context import graph_context
from app.models import ExtractionResult

logger = logging.getLogger("synapse.agent")

TABLE_NAME = "observations"
SNIPPET_LEN = 200


def _connect(data_dir: str) -> tuple[Any, Any | None]:
    """Open the LanceDB dir and the observations table (None if missing)."""
    db = lancedb.connect(data_dir)
    try:
        table = db.open_table(TABLE_NAME)
    except Exception:  # noqa: BLE001 - table not created yet
        table = None
    return db, table


def _schema_for(dim: int) -> pa.Schema:
    return pa.schema(
        [
            ("id", pa.string()),
            ("text", pa.string()),
            ("vector", pa.list_(pa.float32(), dim)),
            ("facility", pa.string()),
            ("country", pa.string()),
            ("extractor", pa.string()),
            ("ts", pa.float64()),
        ]
    )


async def index_extraction(
    client: QvacClient, ext: ExtractionResult, *, data_dir: str
) -> int:
    """Embed ext.raw and upsert it into the observations index; 0/1 rows.

    Never raises: embedding and LanceDB failures are logged and swallowed.
    """
    try:
        text = (ext.raw or "").strip()
        if not text:
            return 0
        vector = await client.embed(text)
        if not vector:
            return 0
        dim = len(vector)
        row_id = hashlib.sha1(text.encode("utf-8")).hexdigest()
        row = {
            "id": row_id,
            "text": text,
            "vector": vector,
            "facility": ext.facility,
            "country": ext.country,
            "extractor": ext.extractor,
            "ts": time.time(),
        }
        await asyncio.to_thread(_upsert, data_dir, row, dim)
        return 1
    except Exception as exc:  # noqa: BLE001 - indexing must never break chat
        logger.warning("No se pudo indexar la observación: %s", exc)
        return 0


def _upsert(data_dir: str, row: dict[str, Any], dim: int) -> None:
    db, table = _connect(data_dir)
    if table is None:
        table = db.create_table(TABLE_NAME, schema=_schema_for(dim))
    elif table.schema.field("vector").type.list_size != dim:
        logger.warning(
            "Dimensión del embedding (%d) no coincide con la tabla (%s); "
            "observación no indexada",
            dim,
            table.schema.field("vector").type,
        )
        return
    try:
        table.delete(f"id = '{row['id']}'")
    except Exception:  # noqa: BLE001 - row may not exist yet
        pass
    table.add([row])


async def retrieve(
    client: QvacClient,
    message: str,
    *,
    data_dir: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Top-k most similar past observations; [] on any failure."""
    try:
        vector = await client.embed(message)
        if not vector:
            return []
        return await asyncio.to_thread(_search, data_dir, vector, top_k)
    except Exception as exc:  # noqa: BLE001 - retrieval is best-effort
        logger.debug("Búsqueda RAG falló: %s", exc)
        return []


def _search(data_dir: str, vector: list[float], top_k: int) -> list[dict[str, Any]]:
    _, table = _connect(data_dir)
    if table is None:
        return []
    return (
        table.search(vector)
        .metric("cosine")
        .limit(top_k)
        .to_list()
    )


def _format_snippets(rows: list[dict[str, Any]]) -> list[str]:
    lines = []
    for row in rows:
        parts = [str(row[k]) for k in ("facility",) if row.get(k)]
        if row.get("extractor"):
            parts.append(f"extractor={row['extractor']}")
        text = str(row.get("text") or "")[:SNIPPET_LEN]
        prefix = f"[{', '.join(parts)}] " if parts else ""
        lines.append(f"- {prefix}{text}")
    return lines


async def build_context(
    client: QvacClient | None,
    message: str,
    *,
    data_dir: str,
    top_k: int,
) -> str:
    """Spanish context block for the system prompt: retrieval + graph, or ""."""
    sections: list[str] = []

    if client is not None:
        rows = await retrieve(client, message, data_dir=data_dir, top_k=top_k)
        if rows:
            sections.append("Observaciones previas similares:\n" + "\n".join(
                _format_snippets(rows)
            ))

    facility = detect_facility(message)
    if facility:
        graph = await graph_context(facility)
        if graph:
            sections.append(f"Equipos conocidos en {facility}:\n{graph}")

    if not sections:
        return ""
    return "Contexto previo de la base de conocimiento:\n" + "\n\n".join(sections)
