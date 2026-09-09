import asyncio
import json

import httpx

from app.agent.qvac import QvacClient
from app.agent.service import handle_chat, parse_llm_json
from app.models import ChatRequest


def _ndjson(*objects):
    return "\n".join(json.dumps(o) for o in objects)


def make_client(handler) -> QvacClient:
    transport = httpx.MockTransport(handler)
    return QvacClient("http://qvac.test", model="medpsy:q4_k_m", embed_model="bge", transport=transport)


def run(coro):
    return asyncio.run(coro)


class TestQvacClient:
    def test_list_models(self):
        def handler(request):
            assert request.url.path == "/api/tags"
            return httpx.Response(200, json={"models": [{"name": "medpsy:q4_k_m"}, {"name": "bge-small"}]})

        client = make_client(handler)
        assert run(client.list_models()) == ["medpsy:q4_k_m", "bge-small"]
        run(client.aclose())

    def test_list_models_down(self):
        client = make_client(lambda req: httpx.Response(503))
        assert run(client.list_models()) == []
        assert run(client.is_up()) is False
        run(client.aclose())

    def test_stream_chat(self):
        chunks = [
            {"message": {"role": "assistant", "content": "ho"}, "done": False},
            {"message": {"role": "assistant", "content": "la"}, "done": False},
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "prompt_eval_count": 10,
                "eval_count": 2,
                "eval_duration": 1_000_000_000,
            },
        ]

        def handler(request):
            assert request.url.path == "/api/chat"
            body = json.loads(request.content)
            assert body["stream"] is True
            return httpx.Response(200, content=_ndjson(*chunks))

        async def collect():
            client = make_client(handler)
            events = [e async for e in client.stream_chat([{"role": "user", "content": "hi"}])]
            await client.aclose()
            return events

        events = run(collect())
        tokens = [e["token"] for e in events if "token" in e]
        done = next(e for e in events if e.get("done"))
        assert tokens == ["ho", "la"]
        assert done["usage"]["eval_count"] == 2


class TestParseLlmJson:
    def test_fenced(self):
        text = 'Explicación\n```json\n{"facility": "Hospital Aurora", "items": []}\n```\nMás texto'
        data = parse_llm_json(text)
        assert data["facility"] == "Hospital Aurora"

    def test_bare(self):
        data = parse_llm_json('prefix {"a": 1} suffix')
        assert data == {"a": 1}

    def test_garbage(self):
        assert parse_llm_json("no json here") is None


def _parse_sse(stream: str):
    events = []
    for block in stream.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


class TestChatFallbackPipeline:
    def test_rule_fallback_when_no_client(self):
        # No QVAC client initialised -> deterministic rule-based path.
        request = ChatRequest(
            message="Visité el Hospital Aurora en Panamá, vi 3 resonancias magnéticas",
            contributor="ana",
            client_type="field_app",
        )

        async def collect():
            return "".join([chunk async for chunk in handle_chat(request)])

        events = _parse_sse(run(collect()))

        types = [e["type"] for e in events]
        assert types[0] == "token"  # fallback acknowledgment
        assert "extraction" in types
        assert types[-1] == "done"
        assert "transaction_id" in events[-1]

        extraction = next(e for e in events if e["type"] == "extraction")
        assert extraction["data"]["facility"] == "Hospital Aurora"
        assert extraction["data"]["extractor"] == "rule"
        assert any(
            i["modality"] == "MR" and i["quantity"] == 3
            for i in extraction["data"]["items"]
        )

        followups = [e for e in events if e["type"] == "followup"]
        assert followups and "fabricante" in followups[0]["question"].lower()
