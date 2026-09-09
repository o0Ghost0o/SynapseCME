"""Auth tests: passwords, JWT expiry, refresh rotation, RBAC enforcement and
capturer identity from the token. No live DB — db helpers are faked."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth import service, tokens
from app.auth.deps import get_current_user
from app.auth.passwords import hash_password, verify_password
from app.main import app

# ---------------------------------------------------------------------------
# Fakes: in-memory users + refresh tokens, patched over app.db helpers
# ---------------------------------------------------------------------------

HASH = hash_password("segura-123")


def make_user(username="marina.solis", role="capturer", disabled=False):
    return {
        "id": 1,
        "username": username,
        "full_name": "Marina Solís",
        "role": role,
        "password_hash": HASH,
        "disabled": disabled,
        "created_at": "2026-01-01T00:00:00Z",
    }


class FakeDB:
    def __init__(self, monkeypatch):
        self.users = {"marina.solis": make_user()}
        self.refresh = {}  # token_hash -> row dict
        self._next_id = 100
        monkeypatch.setattr(service.db, "get_user_by_username", self.get_user_by_username)
        monkeypatch.setattr(service.db, "get_user_by_id", self.get_user_by_id)
        monkeypatch.setattr(service.db, "insert_refresh_token", self.insert_refresh_token)
        monkeypatch.setattr(service.db, "get_refresh_token", self.get_refresh_token)
        monkeypatch.setattr(service.db, "revoke_refresh_token", self.revoke_refresh_token)

    async def get_user_by_username(self, username):
        return self.users.get(username)

    async def get_user_by_id(self, user_id):
        for u in self.users.values():
            if u["id"] == user_id:
                return u
        return None

    async def insert_refresh_token(self, user_id, token_hash, expires_at):
        self._next_id += 1
        self.refresh[token_hash] = {
            "id": self._next_id,
            "user_id": user_id,
            "expires_at": expires_at,
            "revoked": False,
        }
        return self._next_id

    async def get_refresh_token(self, token_hash):
        row = self.refresh.get(token_hash)
        if row is None:
            return None
        user = await self.get_user_by_id(row["user_id"])
        return {
            **row,
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "disabled": user["disabled"],
        }

    async def revoke_refresh_token(self, token_id):
        for row in self.refresh.values():
            if row["id"] == token_id:
                row["revoked"] = True


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

class TestPasswords:
    def test_hash_and_verify(self):
        h = hash_password("clave-secreta")
        assert h != "clave-secreta" and "argon2" in h
        assert verify_password("clave-secreta", h)
        assert not verify_password("otra", h)

    def test_verify_garbage_hash(self):
        assert not verify_password("x", "not-a-hash")


# ---------------------------------------------------------------------------
# JWT lifecycle
# ---------------------------------------------------------------------------

class TestTokens:
    def test_roundtrip(self):
        token = tokens.create_access_token("marina.solis", now=1000)
        payload = tokens.decode_access_token(token, now=1000)
        assert payload["sub"] == "marina.solis"
        assert payload["exp"] == 1000 + 900

    def test_expiry(self):
        token = tokens.create_access_token("marina.solis", now=1000)
        with pytest.raises(tokens.jwt.ExpiredSignatureError):
            tokens.decode_access_token(token, now=1000 + 901)
        # still valid just before expiry
        tokens.decode_access_token(token, now=1000 + 899)

    def test_tampered(self):
        import jwt as pyjwt
        token = tokens.create_access_token("marina.solis", now=1000)
        with pytest.raises(pyjwt.InvalidTokenError):
            tokens.decode_access_token(token + "x", now=1000)


# ---------------------------------------------------------------------------
# Login / refresh rotation / logout (service level)
# ---------------------------------------------------------------------------

class TestAuthService:
    def test_login_ok_and_bad(self, monkeypatch):
        fake = FakeDB(monkeypatch)
        pair = run(service.login("marina.solis", "segura-123"))
        assert pair["token_type"] == "bearer"
        assert pair["expires_in"] == 900
        assert pair["user"]["username"] == "marina.solis"
        assert pair["user"]["role"] == "capturer"
        assert pair["access_token"] and pair["refresh_token"]
        assert len(fake.refresh) == 1  # hash persisted

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            run(service.login("marina.solis", "mala"))
        assert exc.value.status_code == 401
        with pytest.raises(HTTPException) as exc:
            run(service.login("nadie", "segura-123"))
        assert exc.value.status_code == 401

    def test_login_disabled(self, monkeypatch):
        fake = FakeDB(monkeypatch)
        fake.users["marina.solis"]["disabled"] = True
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            run(service.login("marina.solis", "segura-123"))
        assert exc.value.status_code == 401
        assert "deshabilitado" in exc.value.detail

    def test_refresh_rotation_and_old_token_rejected(self, monkeypatch):
        FakeDB(monkeypatch)
        pair = run(service.login("marina.solis", "segura-123"))
        old_refresh = pair["refresh_token"]

        new_pair = run(service.rotate_refresh_token(old_refresh))
        assert new_pair["refresh_token"] != old_refresh
        # same-second access tokens may coincide (second-precision iat);
        # the important part: it decodes to the same user
        assert tokens.decode_access_token(new_pair["access_token"])["sub"] == "marina.solis"

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:  # reuse of revoked token
            run(service.rotate_refresh_token(old_refresh))
        assert exc.value.status_code == 401

    def test_refresh_unknown_token(self, monkeypatch):
        FakeDB(monkeypatch)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            run(service.rotate_refresh_token("no-existe"))
        assert exc.value.status_code == 401

    def test_refresh_expired(self, monkeypatch):
        fake = FakeDB(monkeypatch)
        pair = run(service.login("marina.solis", "segura-123"))
        row = fake.refresh[service.hash_refresh_token(pair["refresh_token"])]
        row["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            run(service.rotate_refresh_token(pair["refresh_token"]))
        assert exc.value.status_code == 401

    def test_logout_revokes(self, monkeypatch):
        fake = FakeDB(monkeypatch)
        pair = run(service.login("marina.solis", "segura-123"))
        run(service.logout(pair["refresh_token"]))
        row = fake.refresh[service.hash_refresh_token(pair["refresh_token"])]
        assert row["revoked"] is True
        # idempotent: unknown token doesn't raise
        run(service.logout("desconocido"))


# ---------------------------------------------------------------------------
# RBAC enforcement + identity via HTTP (dependency override for get_current_user)
# ---------------------------------------------------------------------------

def client_as(role: str, username="marina.solis") -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: make_user(username, role)
    return TestClient(app)


class TestRBAC:
    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_viewer_forbidden_on_chat(self):
        client = client_as("viewer")
        r = client.post("/api/chat", json={"message": "hola", "client_type": "dashboard"})
        assert r.status_code == 403
        assert "Permisos insuficientes" in r.json()["detail"]

    def test_capturer_can_chat(self, monkeypatch):
        FakeDB(monkeypatch)
        client = client_as("capturer")
        r = client.post("/api/chat", json={"message": "hola", "client_type": "field_app"})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]

    def test_non_admin_forbidden_on_user_mgmt(self):
        client = client_as("capturer")
        r = client.get("/api/auth/users")
        assert r.status_code == 403
        r = client.post("/api/auth/users", json={
            "username": "x.y", "password": "12345678", "full_name": "X", "role": "viewer",
        })
        assert r.status_code == 403

    def test_viewer_can_read(self):
        client = client_as("viewer")
        assert client.get("/api/hierarchy").status_code == 200
        assert client.get("/api/network").status_code == 200
        assert client.get("/api/metrics").status_code == 200
        assert client.get("/api/transactions").status_code == 200

    def test_missing_token_401(self):
        client = TestClient(app)  # no override: real dependency, no header
        r = client.get("/api/hierarchy")
        assert r.status_code == 401
        assert "Token de acceso requerido" in r.json()["detail"]

    def test_expired_token_401(self, monkeypatch):
        client = TestClient(app)
        # valid signature but expired -> must be 401
        token = tokens.create_access_token("marina.solis", now=1000)
        r = client.get("/api/hierarchy", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
        assert "expirado" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Capturer identity from the token: chat must ignore a spoofed contributor
# ---------------------------------------------------------------------------

class TestCapturerIdentity:
    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_token_pair_schema_validates(self):
        from app.models import TokenPair

        pair = TokenPair(
            access_token="a", refresh_token="r", expires_in=900,
            user={"username": "u", "full_name": "U", "role": "viewer"},
        )
        assert pair.token_type == "bearer"

    def test_chat_ignores_spoofed_contributor(self, monkeypatch):
        FakeDB(monkeypatch)
        captured = {}

        async def fake_ingest(ext, contributor, client_type, full_name=None):
            captured["contributor"] = contributor
            captured["full_name"] = full_name
            from app.models import IngestResult
            return IngestResult()

        monkeypatch.setattr(
            "app.agent.service.engine.ingest_extraction", fake_ingest
        )
        client = client_as("capturer", username="marina.solis")
        r = client.post("/api/chat", json={
            "message": "Visité el Hospital Aurora en Panamá, vi 2 tomógrafos Siemens",
            "contributor": "usurero-malicioso",  # must be ignored
            "client_type": "field_app",
        })
        assert r.status_code == 200
        assert captured["contributor"] == "marina.solis"
        assert captured["contributor"] != "usurero-malicioso"
        assert captured["full_name"] == "Marina Solís"

    def test_ws_rejects_missing_token(self):
        from app.api.ws import WS_AUTH_ERROR_CODE
        client = TestClient(app)
        with client.websocket_connect("/ws/events") as ws:
            ws.send_json({"type": "hello", "client_type": "dashboard", "name": "x"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "token" in msg["message"].lower()
