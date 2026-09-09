"""Manual smoke test: boots the app without Neo4j/Postgres/QVAC and hits endpoints."""
import json

from fastapi.testclient import TestClient

from app.main import app

with TestClient(app) as c:
    r = c.get("/api/health")
    print("health:", r.status_code, r.json())

    with c.stream("POST", "/api/chat", json={
        "message": "Visité el Hospital Aurora en Panamá, vi 3 resonancias magnéticas y 2 tomógrafos, una RM tiene como 8 años",
        "contributor": "ana",
        "client_type": "field_app",
    }) as r:
        print("chat:", r.status_code, r.headers.get("content-type"))
        for line in r.iter_lines():
            if line.startswith("data: "):
                d = json.loads(line[6:])
                print("  event:", d["type"], str(d)[:140])

    print("hierarchy:", c.get("/api/hierarchy").json())
    print("network:", c.get("/api/network").json())
    print("metrics:", c.get("/api/metrics").json())
    print("transactions:", c.get("/api/transactions").json())

    r = c.get("/api/transactions/export.csv")
    print("csv:", r.status_code, r.headers.get("content-type"), repr(r.text[:80]))

    with c.websocket_connect("/ws/events") as ws:
        ws.send_json({"type": "hello", "client_type": "dashboard", "name": "ops-1"})
        msg = ws.receive_json()
        print("ws hello ->", msg["type"], [cl["name"] for cl in msg["clients"]])
        ws.send_json({"type": "ping"})
        print("ws ping ->", ws.receive_json())
