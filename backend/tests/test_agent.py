import asyncio
import json

import httpx

from app.agent.qvac import QvacClient
from app.agent.service import handle_chat, handle_equipment_chat, parse_llm_json
from app.models import ChatRequest, IngestResult


def _sse_body(*chunks: dict) -> bytes:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return (body + "data: [DONE]\n\n").encode()


def make_client(handler) -> QvacClient:
    transport = httpx.MockTransport(handler)
    return QvacClient("http://qvac.test", model="medpsy:q4_k_m", embed_model="bge", transport=transport)


def run(coro):
    return asyncio.run(coro)


class TestQvacClient:
    def test_list_models(self):
        def handler(request):
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json={"data": [{"id": "medpsy:q4_k_m"}, {"id": "bge-m3"}]})

        client = make_client(handler)
        assert run(client.list_models()) == ["medpsy:q4_k_m", "bge-m3"]
        run(client.aclose())

    def test_list_models_down(self):
        client = make_client(lambda req: httpx.Response(503))
        assert run(client.list_models()) == []
        assert run(client.is_up()) is False
        run(client.aclose())

    def test_stream_chat(self):
        chunks = [
            {"choices": [{"delta": {"role": "assistant", "content": "ho"}}]},
            {"choices": [{"delta": {"content": "la"}}]},
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            },
        ]

        def handler(request):
            assert request.url.path == "/v1/chat/completions"
            body = json.loads(request.content)
            assert body["stream"] is True
            return httpx.Response(
                200,
                content=_sse_body(*chunks),
                headers={"content-type": "text/event-stream"},
            )

        async def collect():
            client = make_client(handler)
            events = [e async for e in client.stream_chat([{"role": "user", "content": "hi"}])]
            await client.aclose()
            return events

        events = run(collect())
        tokens = [e["token"] for e in events if "token" in e]
        done = next(e for e in events if e.get("done"))
        assert tokens == ["ho", "la"]
        assert done["text"] == "hola"
        assert done["usage"]["completion_tokens"] == 2


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


class TestParameterExtractionPipeline:
    """Parámetros: vía LLM (cliente mockeado) y vía fallback por reglas."""

    def _client(self, payload: dict):
        chunks = [
            {"choices": [{"delta": {"role": "assistant", "content": "{\"facility\":"}}]},
            {"choices": [{"delta": {"content": json.dumps(payload)[len("{\"facility\":"):]}}]},
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        ]

        def handler(request):
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(
                    200,
                    content=_sse_body(*chunks),
                    headers={"content-type": "text/event-stream"},
                )
            if request.url.path == "/v1/embeddings":
                return httpx.Response(200, json={"data": [{"embedding": [0.1] * 8}]})
            return httpx.Response(404)

        return make_client(handler)

    def test_llm_extraction_includes_parameters(self, monkeypatch):
        payload = {
            "facility": "Hospital Aurora",
            "city": "Ciudad de Panamá",
            "country": "Panamá",
            "items": [
                {
                    "modality": "MR",
                    "manufacturer": "Siemens",
                    "model": None,
                    "quantity": 1,
                    "age_years": 6,
                    "confidence": 0.9,
                    "parameters": [
                        {"name": "nivel de helio", "value": "45%", "unit": None, "status": "warning"},
                        {"name": "presión criógena", "value": None, "unit": None, "status": "ok"},
                        {"name": "ruido", "value": "alto", "unit": None, "status": "banana"},
                    ],
                }
            ],
            "followup": None,
        }
        client = self._client(payload)
        monkeypatch.setattr("app.agent.service._client", client)

        request = ChatRequest(
            message="la resonancia Siemens tiene el helio al 45%",
            client_type="field_app",
        )

        async def collect():
            return "".join([chunk async for chunk in handle_chat(request)])

        events = _parse_sse(run(collect()))
        extraction = next(e for e in events if e["type"] == "extraction")
        assert extraction["data"]["extractor"] == "llm"
        params = extraction["data"]["items"][0]["parameters"]
        by_name = {p["name"]: p for p in params}
        # "45%" se coerciona a valor numérico + unidad
        assert by_name["nivel de helio"]["value"] == 45
        assert by_name["nivel de helio"]["unit"] == "%"
        assert by_name["nivel de helio"]["status"] == "warning"
        assert by_name["presión criógena"]["status"] == "ok"
        # status fuera de catálogo -> null
        assert by_name["ruido"]["value"] == "alto"
        assert by_name["ruido"]["status"] is None

    def test_rule_fallback_extracts_parameters(self, monkeypatch):
        monkeypatch.setattr("app.agent.service._client", None)
        request = ChatRequest(
            message=(
                "El tomógrafo GE del Hospital Aurora en Panamá tiene el tubo con "
                "1.2 millones de cortes, el calentamiento del ánodo está alto"
            ),
            client_type="field_app",
        )

        async def collect():
            return "".join([chunk async for chunk in handle_chat(request)])

        events = _parse_sse(run(collect()))
        extraction = next(e for e in events if e["type"] == "extraction")
        assert extraction["data"]["extractor"] == "rule"
        params = extraction["data"]["items"][0]["parameters"]
        by_name = {p["name"]: p for p in params}
        assert by_name["cortes de tubo"]["value"] == 1200000
        assert by_name["cortes de tubo"]["status"] == "warning"
        assert by_name["calentamiento del ánodo"]["status"] == "warning"


