"""Graph-neighborhood context for the RAG prompt (facility -> equipment).

Read-only: reuses the engine's driver; returns "" when Neo4j is down or the
facility is unknown, so retrieval never breaks the chat stream.
"""

from __future__ import annotations

import logging

from app.graph import engine

logger = logging.getLogger("synapse.graph")


async def graph_context(facility_name: str) -> str:
    """Equipment summary lines for a facility, "" when unavailable.

    One cypher query over the facility's equipment, ordered by modality.
    """
    if engine.driver() is None or not facility_name:
        return ""
    try:
        facility = await engine.find_facility(facility_name)
        if facility is None:
            return ""
        async with engine.driver().session() as session:
            result = await session.run(
                "MATCH (f:Facility {id: $fid})-[:HAS]->(e:Equipment) "
                "RETURN e.modality AS modality, e.manufacturer AS manufacturer, "
                "       e.model AS model, e.state AS state, "
                "       e.quantity AS quantity, e.age_years AS age_years "
                "ORDER BY modality",
                {"fid": facility["id"]},
            )
            rows = [dict(r) async for r in result]
    except Exception as exc:  # noqa: BLE001 - context is best-effort
        logger.debug("Contexto de grafo no disponible: %s", exc)
        return ""

    lines: list[str] = []
    for row in rows:
        parts = []
        if row.get("state"):
            parts.append(f"estado: {row['state']}")
        if row.get("quantity"):
            parts.append(f"cant: {row['quantity']}")
        if row.get("age_years"):
            parts.append(f"edad: {row['age_years']}")
        suffix = f" ({', '.join(parts)})" if parts else ""
        label = " ".join(
            str(row[k]) for k in ("modality", "manufacturer", "model") if row.get(k)
        )
        lines.append(f"- {label}{suffix}".rstrip())
    return "\n".join(lines)
