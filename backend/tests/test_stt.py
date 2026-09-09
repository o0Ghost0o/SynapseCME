"""STT proxy tests: success, upstream 500, unreachable — all with MockTransport.
No live STT service required; proxy writes no tx_log/perf_log."""

from __future__ import annotations

import asyncio

import httpx
from fastapi.testclient import TestClient

from app.agent import stt as stt_client
from app.auth.deps import get_current_user
from app.main import app


def run(coro):
    return asyncio.run(coro)


def make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://stt.test", transport=httpx.MockTransport(handler), timeout=5.0
    )


def fake_user(role="capturer"):
    return {"id": 1, "username": "marina.solis", "full_name": "Marina Solís",
            "role": role, "disabled": False}


class TestTranscribe:
    def test_success_returns_text(self):
        def handler(request):
            assert request.url.path == "/v1/audio/transcriptions"
            return httpx.Response(200, json={"text": "Visité el Hospital Aurora"})

        async def call():
            async with make_client(handler) as c:
                return await stt_client.transcribe(
                    c, b"RIFF-fake-audio", "nota.wav", "audio/wav", "Systran/faster-whisper-small"
                )

        assert run(call()) == "Visité el Hospital Aurora"

    def test_success_strips_whitespace(self):
        handler = lambda req: httpx.Response(200, json={"text": "  hola  "})
        async def call():
            async with make_client(handler) as c:
                return await stt_client.transcribe(c, b"x", "a.ogg", "audio/ogg", "m")
        assert run(call()) == "hola"

    def test_upstream_500_raises_unavailable(self):
        handler = lambda req: httpx.Response(500, text="boom")
        async def call():
            async with make_client(handler) as c:
                await stt_client.transcribe(c, b"x", "a.wav", "audio/wav", "m")
        try:
            run(call())
            raise AssertionError("should have raised")
        except stt_client.SttUnavailable as exc:
            assert "500" in str(exc)

    def test_unreachable_raises_unavailable(self):
        # real socket connect to a closed port — transport error path
        async def call():
            async with httpx.AsyncClient(base_url="http://127.0.0.1:1", timeout=2.0) as c:
                await stt_client.transcribe(c, b"x", "a.wav", "audio/wav", "m")
        try:
            run(call())
            raise AssertionError("should have raised")
        except stt_client.SttUnavailable as exc:
            assert "no responde" in str(exc)

    def test_empty_text_raises_unavailable(self):
        handler = lambda req: httpx.Response(200, json={"text": ""})
        async def call():
            async with make_client(handler) as c:
                await stt_client.transcribe(c, b"x", "a.wav", "audio/wav", "m")
        try:
            run(call())
            raise AssertionError("should have raised")
        except stt_client.SttUnavailable:
            pass


class TestSttEndpoint:
    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_viewer_forbidden(self):
        app.dependency_overrides[get_current_user] = lambda: fake_user("viewer")
        client = TestClient(app)
        r = client.post("/api/stt", files={"file": ("a.wav", b"x", "audio/wav")})
        assert r.status_code == 403

    def test_capturer_success_via_endpoint(self):
        app.dependency_overrides[get_current_user] = lambda: fake_user("capturer")
        import app.api.stt as stt_router

        def handler(request):
            return httpx.Response(200, json={"text": "dos tomógrafos Siemens"})

        original = stt_router.stt_client.make_client
        stt_router.stt_client.make_client = lambda base: make_client(handler)
        try:
            client = TestClient(app)
            r = client.post("/api/stt", files={"file": ("nota.wav", b"audio", "audio/wav")})
        finally:
            stt_router.stt_client.make_client = original
        assert r.status_code == 200
        assert r.json() == {"text": "dos tomógrafos Siemens"}

    def test_capturer_503_spanish_when_stt_down(self):
        app.dependency_overrides[get_current_user] = lambda: fake_user("capturer")
        import app.api.stt as stt_router

        def handler(request):
            return httpx.Response(503, text="model loading")

        original = stt_router.stt_client.make_client
        stt_router.stt_client.make_client = lambda base: make_client(handler)
        try:
            client = TestClient(app)
            r = client.post("/api/stt", files={"file": ("nota.wav", b"audio", "audio/wav")})
        finally:
            stt_router.stt_client.make_client = original
        assert r.status_code == 503
        assert "Dictado no disponible" in r.json()["detail"]

    def test_empty_file_400(self):
        app.dependency_overrides[get_current_user] = lambda: fake_user("capturer")
        client = TestClient(app)
        r = client.post("/api/stt", files={"file": ("a.wav", b"", "audio/wav")})
        assert r.status_code == 400
