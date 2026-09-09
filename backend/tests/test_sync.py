"""Phase 3 sync tests: ingest endpoint, loopback, enqueue gating, outbox push."""

import asyncio
import json

import httpx
from fastapi import FastAPI

from app.models import EquipmentItem, ExtractionResult, IngestResult
from app.sync import pusher, router, service, store
from app.sync.schemas import SyncPayload

TOKEN = "test-shared-token"


def run(coro):
    return asyncio.run(coro)


def make_payload(node_id: str = "node-A") -> dict:
    ext = ExtractionResult(
        facility="Hospital Aurora",
        country="Panamá",
        items=[EquipmentItem(modality="MR", manufacturer="GE", quantity=1)],
        extractor="rule",
        raw="vi una RM GE en el Hospital Aurora",
    )
    return SyncPayload(
        node_id=node_id,
        contributor="ingeniero-1",
        client_type="web",
        extraction=ext,
    ).model_dump()


def make_client() -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(router.router)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def test_endpoint_disabled_without_token(monkeypatch):
    monkeypatch.setattr(router.settings, "sync_token", "")
    client = make_client()
    resp = run(client.post("/api/sync/ingest", json=make_payload()))
    run(client.aclose())
    assert resp.status_code == 404


def test_endpoint_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(router.settings, "sync_token", TOKEN)
    client = make_client()
    resp = run(
        client.post(
            "/api/sync/ingest",
            json=make_payload(),
            headers={"Authorization": "Bearer wrong"},
        )
    )
    run(client.aclose())
    assert resp.status_code == 401


def test_endpoint_ingests(monkeypatch):
    monkeypatch.setattr(router.settings, "sync_token", TOKEN)

    async def fake_node_id() -> str:
        return "node-B"

    monkeypatch.setattr(store, "get_node_id", fake_node_id)

    received = {}

    async def fake_ingest(ext, contributor, client_type):
        received["extraction"] = ext
        received["contributor"] = contributor
        received["client_type"] = client_type
        return IngestResult(facility_id="fac-x", transaction_ids=[1, 2])

    monkeypatch.setattr(router.engine, "ingest_extraction", fake_ingest)

    client = make_client()
    resp = run(
        client.post(
            "/api/sync/ingest",
            json=make_payload(node_id="node-A"),
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    )
    run(client.aclose())
    assert resp.status_code == 200
    body = resp.json()
    assert body["ignored"] is False
    assert body["facility_id"] == "fac-x"
    assert body["transactions"] == 2
    assert isinstance(received["extraction"], ExtractionResult)
    assert received["extraction"].facility == "Hospital Aurora"
    assert received["contributor"] == "ingeniero-1"
    assert received["client_type"] == "web"


def test_endpoint_ignores_loopback(monkeypatch):
    monkeypatch.setattr(router.settings, "sync_token", TOKEN)

    async def fake_node_id() -> str:
        return "node-A"

    monkeypatch.setattr(store, "get_node_id", fake_node_id)

    called = False

    async def fake_ingest(ext, contributor, client_type):
        nonlocal called
        called = True
        return IngestResult(facility_id="fac-x", transaction_ids=[1])

    monkeypatch.setattr(router.engine, "ingest_extraction", fake_ingest)

    client = make_client()
    resp = run(
        client.post(
            "/api/sync/ingest",
            json=make_payload(node_id="node-A"),
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    )
    run(client.aclose())
    assert resp.status_code == 200
    assert resp.json() == {"ignored": True, "facility_id": None, "transactions": 0}
    assert called is False


def test_enqueue_noop_without_peers(monkeypatch):
    monkeypatch.setattr(service.settings, "sync_peers", "")
    called = False

    async def spy_enqueue(payload):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(store, "enqueue", spy_enqueue)

    ext = ExtractionResult(facility="Hospital Aurora")
    run(service.enqueue_extraction(ext, "ingeniero-1", "web"))
    assert called is False


def test_push_once_marks_sent(monkeypatch):
    row = {"id": 7, "payload": make_payload(node_id="node-A")}

    async def fake_fetch_pending(limit: int = 20):
        return [row]

    sent = []
    attempts = []

    async def spy_mark_sent(row_id: int):
        sent.append(row_id)

    async def spy_mark_attempt(row_id: int):
        attempts.append(row_id)

    monkeypatch.setattr(store, "fetch_pending", fake_fetch_pending)
    monkeypatch.setattr(store, "mark_sent", spy_mark_sent)
    monkeypatch.setattr(store, "mark_attempt", spy_mark_attempt)

    def handler(request):
        assert request.url.path == "/api/sync/ingest"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        body = json.loads(request.content)
        assert body["node_id"] == "node-A"
        return httpx.Response(200, json={"ignored": False})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    run(pusher.push_once(http, ["http://peer1.test", "http://peer2.test/"], TOKEN))
    run(http.aclose())

    assert sent == [7]
    assert attempts == []
