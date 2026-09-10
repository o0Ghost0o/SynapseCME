"""Conversaciones (Fase 4): CRUD + aislamiento entre usuarios, RBAC y
persistencia del POST /api/chat sobre conversaciones. Sin DB real: los
helpers de app.db se falsifican en memoria."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.agent import service
from app.agent.qvac import QvacClient
from app.auth.deps import get_current_user
from app.main import app


def make_user(username="marina.solis", role="capturer", user_id=1):
    return {
        "id": user_id,
        "username": username,
        "full_name": "Marina Solís",
        "role": role,
        "disabled": False,
        "created_at": "2026-01-01T00:00:00Z",
    }


def client_as(user: dict) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _parse_sse(stream: str):
    events = []
    for block in stream.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


class FakeConvDB:
    """In-memory fake of the conversations db helpers."""

    def __init__(self, monkeypatch):
        self.convs: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self._n = 0
        monkeypatch.setattr(db, "pool", lambda: object())
        monkeypatch.setattr(db, "create_conversation", self.create_conversation)
        monkeypatch.setattr(db, "get_conversation", self.get_conversation)
        monkeypatch.setattr(db, "list_conversations", self.list_conversations)
        monkeypatch.setattr(db, "delete_conversation", self.delete_conversation)
        monkeypatch.setattr(db, "add_chat_message", self.add_chat_message)
        monkeypatch.setattr(db, "list_chat_messages", self.list_chat_messages)
        monkeypatch.setattr(db, "set_conversation_title", self.set_conversation_title)

    def _next_id(self) -> str:
        self._n += 1
        return f"11111111-2222-3333-4444-{self._n:012d}"

    def seed(self, user_id: int, title: str = "", n_messages: int = 0) -> str:
        cid = self._next_id()
        n = self._n
        self.convs[cid] = {
            "id": cid,
            "user_id": user_id,
            "title": title,
            "created_at": f"2026-09-0{1 + (n % 8)}T10:00:00Z",
            "last_message_at": f"2026-09-0{1 + (n % 8)}T10:05:00Z",
        }
        self.messages[cid] = []
        for i in range(n_messages):
            self.messages[cid].append(
                {
                    "id": i + 1,
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"mensaje {i + 1}",
                    "extraction": {"facility": "Hospital Aurora"} if i == 0 else None,
                    "created_at": "2026-09-01T10:00:00Z",
                }
            )
        return cid

    async def create_conversation(self, user_id):
        cid = self._next_id()
        self.convs[cid] = {
            "id": cid,
            "user_id": user_id,
            "title": "",
            "created_at": "2026-09-10T10:00:00Z",
            "last_message_at": "2026-09-10T10:00:00Z",
        }
        self.messages[cid] = []
        return dict(self.convs[cid])

    async def get_conversation(self, conversation_id):
        conv = self.convs.get(conversation_id)
        return dict(conv) if conv else None

    async def list_conversations(self, user_id):
        mine = [c for c in self.convs.values() if c["user_id"] == user_id]
        mine.sort(key=lambda c: c["last_message_at"], reverse=True)
        return [
            {"id": c["id"], "title": c["title"], "last_message_at": c["last_message_at"]}
            for c in mine
        ]

    async def delete_conversation(self, conversation_id):
        return self.convs.pop(conversation_id, None) is not None

    async def add_chat_message(self, conversation_id, role, content, extraction=None):
        msg = {
            "id": len(self.messages[conversation_id]) + 1,
            "role": role,
            "content": content,
            "extraction": extraction,
            "created_at": "2026-09-10T10:01:00Z",
        }
        self.messages[conversation_id].append(msg)
        return dict(msg)

    async def list_chat_messages(self, conversation_id):
        return list(self.messages.get(conversation_id, []))

    async def set_conversation_title(self, conversation_id, title):
        conv = self.convs.get(conversation_id)
        if conv is None:
            return False
        conv["title"] = title
        return True


@pytest.fixture(autouse=True)
def _clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# CRUD + aislamiento
# ---------------------------------------------------------------------------

class TestConversationsCRUD:
    def test_list_empty(self, monkeypatch):
        FakeConvDB(monkeypatch)
        r = client_as(make_user()).get("/api/conversations")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_only_own_desc(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        mine_old = fake.seed(user_id=1, title="Vieja")
        fake.convs[mine_old]["last_message_at"] = "2026-09-01T10:00:00Z"
        mine_new = fake.seed(user_id=1, title="Reciente")
        fake.convs[mine_new]["last_message_at"] = "2026-09-09T10:00:00Z"
        fake.seed(user_id=2, title="De otro")

        r = client_as(make_user()).get("/api/conversations")
        assert r.status_code == 200
        items = r.json()
        assert [i["title"] for i in items] == ["Reciente", "Vieja"]
        assert all(i["id"] in (mine_old, mine_new) for i in items)

    def test_detail_returns_messages_with_extraction(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=1, title="Visita La Fe", n_messages=3)
        r = client_as(make_user()).get(f"/api/conversations/{cid}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == cid
        assert body["title"] == "Visita La Fe"
        assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
        assert body["messages"][0]["extraction"]["facility"] == "Hospital Aurora"
        assert body["messages"][1]["extraction"] is None

    def test_detail_404_other_user(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=2)
        r = client_as(make_user(user_id=1)).get(f"/api/conversations/{cid}")
        assert r.status_code == 404

    def test_detail_404_unknown(self, monkeypatch):
        FakeConvDB(monkeypatch)
        r = client_as(make_user()).get("/api/conversations/99999999-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_detail_admin_any(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=2, title="Ajena")
        r = client_as(make_user(username="root", role="admin", user_id=9)).get(
            f"/api/conversations/{cid}"
        )
        assert r.status_code == 200
        assert r.json()["title"] == "Ajena"

    def test_delete_own(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=1)
        r = client_as(make_user()).delete(f"/api/conversations/{cid}")
        assert r.status_code == 204
        assert cid not in fake.convs

    def test_delete_other_user_404(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=2)
        r = client_as(make_user(user_id=1)).delete(f"/api/conversations/{cid}")
        assert r.status_code == 404
        assert cid in fake.convs

    def test_delete_admin_any(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=2)
        r = client_as(make_user(username="root", role="admin", user_id=9)).delete(
            f"/api/conversations/{cid}"
        )
        assert r.status_code == 204
        assert cid not in fake.convs

    def test_viewer_forbidden(self, monkeypatch):
        FakeConvDB(monkeypatch)
        client = client_as(make_user(role="viewer"))
        assert client.get("/api/conversations").status_code == 403
        assert client.get("/api/conversations/x").status_code == 403

    def test_missing_token_401(self, monkeypatch):
        FakeConvDB(monkeypatch)
        r = TestClient(app).get("/api/conversations")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/chat + persistencia
# ---------------------------------------------------------------------------

OBSERVATION = "Visité el Hospital Aurora en Panamá, vi 2 tomógrafos Siemens"


class TestChatPersistence:
    def _post_chat(self, client: TestClient, payload: dict) -> httpx.Response:
        return client.post("/api/chat", json={"client_type": "field_app", **payload})

    def test_chat_creates_conversation_and_persists(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        monkeypatch.setattr(service, "_client", None)  # fallback determinista
        client = client_as(make_user())

        r = self._post_chat(client, {"message": OBSERVATION})
        assert r.status_code == 200

        events = _parse_sse(r.text)
        done = events[-1]
        assert done["type"] == "done"
        cid = done["conversation_id"]

        conv = fake.convs[cid]
        assert conv["user_id"] == 1
        msgs = fake.messages[cid]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[0]["content"] == OBSERVATION
        # fallback: el texto emitido es el ACK; la extracción viaja en jsonb
        assert msgs[1]["content"]
        assert msgs[1]["extraction"]["facility"] == "Hospital Aurora"

    def test_chat_anchors_existing_conversation(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=1, n_messages=2)
        monkeypatch.setattr(service, "_client", None)
        client = client_as(make_user())

        r = self._post_chat(client, {"message": OBSERVATION, "conversation_id": cid})
        assert r.status_code == 200
        events = _parse_sse(r.text)
        assert events[-1]["conversation_id"] == cid
        # no se creó una conversación nueva
        assert len(fake.convs) == 1
        assert [m["role"] for m in fake.messages[cid]] == ["user", "assistant", "user", "assistant"]

    def test_chat_unknown_conversation_404(self, monkeypatch):
        FakeConvDB(monkeypatch)
        client = client_as(make_user())
        r = self._post_chat(
            client, {"message": "hola", "conversation_id": "99999999-0000-0000-0000-000000000000"}
        )
        assert r.status_code == 404

    def test_chat_other_user_conversation_404(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=2)
        client = client_as(make_user(user_id=1))
        r = self._post_chat(client, {"message": "hola", "conversation_id": cid})
        assert r.status_code == 404

    def test_chat_without_db_keeps_legacy_behavior(self, monkeypatch):
        # pool() None -> sin persistencia, done sin conversation_id
        monkeypatch.setattr(db, "pool", lambda: None)
        monkeypatch.setattr(service, "_client", None)
        client = client_as(make_user())
        r = self._post_chat(client, {"message": OBSERVATION})
        assert r.status_code == 200
        done = _parse_sse(r.text)[-1]
        assert done["type"] == "done"
        assert "conversation_id" not in done

    def test_title_fallback_scheduled_after_done(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        monkeypatch.setattr(service, "_client", None)
        captured = {}
        real_create_task = asyncio.create_task

        def spy_create_task(coro):
            captured["coro"] = coro
            # tarea mínima que satisface add/set done_callback sin correr el coro
            task = real_create_task(asyncio.sleep(0))
            return task

        monkeypatch.setattr(service.asyncio, "create_task", spy_create_task)
        client = client_as(make_user())
        r = self._post_chat(client, {"message": OBSERVATION})
        assert r.status_code == 200
        cid = _parse_sse(r.text)[-1]["conversation_id"]

        assert "coro" in captured
        asyncio.run(captured["coro"])  # QVAC caído -> fallback determinista
        title = fake.convs[cid]["title"]
        assert title == " ".join(OBSERVATION.split()[:6])

    def test_title_not_regenerated_when_already_set(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=1, title="Ya titulada")
        monkeypatch.setattr(service, "_client", None)
        captured = {}
        real_create_task = asyncio.create_task

        def spy_create_task(coro):
            captured["coro"] = coro
            return real_create_task(asyncio.sleep(0))

        monkeypatch.setattr(service.asyncio, "create_task", spy_create_task)
        client = client_as(make_user())
        r = self._post_chat(client, {"message": OBSERVATION, "conversation_id": cid})
        assert r.status_code == 200
        asyncio.run(captured["coro"])
        assert fake.convs[cid]["title"] == "Ya titulada"


# ---------------------------------------------------------------------------
# Generación de títulos (LLM + fallback)
# ---------------------------------------------------------------------------

class FakeTitleClient:
    """QvacClient stub: .chat() devuelve lo configurado."""

    def __init__(self, reply: str | None):
        self.reply = reply
        self.calls: list[dict] = []

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return self.reply


def run(coro):
    return asyncio.run(coro)


class TestTitleGeneration:
    def test_llm_title_applied(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=1)
        client = FakeTitleClient("Tomógrafos Siemens en Hospital")

        title = run(service.generate_conversation_title(client, cid, OBSERVATION, "ACK"))
        assert title == "Tomógrafos Siemens en Hospital"
        assert fake.convs[cid]["title"] == title
        call = client.calls[0]
        assert call["temperature"] == 0.0
        assert call["max_tokens"] == 256
        assert OBSERVATION in call["messages"][-1]["content"]

    def test_llm_failure_falls_back_to_first_words(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=1)
        title = run(service.generate_conversation_title(None, cid, OBSERVATION, "ACK"))
        assert title == " ".join(OBSERVATION.split()[:6])
        assert fake.convs[cid]["title"] == title

    def test_empty_llm_reply_falls_back(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=1)
        title = run(
            service.generate_conversation_title(FakeTitleClient("  "), cid, OBSERVATION)
        )
        assert title == " ".join(OBSERVATION.split()[:6])

    def test_skips_when_title_already_set(self, monkeypatch):
        fake = FakeConvDB(monkeypatch)
        cid = fake.seed(user_id=1, title="Original")
        client = FakeTitleClient("Otro título")
        title = run(service.generate_conversation_title(client, cid, OBSERVATION))
        assert title is None
        assert fake.convs[cid]["title"] == "Original"
        assert client.calls == []


# ---------------------------------------------------------------------------
# QvacClient.chat (no streaming)
# ---------------------------------------------------------------------------

class TestQvacChat:
    def test_chat_non_stream(self):
        def handler(request):
            assert request.url.path == "/v1/chat/completions"
            body = json.loads(request.content)
            assert body["stream"] is False
            assert body["max_tokens"] == 20
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Título corto"}}]},
            )

        client = QvacClient(
            "http://qvac.test", model="medpsy:q4_k_m", embed_model="bge",
            transport=httpx.MockTransport(handler),
        )
        assert run(client.chat([{"role": "user", "content": "x"}], max_tokens=20)) == "Título corto"
        run(client.aclose())

    def test_chat_down_returns_none(self):
        client = QvacClient(
            "http://qvac.test", model="m", embed_model="e",
            transport=httpx.MockTransport(lambda req: httpx.Response(503)),
        )
        assert run(client.chat([{"role": "user", "content": "x"}])) is None
        run(client.aclose())

    def test_chat_empty_choices_returns_none(self):
        client = QvacClient(
            "http://qvac.test", model="m", embed_model="e",
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": []})),
        )
        assert run(client.chat([{"role": "user", "content": "x"}])) is None
        run(client.aclose())
