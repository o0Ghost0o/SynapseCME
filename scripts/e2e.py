"""End-to-end validation of the SynapseCME stack against live local services.

Checks the full flow: chat (SSE) -> graph mutation -> hierarchy/network reads ->
transaction_log/perf_log rows -> WS presence + tx broadcast.

Env overrides:
    API_BASE        default http://localhost:8000
    NEO4J_URI       default bolt://localhost:7687
    NEO4J_USER      default neo4j
    NEO4J_PASSWORD  default synapse-local-dev
    POSTGRES_DSN    default postgresql://synapse:synapse-local-dev@localhost:5432/synapse_state

QVAC may be down: the rule-based fallback path is expected and still logs perf.
Exit code 0 = all checks passed, 1 = at least one failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import websockets

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

API_BASE = os.environ.get("API_BASE", "http://localhost:8000").rstrip("/")
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "synapse-local-dev")
POSTGRES_DSN = os.environ.get(
    "POSTGRES_DSN",
    "postgresql://synapse:synapse-local-dev@localhost:5432/synapse_state",
)

CHAT_MESSAGE = (
    "Visité el Hospital Aurora en Panamá, vi 2 tomógrafos Siemens de unos 6 años"
)

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def summary() -> int:
    failed = [n for n, ok, _ in _results if not ok]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} checks passed")
    if failed:
        print("FAILURES: " + ", ".join(failed))
        return 1
    print("E2E OK")
    return 0


def parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def read_events_until(
    ws, wanted: set[str], timeout: float = 20.0
) -> dict[str, dict]:
    """Read WS messages until all types in `wanted` have been seen."""
    seen: dict[str, dict] = {}
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while wanted - set(seen):
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            if msg.get("type") in wanted and msg["type"] not in seen:
                seen[msg["type"]] = msg
    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
        pass
    return seen


async def run() -> int:
    print(f"API_BASE={API_BASE} (QVAC expected up or down; fallback OK)")

    # -- Step 1: health ------------------------------------------------------
    print("\n[1] Backend health")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as http:
        try:
            r = await http.get("/api/health")
            check("GET /api/health", r.status_code == 200 and r.json().get("status") == "ok",
                  f"status={r.status_code} body={r.json()}")
        except httpx.HTTPError as exc:
            check("GET /api/health", False, f"no alcanzable: {exc}")
            return summary()

    # -- Step 2: WS connect + presence, then chat that triggers a mutation --
    print("\n[2] Chat SSE + WS live broadcast")
    ws_url = API_BASE.replace("http", "ws") + "/ws/events"
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"type": "hello", "client_type": "dashboard", "name": "e2e-bot"}))
        presence_events = await read_events_until(ws, {"presence"})
        presence_msg = presence_events.get("presence")
        check(
            "WS hello -> presence",
            presence_msg is not None
            and any(c.get("name") == "e2e-bot" for c in presence_msg.get("clients", [])),
            str(presence_msg)[:120],
        )

        async def post_chat() -> httpx.Response:
            async with httpx.AsyncClient(base_url=API_BASE, timeout=60.0) as c:
                return await c.post("/api/chat", json={
                    "message": CHAT_MESSAGE,
                    "contributor": "e2e-bot",
                    "client_type": "field_app",
                })

        chat_task = asyncio.create_task(post_chat())
        # mutation is broadcast before tx; capture both in one pass
        live = await read_events_until(ws, {"tx", "mutation"}, timeout=30.0)
        tx_msg = live.get("tx")
        check(
            "WS tx broadcast on mutation",
            tx_msg is not None and tx_msg.get("entry", {}).get("actor") == "e2e-bot",
            str(tx_msg)[:140],
        )
        check("WS mutation broadcast", "mutation" in live, str(live.get("mutation"))[:120])
        resp = await chat_task

    check("POST /api_chat status", resp.status_code == 200, f"status={resp.status_code}")
    check(
        "POST /api/chat content-type SSE",
        "text/event-stream" in resp.headers.get("content-type", ""),
        resp.headers.get("content-type", ""),
    )
    events = parse_sse(resp.text)
    by_type = [e.get("type") for e in events]
    check("SSE has extraction event", "extraction" in by_type, f"events={by_type}")
    check("SSE has done event", by_type and by_type[-1] == "done", f"order={by_type}")

    extraction = next((e for e in events if e.get("type") == "extraction"), {})
    data = extraction.get("data", {})
    items = data.get("items", [])
    ct = next((i for i in items if i.get("modality") == "CT"), None)
    check(
        "extraction: Hospital Aurora + Siemens CT qty 2",
        data.get("facility") == "Hospital Aurora"
        and ct is not None
        and ct.get("manufacturer") == "Siemens"
        and ct.get("quantity") == 2,
        f"facility={data.get('facility')} items={items}",
    )
    check(
        "done carries transaction_id",
        bool(next((e for e in events if e.get("type") == "done"), {}).get("transaction_id")),
        "",
    )

    # -- Step 3: graph reads --------------------------------------------------
    print("\n[3] Graph reads")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as http:
        r = await http.get("/api/hierarchy")
        hierarchy = r.json()
        fac_names = [
            f["name"]
            for region in hierarchy.get("regions", [])
            for country in region.get("countries", [])
            for f in country.get("facilities", [])
        ]
        check("hierarchy includes Hospital Aurora", "Hospital Aurora" in fac_names,
              f"facilities={fac_names}")

        r = await http.get("/api/network")
        network = r.json()
        aurora_nodes = [
            n for n in network.get("nodes", [])
            if n.get("type") == "Facility" and "Aurora" in n.get("label", "")
        ]
        check(
            "network has Aurora facility node with links",
            bool(aurora_nodes) and any(
                l["source"] in {n["id"] for n in aurora_nodes}
                or l["target"] in {n["id"] for n in aurora_nodes}
                for l in network.get("links", [])
            ),
            f"nodes={len(network.get('nodes', []))} links={len(network.get('links', []))}",
        )

        if aurora_nodes:
            r = await http.get(f"/api/facility/{aurora_nodes[0]['id']}")
            detail = r.json()
            ct_nodes = [
                e for e in detail.get("equipment", [])
                if e.get("modality") == "CT" and e.get("manufacturer") == "Siemens"
            ]
            check(
                "facility detail: Siemens CT with observation",
                r.status_code == 200 and bool(ct_nodes)
                and any(e.get("observations") for e in ct_nodes),
                f"equipment={[(e.get('modality'), e.get('manufacturer'), e.get('state')) for e in detail.get('equipment', [])]}",
            )

    # -- Step 4: direct DB verification ---------------------------------------
    print("\n[4] Direct Neo4j / Postgres verification")
    from neo4j import GraphDatabase

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as s:
            row = s.run(
                "MATCH (f:Facility {name: 'Hospital Aurora'})-[:HAS]->(e:Equipment) "
                "WHERE e.manufacturer = 'Siemens' AND e.modality = 'CT' "
                "RETURN count(e) AS n"
            ).single()
        driver.close()
        check("Neo4j: Aurora CT Siemens exists", bool(row and row["n"] >= 1),
              f"count={row['n'] if row else None}")
    except Exception as exc:  # noqa: BLE001
        check("Neo4j: Aurora CT Siemens exists", False, str(exc)[:120])

    try:
        import asyncpg

        async def pg_checks() -> tuple[int, int]:
            conn = await asyncpg.connect(POSTGRES_DSN)
            tx = await conn.fetchval(
                "SELECT count(*) FROM transaction_log WHERE actor = 'e2e-bot'"
            )
            perf = await conn.fetchval("SELECT count(*) FROM perf_log")
            await conn.close()
            return tx, perf

        tx_count, perf_count = await pg_checks()
        check("Postgres: transaction_log rows for e2e-bot", tx_count >= 1, f"rows={tx_count}")
        check("Postgres: perf_log has entries (fallback logs metrics)", perf_count >= 1,
              f"rows={perf_count}")
    except Exception as exc:  # noqa: BLE001
        check("Postgres: transaction_log rows for e2e-bot", False, str(exc)[:120])
        check("Postgres: perf_log has entries (fallback logs metrics)", False, "")

    # -- Step 5: API metrics/transactions --------------------------------------
    print("\n[5] Metrics + transactions endpoints")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as http:
        r = await http.get("/api/metrics")
        entries = r.json().get("entries", [])
        check(
            "/api/metrics shows a perf entry",
            r.status_code == 200 and bool(entries)
            and {"model", "ttft_ms", "total_ms", "throughput_tps"} <= set(entries[0]),
            f"entries={len(entries)}",
        )
        r = await http.get("/api/transactions", params={"limit": 10})
        entries = r.json().get("entries", [])
        check(
            "/api/transactions has e2e-bot entry",
            r.status_code == 200 and any(e.get("actor") == "e2e-bot" for e in entries),
            f"entries={len(entries)}",
        )
        r = await http.get("/api/transactions/export.csv")
        check(
            "CSV export works",
            r.status_code == 200 and r.text.startswith("id,actor"),
            f"content-type={r.headers.get('content-type')}",
        )

    return summary()


def main() -> None:
    code = asyncio.run(run())
    sys.exit(code)


if __name__ == "__main__":
    main()
