"""Neo4j graph engine: driver lifecycle, schema bootstrap, MERGE-based ingestion.

Writes are MERGE-based and idempotent. Every mutation logs a transaction_log
row (PostgreSQL) and broadcasts a WS event. If Neo4j is down the driver stays
None and all reads return empty results so the API degrades gracefully.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app import db
from app.core.config import Settings
from app.core.events import bus
from app.graph.states import Vote, consensus, parse_state, state_transition
from app.models import ExtractionResult, IngestResult

logger = logging.getLogger("synapse.graph")

SCHEMA_PATH = Path(__file__).with_name("schema.cypher")

# Rough country -> region mapping for the Region node level.
REGION_MAP = {
    "panamá": "América Latina",
    "mexico": "América Latina",
    "méxico": "América Latina",
    "colombia": "América Latina",
    "argentina": "América Latina",
    "chile": "América Latina",
    "perú": "América Latina",
    "peru": "América Latina",
    "ecuador": "América Latina",
    "brasil": "América Latina",
    "costa rica": "América Latina",
    "guatemala": "América Latina",
    "españa": "Europa",
    "spain": "Europa",
    "francia": "Europa",
    "alemania": "Europa",
    "estados unidos": "Norteamérica",
    "usa": "Norteamérica",
}

NETWORK_NODE_LIMIT = 500

_driver: AsyncDriver | None = None


def init_driver(settings: Settings) -> bool:
    global _driver
    try:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info("Driver Neo4j inicializado (%s)", settings.neo4j_uri)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Neo4j no disponible (%s); operaciones de grafo desactivadas", exc)
        _driver = None
        return False


def driver() -> AsyncDriver | None:
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def check_connectivity() -> bool:
    if _driver is None:
        return False
    try:
        await _driver.verify_connectivity()
        return True
    except Exception:  # noqa: BLE001
        return False


async def bootstrap_schema() -> None:
    """Execute schema.cypher statement-by-statement (all idempotent)."""
    if _driver is None:
        return
    statements = [
        line.strip()
        for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]
    async with _driver.session() as session:
        for stmt in statements:
            await session.run(stmt)
    logger.info("Esquema del grafo verificado (%d sentencias)", len(statements))


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def find_facility(name: str) -> dict[str, Any] | None:
    """Duplicate detection: full-text index first, fuzzy CONTAINS fallback."""
    if _driver is None or not name:
        return None
    async with _driver.session() as session:
        try:
            result = await session.run(
                "CALL db.index.fulltext.queryNodes('facilitySearch', $q) "
                "YIELD node, score RETURN node.id AS id, node.name AS name "
                "ORDER BY score DESC LIMIT 3",
                {"q": _sanitize_ft_query(name)},
            )
            rows = [dict(r) async for r in result]
        except Exception:  # noqa: BLE001 - index may not exist yet
            rows = []
        if rows:
            # Exact/near match on the top hit
            top = rows[0]
            if top["name"].strip().lower() == name.strip().lower():
                return top
        # Fallback: substring match both ways
        result = await session.run(
            "MATCH (f:Facility) WHERE toLower(f.name) CONTAINS toLower($q) "
            "OR toLower($q) CONTAINS toLower(f.name) "
            "RETURN f.id AS id, f.name AS name LIMIT 3",
            {"q": name.strip()},
        )
        rows = [dict(r) async for r in result]
        for row in rows:
            if row["name"].strip().lower() == name.strip().lower():
                return row
        return rows[0] if rows else None


def _sanitize_ft_query(name: str) -> str:
    # Escape lucene special chars, keep alphanumeric words
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in name)
    return cleaned.strip() or name


async def ingest_extraction(
    ext: ExtractionResult,
    contributor: str,
    client_type: str | None,
    full_name: str | None = None,
) -> IngestResult:
    """MERGE the extracted hierarchy + observation, apply consensus states."""
    result = IngestResult()
    if _driver is None:
        return result
    if not ext.facility:
        logger.info("Extracción sin facilidad; nada que ingerir")
        return result

    existing = await find_facility(ext.facility)
    facility_id = existing["id"] if existing else _new_id("fac")
    result.facility_created = existing is None
    result.facility_id = facility_id

    region_name = REGION_MAP.get((ext.country or "").strip().lower(), "Otras regiones")
    city_name = ext.city or "Ciudad sin especificar"
    country_name = ext.country or "País sin especificar"

    async with _driver.session() as session:
        await session.execute_write(
            _merge_hierarchy,
            region_name=region_name,
            country_name=country_name,
            city_name=city_name,
            facility_id=facility_id,
            facility_name=ext.facility.strip(),
        )
        result.mutation_summary = (
            f"Facilidad {ext.facility} vinculada a {city_name}, {country_name}"
        )

        if existing is None:
            entry = await db.log_transaction(
                actor=contributor,
                client_type=client_type,
                action="create",
                target_type="Facility",
                target_id=facility_id,
                target_name=ext.facility,
                payload={"city": city_name, "country": country_name, "region": region_name,
                         "full_name": full_name},
            )
            if entry is not None:
                result.transaction_ids.append(entry["id"])
            await _emit_tx(entry, f"Nueva facilidad registrada: {ext.facility}")

        obs_id = _new_id("obs")
        for item in ext.items:
            # Duplicate detection: same facility + modality; prefer an exact
            # manufacturer/model match, else reuse the unit whose manufacturer
            # is still unknown so a later identification upgrades it.
            candidates = await session.run(
                "MATCH (f:Facility {id: $fid})-[:HAS]->(e:Equipment {modality: $modality}) "
                "RETURN e.id AS id, e.manufacturer AS manufacturer, e.model AS model, "
                "       e.state AS state",
                {"fid": facility_id, "modality": item.modality},
            )
            rows = [dict(r) async for r in candidates]
            target = _pick_equipment(rows, item.manufacturer, item.model)
            equipment_id = target["id"] if target else _new_id("eq")

            tx = await session.execute_write(
                _merge_equipment_and_observation,
                facility_id=facility_id,
                equipment_id=equipment_id,
                equip_key=item.model or item.manufacturer or "sin-modelo",
                obs_id=obs_id if len(ext.items) == 1 else _new_id("obs"),
                contributor=contributor,
                item=item.model_dump(),
                text=ext.raw or "",
                confidence=item.confidence,
            )
            equipment_id = tx["equipment_id"]
            created = tx["created"]
            result.equipment_ids.append(equipment_id)

            # Consensus: gather all votes for this equipment's attributes.
            votes_rows = await session.run(
                "MATCH (o:Observation)-[:OBSERVED]->(e:Equipment {id: $eid}) "
                "OPTIONAL MATCH (o)-[:MADE_BY]->(c:Contributor) "
                "RETURN coalesce(c.name, 'anon') AS contributor, "
                "       o.confidence AS confidence",
                {"eid": equipment_id},
            )
            rows = [dict(r) async for r in votes_rows]
            n_contributors = len({r["contributor"] for r in rows})
            new_state, _, _ = consensus(_expand_votes(rows))

            old_state = parse_state(tx.get("state"))
            transition = state_transition(old_state, new_state)
            if transition or created:
                await session.run(
                    "MATCH (e:Equipment {id: $eid}) SET e.state = $state",
                    {"eid": equipment_id, "state": new_state.value},
                )

            action = "create" if created else ("promote" if transition else "merge")
            label = f"{item.modality} {item.manufacturer or ''}".strip()
            if transition:
                await db.log_state_transition(
                    equipment_id, "exists", old_state.value, new_state.value,
                    item.confidence, obs_id,
                )
                summary = (
                    f"{label} en {ext.facility}: {transition} "
                    f"({n_contributors} contribuyentes)"
                )
            else:
                summary = f"{label} observado en {ext.facility}"
            result.mutation_summary += f"; {summary}"

            entry = await db.log_transaction(
                actor=contributor,
                client_type=client_type,
                action=action,
                target_type="Equipment",
                target_id=equipment_id,
                target_name=f"{ext.facility} · {label}",
                state_transition=transition,
                payload={
                    "facility_id": facility_id,
                    "modality": item.modality,
                    "manufacturer": item.manufacturer,
                    "model": item.model,
                    "quantity": item.quantity,
                    "age_years": item.age_years,
                    "confidence": item.confidence,
                    "full_name": full_name,
                },
            )
            if entry is not None:
                result.transaction_ids.append(entry["id"])
            await _emit_tx(entry, summary)

    return result


def _expand_votes(rows: list[dict[str, Any]]) -> list[Vote]:
    """One vote per contributing observation (value = 'exists' for the unit)."""
    votes: list[Vote] = []
    for r in rows:
        votes.append(
            Vote(
                value="exists",
                confidence=float(r["confidence"] or 0.5),
                contributor=str(r["contributor"] or "anon"),
            )
        )
    return votes


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _pick_equipment(
    candidates: list[dict[str, Any]], manufacturer: str | None, model: str | None
) -> dict[str, Any] | None:
    """Choose the existing equipment node an observation most likely refers to.

    Returns None when the observation identifies a unit that conflicts with
    every known candidate (e.g. reports Siemens where only a GE unit is
    known) so the caller creates a new node instead of overwriting data.
    """
    if not candidates:
        return None
    mfr, mdl = _norm(manufacturer), _norm(model)
    if mfr:
        for c in candidates:
            if _norm(c.get("manufacturer")) == mfr:
                return c
        # Upgrade an unidentified unit with this identification.
        for c in candidates:
            if not c.get("manufacturer"):
                return c
        # Known manufacturers conflict: this is a different unit.
        return None
    if mdl:
        for c in candidates:
            if _norm(c.get("model")) == mdl:
                return c
        for c in candidates:
            if not c.get("model"):
                return c
        return None
    # No manufacturer/model reported: reuse the first candidate (the
    # merge keeps whichever attributes are already known).
    return candidates[0]


async def _merge_hierarchy(
    tx: Any,
    region_name: str,
    country_name: str,
    city_name: str,
    facility_id: str,
    facility_name: str,
) -> None:
    await tx.run(
        "MERGE (r:Region {name: $region}) "
        "MERGE (c:Country {name: $country}) "
        "MERGE (ci:City {name: $city}) "
        "MERGE (f:Facility {id: $fid}) "
        "ON CREATE SET f.name = $fname, f.created_at = datetime() "
        "ON MATCH SET f.name = coalesce(f.name, $fname) "
        "MERGE (r)-[:HAS]->(c) "
        "MERGE (c)-[:HAS]->(ci) "
        "MERGE (ci)-[:HAS]->(f)",
        region=region_name,
        country=country_name,
        city=city_name,
        fid=facility_id,
        fname=facility_name,
    )


async def _merge_equipment_and_observation(
    tx: Any,
    facility_id: str,
    equipment_id: str,
    equip_key: str,
    obs_id: str,
    contributor: str,
    item: dict[str, Any],
    text: str,
    confidence: float,
) -> dict[str, Any]:
    # The caller pre-resolves the equipment id (duplicate detection); create
    # the node only when nothing exists under that id yet.
    # Parameters merge idempotently per (source_observation_id, name).
    parameters = [
        {
            "id": _new_id("par"),
            "name": p["name"],
            "value": p.get("value"),
            "unit": p.get("unit"),
            "status": p.get("status"),
        }
        for p in (item.get("parameters") or [])
        if p.get("name")
    ]
    result = await tx.run(
        "MATCH (f:Facility {id: $fid}) "
        "OPTIONAL MATCH (existing:Equipment {id: $eid}) "
        "WITH f, existing "
        "FOREACH (_ IN CASE WHEN existing IS NULL THEN [1] ELSE [] END | "
        "  CREATE (e:Equipment {id: $eid, facility_key: $fkey, state: 'Desconocido'}) "
        "  MERGE (f)-[:HAS]->(e)) "
        "WITH f, existing, coalesce(existing.id, $eid) AS real_id "
        "MATCH (e:Equipment {id: real_id}) "
        "SET e.modality = $modality, "
        "    e.manufacturer = coalesce($manufacturer, e.manufacturer), "
        "    e.model = coalesce($model, e.model), "
        "    e.quantity = coalesce($quantity, e.quantity, 1), "
        "    e.age_years = coalesce($age_years, e.age_years), "
        "    e.facility_id = $fid "
        "MERGE (c:Contributor {name: $contributor}) "
        "CREATE (o:Observation {id: $oid, text: $text, confidence: $confidence, "
        "                       created_at: datetime()}) "
        "MERGE (o)-[:OBSERVED]->(e) "
        "MERGE (o)-[:MADE_BY]->(c) "
        "FOREACH (p IN $par_list | "
        "  MERGE (par:Parameter {source_observation_id: $oid, name: p.name}) "
        "  ON CREATE SET par.id = p.id, par.value = p.value, par.unit = p.unit, "
        "                par.status = p.status, par.created_at = datetime() "
        "  MERGE (par)-[:MEASURED_ON]->(e)) "
        "RETURN e.id AS equipment_id, e.state AS state, "
        "       (existing IS NULL) AS created",
        fid=facility_id,
        fkey=f"{facility_id}:{item['modality']}:{equip_key}",
        eid=equipment_id,
        modality=item["modality"],
        manufacturer=item.get("manufacturer"),
        model=item.get("model"),
        quantity=item.get("quantity"),
        age_years=item.get("age_years"),
        contributor=contributor,
        oid=obs_id,
        text=text,
        confidence=confidence,
        par_list=parameters,
    )
    record = await result.single()
    return dict(record) if record else {"equipment_id": equipment_id, "created": True}


async def _emit_tx(entry: dict[str, Any] | None, summary: str) -> None:
    await bus.broadcast({"type": "mutation", "summary": summary})
    if entry is not None:
        await bus.broadcast({"type": "tx", "entry": entry})


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get_facility_detail(facility_id: str) -> dict[str, Any] | None:
    if _driver is None:
        return None
    async with _driver.session() as session:
        result = await session.run(
            "MATCH (f:Facility {id: $fid}) "
            "OPTIONAL MATCH (f)<-[:HAS]-(ci:City)<-[:HAS]-(co:Country)<-[:HAS]-(r:Region) "
            "RETURN f.id AS id, f.name AS name, ci.name AS city, co.name AS country, "
            "       r.name AS region LIMIT 1",
            {"fid": facility_id},
        )
        row = await result.single()
        if row is None:
            return None
        facility = dict(row)

        result = await session.run(
            "MATCH (f:Facility {id: $fid})-[:HAS]->(e:Equipment) "
            "OPTIONAL MATCH (o:Observation)-[:OBSERVED]->(e) "
            "OPTIONAL MATCH (o)-[:MADE_BY]->(c:Contributor) "
            "RETURN e.id AS id, e.modality AS modality, e.manufacturer AS manufacturer, "
            "       e.model AS model, e.quantity AS quantity, e.age_years AS age_years, "
            "       e.state AS state, "
            "       collect({id: o.id, contributor: c.name, text: o.text, "
            "                 confidence: o.confidence, "
            "                 created_at: toString(o.created_at)}) "
            "         AS observations ORDER BY e.id",
            {"fid": facility_id},
        )
        equipment = []
        async for r in result:
            d = dict(r)
            d["observations"] = [o for o in d["observations"] if o.get("id")]
            equipment.append(d)
        return {"facility": facility, "equipment": equipment}


async def get_hierarchy() -> dict[str, Any]:
    if _driver is None:
        return {"regions": []}
    async with _driver.session() as session:
        result = await session.run(
            "MATCH (r:Region)-[:HAS]->(c:Country) "
            "OPTIONAL MATCH (c)-[:HAS*1..2]->(f:Facility) "
            "RETURN r.name AS region, c.name AS country, "
            "       collect(DISTINCT {id: f.id, name: f.name}) AS facilities "
            "ORDER BY region, country"
        )
        regions: dict[str, dict[str, Any]] = {}
        async for row in result:
            d = dict(row)
            region = regions.setdefault(d["region"], {"name": d["region"], "countries": {}})
            facilities = [f for f in d["facilities"] if f.get("id")]
            region["countries"][d["country"]] = {
                "name": d["country"],
                "facilities": facilities,
            }
        return {
            "regions": [
                {**r, "countries": list(r["countries"].values())}
                for r in regions.values()
            ]
        }


async def get_network(limit: int = NETWORK_NODE_LIMIT) -> dict[str, Any]:
    """Full graph dump for the viz, capped at ``limit`` nodes."""
    if _driver is None:
        return {"nodes": [], "links": []}
    async with _driver.session() as session:
        result = await session.run(
            "MATCH (n) RETURN elementId(n) AS eid, labels(n) AS labels, n "
            "LIMIT $limit",
            {"limit": limit},
        )
        nodes: list[dict[str, Any]] = []
        key_by_eid: dict[str, str] = {}
        ids: set[str] = set()
        async for row in result:
            eid = row["eid"]
            ids.add(eid)
            node = dict(row["n"])
            labels = row["labels"]
            ntype = labels[0] if labels else "Node"
            label = (
                node.get("name")
                or node.get("model")
                or node.get("modality")
                or node.get("text", "")[:40]
                or node.get("id", eid)
            )
            # Business key (property id or name), so ids from this dump can be
            # used with /api/facility/{facility_id}; fall back to elementId.
            key = str(node.get("id") or node.get("name") or eid)
            key_by_eid[eid] = key
            nodes.append(
                {
                    "id": key,
                    "label": str(label),
                    "type": ntype,
                    "state": node.get("state"),
                }
            )
        if not ids:
            return {"nodes": [], "links": []}
        result = await session.run(
            "MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids AND elementId(b) IN $ids "
            "RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type",
            {"ids": list(ids)},
        )
        links = [
            {
                "source": key_by_eid.get(r["source"], r["source"]),
                "target": key_by_eid.get(r["target"], r["target"]),
                "type": r["type"],
            }
            async for r in result
        ]
        return {"nodes": nodes, "links": links}


def _row_to_parameter(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "value": row["value"],
        "unit": row["unit"],
        "status": row["status"],
        "source_observation_id": row["source_observation_id"],
        "created_at": row["created_at"],
    }


async def get_equipment_detail(equipment_id: str) -> dict[str, Any] | None:
    """Equipo + observaciones + parámetros (último por nombre + historial)."""
    if _driver is None:
        return None
    async with _driver.session() as session:
        result = await session.run(
            "MATCH (e:Equipment {id: $eid}) "
            "OPTIONAL MATCH (f:Facility)-[:HAS]->(e) "
            "OPTIONAL MATCH (f)<-[:HAS]-(ci:City)<-[:HAS]-(co:Country) "
            "RETURN e.id AS id, e.modality AS modality, e.manufacturer AS manufacturer, "
            "       e.model AS model, e.quantity AS quantity, e.age_years AS age_years, "
            "       e.state AS state, f.id AS facility_id, f.name AS facility_name, "
            "       ci.name AS city, co.name AS country LIMIT 1",
            {"eid": equipment_id},
        )
        row = await result.single()
        if row is None:
            return None
        equipment = dict(row)

        result = await session.run(
            "MATCH (e:Equipment {id: $eid}) "
            "OPTIONAL MATCH (o:Observation)-[:OBSERVED]->(e) "
            "OPTIONAL MATCH (o)-[:MADE_BY]->(c:Contributor) "
            "RETURN o.id AS id, c.name AS contributor, o.text AS text, "
            "       o.confidence AS confidence, toString(o.created_at) AS created_at "
            "ORDER BY o.created_at DESC",
            {"eid": equipment_id},
        )
        observations = [dict(r) async for r in result if r["id"]]

        result = await session.run(
            "MATCH (p:Parameter)-[:MEASURED_ON]->(:Equipment {id: $eid}) "
            "RETURN p.id AS id, p.name AS name, p.value AS value, p.unit AS unit, "
            "       p.status AS status, p.source_observation_id AS source_observation_id, "
            "       toString(p.created_at) AS created_at "
            "ORDER BY p.created_at DESC",
            {"eid": equipment_id},
        )
        history = [_row_to_parameter(dict(r)) async for r in result]

    # Último valor por nombre (el historial ya viene ordenado desc).
    latest: dict[str, dict[str, Any]] = {}
    for p in history:
        latest.setdefault(p["name"], p)
    return {
        "equipment": equipment,
        "observations": observations,
        "parameters": list(latest.values()),
        "parameter_history": history,
    }


_EQUIPMENT_FILTERS = (
    "($modality IS NULL OR e.modality = $modality) "
    "AND ($manufacturer IS NULL OR toLower(coalesce(e.manufacturer, '')) "
    "     CONTAINS toLower($manufacturer)) "
    "AND ($state IS NULL OR e.state = $state) "
    "AND ($country IS NULL OR co.name = $country) "
    "AND ($facility IS NULL OR f.id = $facility "
    "     OR toLower(f.name) CONTAINS toLower($facility)) "
    "AND ($q IS NULL OR toLower(coalesce(e.manufacturer, '') + ' ' + "
    "     coalesce(e.model, '')) CONTAINS toLower($q)) "
    "AND (NOT $has_issue OR EXISTS { "
    "      MATCH (pi:Parameter)-[:MEASURED_ON]->(e) "
    "      WHERE pi.status IN ['warning', 'critical'] }) "
)

_EQUIPMENT_MATCH = (
    "MATCH (f:Facility)-[:HAS]->(e:Equipment) "
    "OPTIONAL MATCH (f)<-[:HAS]-(ci:City)<-[:HAS]-(co:Country) "
    f"WHERE {_EQUIPMENT_FILTERS}"
)


async def list_equipments(
    modality: str | None = None,
    manufacturer: str | None = None,
    state: str | None = None,
    country: str | None = None,
    facility: str | None = None,
    q: str | None = None,
    has_issue: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Lista plana de equipos con filtros parametrizados y paginación."""
    if _driver is None:
        return {"total": 0, "items": [], "limit": limit, "offset": offset}
    params = {
        "modality": modality or None,
        "manufacturer": manufacturer or None,
        "state": state or None,
        "country": country or None,
        "facility": facility or None,
        "q": q or None,
        "has_issue": has_issue,
        "limit": max(min(limit, 500), 1),
        "offset": max(offset, 0),
    }
    async with _driver.session() as session:
        result = await session.run(
            f"{_EQUIPMENT_MATCH} RETURN count(DISTINCT e) AS total",
            params,
        )
        row = await result.single()
        total = int(row["total"]) if row else 0

        result = await session.run(
            f"{_EQUIPMENT_MATCH} "
            "RETURN e.id AS id, e.modality AS modality, e.manufacturer AS manufacturer, "
            "       e.model AS model, e.quantity AS quantity, e.age_years AS age_years, "
            "       e.state AS state, f.id AS facility_id, f.name AS facility_name, "
            "       ci.name AS city, co.name AS country, "
            "       EXISTS { MATCH (pi:Parameter)-[:MEASURED_ON]->(e) "
            "                WHERE pi.status IN ['warning', 'critical'] } AS has_issue "
            "ORDER BY f.name, e.id "
            "SKIP $offset LIMIT $limit",
            params,
        )
        items = [dict(r) async for r in result]
    return {"total": total, "items": items, "limit": params["limit"], "offset": params["offset"]}