class TestEquipmentChatPipeline:
    """Mini-chat de revisión: extracción anclada al equipo + ingesta dirigida."""

    CTX = {
        "id": "eq-1",
        "modality": "MR",
        "manufacturer": None,
        "model": None,
        "age_years": None,
        "state": "Desconocido",
        "facility_id": "fac-1",
        "facility_name": "Clínica Puerto Verde",
        "city": "Colón",
        "country": "Panamá",
    }

    def _client(self, payload: dict):
        body = json.dumps(payload, ensure_ascii=False)
        chunks = [
            {"choices": [{"delta": {"role": "assistant", "content": body[:20]}}]},
            {"choices": [{"delta": {"content": body[20:]}}]},
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        ]

        def handler(request):
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(
                    200,
                    content=_sse_body(*chunks),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(404)

        return make_client(handler)

    def _patch_ctx(self, monkeypatch):
        async def fake_ctx(eid):
            return self.CTX

        monkeypatch.setattr("app.agent.service.engine.get_equipment_context", fake_ctx)

    def test_llm_revision_updates_equipment(self, monkeypatch):
        payload = {
            "manufacturer": "Philips",
            "model": None,
            "age_years": 4,
            "parameters": [
                {"name": "corriente del tubo", "value": "10 mA", "unit": None, "status": "ok"},
            ],
            "note": "Anotado: fabricante Philips y corriente del tubo 10 mA.",
            "followup": "¿Cuál es el modelo exacto del equipo?",
        }
        monkeypatch.setattr("app.agent.service._client", self._client(payload))
        self._patch_ctx(monkeypatch)
        captured = {}

        async def fake_ingest(ext, equipment_id, contributor, client_type, full_name=None):
            captured["ext"] = ext
            captured["equipment_id"] = equipment_id
            captured["contributor"] = contributor
            return IngestResult(transaction_ids=[9])

        monkeypatch.setattr(
            "app.agent.service.engine.ingest_equipment_revision", fake_ingest
        )

        async def collect():
            chunks = [
                c
                async for c in handle_equipment_chat(
                    "El fabricante es Philips y la corriente del tubo es 10 mA nominal",
                    "eq-1",
                    {"username": "tec.maria", "full_name": "María Téc"},
                    "field_app",
                )
            ]
            return "".join(chunks)

        events = _parse_sse(run(collect()))

        token = next(e for e in events if e["type"] == "token")
        assert token["text"] == "Anotado: fabricante Philips y corriente del tubo 10 mA."
        extraction = next(e for e in events if e["type"] == "extraction")
        assert extraction["data"]["extractor"] == "llm"
        assert extraction["data"]["facility"] == "Clínica Puerto Verde"
        item = extraction["data"]["items"][0]
        assert item["manufacturer"] == "Philips"
        assert item["age_years"] == 4
        assert item["parameters"][0]["value"] == 10
        assert item["parameters"][0]["unit"] == "mA"
        followup = next(e for e in events if e["type"] == "followup")
        assert "modelo" in followup["question"].lower()
        assert events[-1]["type"] == "done"
        assert events[-1]["transaction_id"] == 9

        # La ingesta fue dirigida al equipo con el contribuyente autenticado.
        assert captured["equipment_id"] == "eq-1"
        assert captured["contributor"] == "tec.maria"
        assert captured["ext"].raw.startswith("El fabricante es Philips")

    def test_fallback_without_client_keeps_raw_observation(self, monkeypatch):
        monkeypatch.setattr("app.agent.service._client", None)
        self._patch_ctx(monkeypatch)
        captured = {}

        async def fake_ingest(ext, equipment_id, contributor, client_type, full_name=None):
            captured["ext"] = ext
            return IngestResult(transaction_ids=[])

        monkeypatch.setattr(
            "app.agent.service.engine.ingest_equipment_revision", fake_ingest
        )

        async def collect():
            chunks = [
                c
                async for c in handle_equipment_chat(
                    "La corriente del tubo es 10 mA nominal",
                    "eq-1",
                    {"username": "tec.maria", "full_name": None},
                    "field_app",
                )
            ]
            return "".join(chunks)

        events = _parse_sse(run(collect()))
        types = [e["type"] for e in events]
        assert types[0] == "token"  # ack de fallback
        extraction = next(e for e in events if e["type"] == "extraction")
        assert extraction["data"]["extractor"] == "rule"
        assert extraction["data"]["items"] == []
        assert events[-1]["type"] == "done"
        # Nada se inventa: la observación cruda se ancla al equipo.
        assert captured["ext"].raw == "La corriente del tubo es 10 mA nominal"
        assert captured["ext"].items == []

    def test_unknown_equipment_emits_error(self, monkeypatch):
        async def fake_ctx(eid):
            return None

        monkeypatch.setattr("app.agent.service.engine.get_equipment_context", fake_ctx)

        async def collect():
            chunks = [
                c
                async for c in handle_equipment_chat(
                    "hola", "eq-nope", {"username": "tec.maria", "full_name": None}
                )
            ]
            return "".join(chunks)

        events = _parse_sse(run(collect()))
        assert events[0]["type"] == "error"

    def test_llm_string_nulls_are_normalized(self, monkeypatch):
        # MedPsy en streaming emite la cadena "null" en lugar de JSON null;
        # debe normalizarse para no romper EquipmentItem (age_years float).
        payload = {
            "manufacturer": "Philips",
            "model": "null",
            "age_years": "null",
            "parameters": [],
            "note": None,
            "followup": None,
        }
        monkeypatch.setattr("app.agent.service._client", self._client(payload))
        self._patch_ctx(monkeypatch)
        captured = {}

        async def fake_ingest(ext, equipment_id, contributor, client_type, full_name=None):
            captured["ext"] = ext
            return IngestResult(transaction_ids=[])

        monkeypatch.setattr(
            "app.agent.service.engine.ingest_equipment_revision", fake_ingest
        )

        async def collect():
            return "".join(
                [
                    c
                    async for c in handle_equipment_chat(
                        "es Philips",
                        "eq-1",
                        {"username": "tec.maria", "full_name": None},
                    )
                ]
            )

        events = _parse_sse(run(collect()))
        extraction = next(e for e in events if e["type"] == "extraction")
        item = extraction["data"]["items"][0]
        assert item["manufacturer"] == "Philips"
        assert item["model"] is None
        assert item["age_years"] is None
        assert captured["ext"].followup is None
