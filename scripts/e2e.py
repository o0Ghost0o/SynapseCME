"""End-to-end validation of the SynapseCME stack against live local services.

Checks the full flow: auth (login/roles/identity) -> chat (SSE) -> graph
mutation -> hierarchy/network reads -> transaction_log/perf_log rows ->
WS presence + tx broadcast.

Env overrides:
    API_BASE        default http://localhost:8000
    ADMIN_USER      default admin
    ADMIN_PASSWORD  default synapse-admin
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
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import websockets

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

API_BASE = os.environ.get("API_BASE", "http://localhost:8000").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "synapse-admin")

# Run-scoped assertions: everything created before this instant is ignored,
# so the suite passes on a dirty DB. UTC epoch seconds.
STARTED_AT = time.time()

NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "synapse-local-dev")
POSTGRES_DSN = os.environ.get(
    "POSTGRES_DSN",
    "postgresql://synapse:synapse-local-dev@localhost:5432/synapse_state",
)


def _host_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _container_ip(container: str) -> str | None:
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f",
             "{{.NetworkSettings.Networks.synapsecme_default.IPAddress}}", container],
            capture_output=True, text=True, timeout=10,
        )
        ip = out.stdout.strip()
        return ip or None
    except Exception:  # noqa: BLE001 - docker unavailable or layout differs
        return None


def _resolve_uri(env_var: str, container: str, default_host: str, port: int,
                 scheme: str) -> str:
    """Env var wins; else localhost if open; else the container's bridge IP.

    The compose file no longer publishes host ports, so on a dev host the
    direct-DB checks must reach the container network.
    """
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit
    if _host_port_open(default_host, port):
        return f"{scheme}://{default_host}:{port}"
    ip = _container_ip(container)
    if ip:
        return f"{scheme}://{ip}:{port}"
    return f"{scheme}://{default_host}:{port}"


NEO4J_URI = _resolve_uri("NEO4J_URI", "synapse-neo4j", "localhost", 7687, "bolt")


def _resolve_pg_dsn() -> str:
    explicit = os.environ.get("POSTGRES_DSN")
    if explicit:
        return explicit
    if _host_port_open("localhost", 5432):
        return POSTGRES_DSN
    ip = _container_ip("synapse-postgres")
    if ip:
        return f"postgresql://synapse:synapse-local-dev@{ip}:5432/synapse_state"
    return POSTGRES_DSN


POSTGRES_DSN = _resolve_pg_dsn()

CHAT_MESSAGE = (
    "Visité el Hospital Aurora en Panamá, vi 2 tomógrafos Siemens de unos 6 años"
)
SPOOFED_CONTRIBUTOR = "usurero-malicioso"

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

    # -- Step 1: health + login ------------------------------------------------
    print("\n[1] Health + admin login")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as http:
        try:
            r = await http.get("/api/health")
            check("GET /api/health (sin token)", r.status_code == 200 and r.json().get("status") == "ok",
                  f"status={r.status_code} body={r.json()}")
        except httpx.HTTPError as exc:
            check("GET /api/health (sin token)", False, f"no alcanzable: {exc}")
            return summary()

        r = await http.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
        check("POST /api/auth/login (admin)", r.status_code == 200,
              f"status={r.status_code} {r.text[:120]}")
        if r.status_code != 200:
            return summary()
        pair = r.json()
        token = pair["access_token"]
        refresh = pair["refresh_token"]
        check("login devuelve user + expires_in=900",
              pair.get("expires_in") == 900
              and pair.get("user", {}).get("username") == ADMIN_USER
              and pair.get("token_type") == "bearer", "")
        auth = {"Authorization": f"Bearer {token}"}

        r = await http.get("/api/auth/me", headers=auth)
        check("GET /api/auth/me", r.status_code == 200 and r.json().get("role") == "admin",
              f"status={r.status_code} body={r.text[:100]}")

        r = await http.post("/api/auth/refresh", json={"refresh_token": refresh})
        check("POST /api/auth/refresh (rotación)",
              r.status_code == 200 and r.json().get("refresh_token") != refresh, "")
        rotated = r.json()
        r = await http.post("/api/auth/refresh", json={"refresh_token": refresh})
        check("refresh revocado (reuse) -> 401", r.status_code == 401, f"status={r.status_code}")
        token = rotated["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # authenticated request without token must 401
        r = await http.get("/api/hierarchy")
        check("sin token -> 401", r.status_code == 401, f"status={r.status_code}")

    # -- Step 2: user management + role enforcement ------------------------------
    print("\n[2] Roles: viewer 403 en chat, user mgmt admin-only")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as http:
        viewer_user, viewer_pass = "e2e.viewer", "viewer-pass-123"
        r = await http.post("/api/auth/users", headers=auth, json={
            "username": viewer_user, "password": viewer_pass,
            "full_name": "Visor E2E", "role": "viewer",
        })
        check("POST /api/auth/users (admin crea viewer)", r.status_code in (201, 409),
              f"status={r.status_code}")
        r = await http.get("/api/auth/users", headers=auth)
        check("GET /api/auth/users lista sin hashes",
              r.status_code == 200
              and any(u.get("username") == viewer_user for u in r.json().get("entries", []))
              and all("password_hash" not in u for u in r.json().get("entries", [])), "")

        r = await http.post("/api/auth/login", json={"username": viewer_user, "password": viewer_pass})
        viewer_token = r.json().get("access_token") if r.status_code == 200 else None
        check("login del viewer", r.status_code == 200, f"status={r.status_code}")

        r = await http.post("/api/chat", json={"message": "hola", "client_type": "dashboard"},
                            headers={"Authorization": f"Bearer {viewer_token}"})
        check("viewer -> 403 en /api/chat", r.status_code == 403, f"status={r.status_code}")

        r = await http.get("/api/auth/users", headers={"Authorization": f"Bearer {viewer_token}"})
        check("viewer -> 403 en gestión de usuarios", r.status_code == 403, f"status={r.status_code}")

        r = await http.get("/api/hierarchy", headers={"Authorization": f"Bearer {viewer_token}"})
        check("viewer puede leer jerarquía", r.status_code == 200, f"status={r.status_code}")

    # -- Step 3: WS auth + chat with spoofed contributor -------------------------
    print("\n[3] WS autenticado + chat (identidad del token)")
    ws_url = API_BASE.replace("http", "ws") + "/ws/events"

    # unauthenticated hello must be rejected
    try:
        async with websockets.connect(ws_url) as ws_bad:
            await ws_bad.send(json.dumps({"type": "hello", "client_type": "dashboard", "name": "x"}))
            msg = json.loads(await asyncio.wait_for(ws_bad.recv(), timeout=10))
            check("WS hello sin token -> error en español",
                  msg.get("type") == "error" and "token" in msg.get("message", "").lower(),
                  str(msg)[:100])
    except Exception as exc:  # noqa: BLE001
        check("WS hello sin token -> error en español", False, str(exc)[:100])

    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({
            "type": "hello", "token": token, "client_type": "dashboard", "name": "e2e-bot",
        }))
        presence_events = await read_events_until(ws, {"presence"})
        presence_msg = presence_events.get("presence")
        clients = presence_msg.get("clients", []) if presence_msg else []
        check(
            "WS hello con token -> presence con usuario autenticado",
            any(c.get("username") == ADMIN_USER for c in clients),
            str(clients)[:140],
        )

        async def post_chat() -> httpx.Response:
            async with httpx.AsyncClient(base_url=API_BASE, timeout=60.0) as c:
                return await c.post("/api/chat", headers=auth, json={
                    "message": CHAT_MESSAGE,
                    "contributor": SPOOFED_CONTRIBUTOR,  # must be ignored
                    "client_type": "field_app",
                })

        chat_task = asyncio.create_task(post_chat())
        # mutation is broadcast before tx; capture both in one pass
        live = await read_events_until(ws, {"tx", "mutation"}, timeout=30.0)
        tx_msg = live.get("tx")
        tx_entry = tx_msg.get("entry", {}) if tx_msg else {}
        check(
            "WS tx broadcast: actor = usuario del token (no el spoof)",
            tx_entry.get("actor") == ADMIN_USER and tx_entry.get("actor") != SPOOFED_CONTRIBUTOR,
            f"actor={tx_entry.get('actor')}",
        )
        check("WS mutation broadcast", "mutation" in live, str(live.get("mutation"))[:120])
        resp = await chat_task

    check("POST /api/chat status", resp.status_code == 200, f"status={resp.status_code}")
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

    # -- Step 4: graph reads --------------------------------------------------
    print("\n[4] Graph reads")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as http:
        r = await http.get("/api/hierarchy", headers=auth)
        hierarchy = r.json()
        fac_names = [
            f["name"]
            for region in hierarchy.get("regions", [])
            for country in region.get("countries", [])
            for f in country.get("facilities", [])
        ]
        check("hierarchy includes Hospital Aurora", "Hospital Aurora" in fac_names,
              f"facilities={len(fac_names)}")

        r = await http.get("/api/network", headers=auth)
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
            r = await http.get(f"/api/facility/{aurora_nodes[0]['id']}", headers=auth)
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

    # -- Step 5: direct DB verification ----------------------------------------
    print("\n[5] Direct Neo4j / Postgres verification")
    from neo4j import GraphDatabase

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as s:
            # Run-scoped: only observations created during this run count,
            # so the checks pass on a dirty graph from earlier runs/seed.
            row = s.run(
                "MATCH (o:Observation)-[:OBSERVED]->(e:Equipment)<-[:HAS]-"
                "(f:Facility {name: 'Hospital Aurora'}) "
                "WHERE e.manufacturer = 'Siemens' AND e.modality = 'CT' "
                "AND o.created_at >= datetime({epochSeconds: toInteger($started)}) "
                "RETURN count(o) AS n",
                {"started": STARTED_AT},
            ).single()
            made_by = s.run(
                "MATCH (o:Observation)-[:OBSERVED]->(:Equipment)<-[:HAS]-"
                "(f:Facility {name:'Hospital Aurora'}) "
                "MATCH (o)-[:MADE_BY]->(c:Contributor {name: $actor}) "
                "WHERE o.created_at >= datetime({epochSeconds: toInteger($started)}) "
                "RETURN count(o) AS n",
                {"actor": ADMIN_USER, "started": STARTED_AT},
            ).single()
        driver.close()
        check("Neo4j: Aurora CT Siemens observado en esta corrida",
              bool(row and row["n"] >= 1), f"count={row['n'] if row else None}")
        check("Neo4j: observations MADE_BY el actor del token (no spoof)",
              bool(made_by and made_by["n"] >= 1), f"count={made_by['n'] if made_by else None}")
    except Exception as exc:  # noqa: BLE001
        check("Neo4j: Aurora CT Siemens observado en esta corrida", False, str(exc)[:120])

    try:
        import asyncpg

        async def pg_checks() -> tuple[int, int, int, int]:
            conn = await asyncpg.connect(POSTGRES_DSN)
            # Run-scoped: only rows created after STARTED_AT.
            tx = await conn.fetchval(
                "SELECT count(*) FROM transaction_log "
                "WHERE actor = $1 AND created_at >= to_timestamp($2)",
                ADMIN_USER, STARTED_AT,
            )
            spoof = await conn.fetchval(
                "SELECT count(*) FROM transaction_log "
                "WHERE actor = $1 AND created_at >= to_timestamp($2)",
                SPOOFED_CONTRIBUTOR, STARTED_AT,
            )
            perf = await conn.fetchval(
                "SELECT count(*) FROM perf_log WHERE created_at >= to_timestamp($1)",
                STARTED_AT,
            )
            users = await conn.fetchval("SELECT count(*) FROM users")
            await conn.close()
            return tx, spoof, perf, users

        tx_count, spoof_count, perf_count, user_count = await pg_checks()
        check("Postgres: transaction_log actor = token user (esta corrida)",
              tx_count >= 1, f"rows={tx_count}")
        check("Postgres: ningún tx con actor spoof", spoof_count == 0, f"rows={spoof_count}")
        check("Postgres: perf_log has entries (fallback logs metrics)",
              perf_count >= 1, f"rows={perf_count}")
        check("Postgres: users table poblada", user_count >= 2, f"users={user_count}")
    except Exception as exc:  # noqa: BLE001
        check("Postgres: transaction_log actor = token user (esta corrida)",
              False, str(exc)[:120])

    # -- Step 6: API metrics/transactions ---------------------------------------
    print("\n[6] Metrics + transactions endpoints")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as http:
        r = await http.get("/api/metrics", headers=auth)
        entries = r.json().get("entries", [])
        check(
            "/api/metrics shows a perf entry",
            r.status_code == 200 and bool(entries)
            and {"model", "ttft_ms", "total_ms", "throughput_tps"} <= set(entries[0]),
            f"entries={len(entries)}",
        )
        r = await http.get("/api/transactions", params={"limit": 10}, headers=auth)
        entries = r.json().get("entries", [])
        check(
            "/api/transactions has admin entry",
            r.status_code == 200 and any(e.get("actor") == ADMIN_USER for e in entries),
            f"entries={len(entries)}",
        )
        r = await http.get("/api/transactions/export.csv", headers=auth)
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
