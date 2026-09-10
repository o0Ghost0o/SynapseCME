"""Fase 5: router de intención + tool loop del asistente (QVAC mockeado)."""

import asyncio
import json

import httpx

from app.agent import assistant, service
from app.agent.qvac import QvacClient
from app.models import ChatRequest


def run(coro):
    return asyncio.run(coro)


def make_client(handler) -> QvacClient:
    transport = httpx.MockTransport(handler)
    return QvacClient("http://qvac.test", model="medpsy:q4_k_m", embed_model="bge", transport=transport)


def _chat_response(text: str) -> httpx.Response:
    """Respuesta no-stream de /v1/chat/completions (lo que usa client.chat)."""
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


class TestRouter:
    def _client(self, label: str) -> QvacClient:
        def handler(request):
            assert request.url.path == "/v1/chat/completions"
            body = json.loads(request.content)
            assert body["stream"] is False
            return _chat_response(label)

        return make_client(handler)

    def test_question(self):
        client = self._client("question")
        assert run(assistant.classify_intent(client, "¿Cuántas resonancias hay en Valencia?")) == "question"
        run(client.aclose())

    def test_observation(self):
        client = self._client("observation")
        assert (
            run(assistant.classify_intent(client, "En el Hospital Aurora hay 2 resonancias Siemens de 6 años"))
            == "observation"
        )
        run(client.aclose())

    def test_mixed(self):
        client = self._client("mixed")
        assert (
            run(assistant.classify_intent(client, "Hay 2 resonancias en Valencia, ¿cuántas tenemos registradas?"))
            == "mixed"
        )
        run(client.aclose())

    def test_garbage_defaults_to_observation(self):
        client = self._client("I am not sure, maybe banana")
        assert run(assistant.classify_intent(client, "hola")) == "observation"
        run(client.aclose())

    def test_unavailable_model_defaults_to_observation(self):
        client = make_client(lambda req: httpx.Response(503))
        assert run(assistant.classify_intent(client, "¿Qué equipos hay?")) == "observation"
        run(client.aclose())


def _parse_sse(stream: str):
    events = []
    for block in stream.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


class _ScriptedClient:
    """QvacClient mockeado: respuestas no-stream por orden de llamada."""

    def __init__(self, replies: list[str | None]):
        self.replies = list(replies)
        self.calls = 0
        self.model = "medpsy:mock"

    async def chat(self, messages, **kwargs):
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else None
        return reply

    async def stream_chat(self, messages, model=None):
        # El pipeline de observación no se ejercita con este mock: un QvacError
        # activa el fallback determinista (mismo contrato que QVAC caído).
        from app.agent.qvac import QvacError

        raise QvacError("mock sin streaming")
        yield  # pragma: no cover - marca la función como generador

    async def embed(self, text, model=None):
        return [0.1] * 8


def _question_request(message: str = "¿Qué equipos hay?") -> ChatRequest:
    return ChatRequest(message=message, client_type="field_app")


class TestToolLoop:
    def test_final_directo(self):
        client = _ScriptedClient(['{"action":"final","answer_es":"Hay 5 equipos."}'])
        result = run(
            assistant.answer_question(client, "¿Qué equipos hay?", intent="question", contributor="ana")
        )
        assert result.answer == "Hay 5 equipos."
        assert result.events == [{"type": "answer", "text": "Hay 5 equipos."}]
        assert client.calls == 1  # una sola llamada de loop (final directo)

    def test_una_tool_y_final(self, monkeypatch):
        client = _ScriptedClient(
            [
                '{"action":"tool","tool":"list_equipment","args":{"modality":"MR"}}',
                '{"action":"final","answer_es":"No hay equipos registrados."}',
            ]
        )
        result = run(
            assistant.answer_question(client, "¿Qué equipos hay?", intent="question", contributor="ana")
        )
        names = [e.get("name") for e in result.events if e["type"] == "tool"]
        assert names == ["list_equipment"]
        assert result.events[-1] == {"type": "answer", "text": "No hay equipos registrados."}

    def test_tool_desconocida_es_error_y_el_modelo_corrige(self):
        client = _ScriptedClient(
            [
                '{"action":"tool","tool":"run_cypher","args":{}}',
                '{"action":"final","answer_es":"No pude consultar eso."}',
            ]
        )
        result = run(
            assistant.answer_question(client, "consulta", intent="question", contributor="ana")
        )
        names = [e.get("name") for e in result.events if e["type"] == "tool"]
        assert names == ["run_cypher"]
        assert result.answer == "No pude consultar eso."

    def test_args_invalidos_detalle_y_correccion(self):
        client = _ScriptedClient(
            [
                '{"action":"tool","tool":"get_equipment_detail","args":{}}',
                '{"action":"tool","tool":"get_equipment_detail","args":{"id":"eq-x"}}',
                '{"action":"final","answer_es":"El equipo eq-x no existe."}',
            ]
        )
        result = run(
            assistant.answer_question(client, "dime del equipo eq-x", intent="question", contributor="ana")
        )
        names = [e.get("name") for e in result.events if e["type"] == "tool"]
        assert names == ["get_equipment_detail", "get_equipment_detail"]
        assert result.answer == "El equipo eq-x no existe."

    def test_limite_3_iteraciones_disculpa(self):
        client = _ScriptedClient(
            [
                '{"action":"tool","tool":"list_equipment","args":{}}',
                '{"action":"tool","tool":"list_equipment","args":{}}',
                '{"action":"tool","tool":"list_equipment","args":{}}',
            ]
        )
        result = run(
            assistant.answer_question(client, "¿Qué equipos hay?", intent="question", contributor="ana")
        )
        assert len([e for e in result.events if e["type"] == "tool"]) == 3
        assert result.answer == assistant.APOLOGY_ANSWER
        assert result.events[-1]["type"] == "answer"

    def test_json_invalido_se_corrige(self):
        client = _ScriptedClient(
            [
                "no es json",
                '{"action":"final","answer_es":"Respuesta tras corregir."}',
            ]
        )
        result = run(
            assistant.answer_question(client, "hola", intent="question", contributor="ana")
        )
        assert result.answer == "Respuesta tras corregir."

    def test_ingest_solo_permitido_en_mixed(self):
        client = _ScriptedClient(
            [
                '{"action":"tool","tool":"ingest_observation","args":{"text":"x"}}',
                '{"action":"final","answer_es":"ok"}',
            ]
        )
        result = run(
            assistant.answer_question(client, "pregunta", intent="question", contributor="ana")
        )
        assert result.answer == "ok"
        # Solo se llamó una vez al modelo tras el rechazo del tool + final
        assert client.calls == 2

    def test_ingest_en_mixed_persiste_en_grafo(self, monkeypatch):
        ingested = {}

        class FakeIngest:
            transaction_ids = [42]

        async def fake_ingest(ext, contributor, client_type, full_name=None):
            ingested["ext"] = ext
            ingested["contributor"] = contributor
            return FakeIngest()

        monkeypatch.setattr("app.graph.engine.ingest_extraction", fake_ingest)
        monkeypatch.setattr("app.agent.assistant.rag.index_extraction", _noop_async)
        monkeypatch.setattr(
            "app.agent.assistant.sync_service.enqueue_extraction", _noop_async
        )

        client = _ScriptedClient(
            [
                '{"action":"tool","tool":"ingest_observation","args":{"text":"En el Hospital Aurora hay 1 resonancia Siemens de 6 años, el helio está al 45%"}}',
                '{"action":"final","answer_es":"Registré la observación y hay 1 resonancia."}',
            ]
        )
        result = run(
            assistant.answer_question(
                client,
                "Hay 1 resonancia en el Hospital Aurora, ¿cuántas hay en total?",
                intent="mixed",
                contributor="ana",
            )
        )
        assert result.answer == "Registré la observación y hay 1 resonancia."
        ext = ingested["ext"]
        assert ext.facility == "Hospital Aurora"
        assert any(i.modality == "MR" for i in ext.items)
        assert ingested["contributor"] == "ana"


async def _noop_async(*args, **kwargs):
    return None


class TestQuestionPipeline:
    """handle_chat completo con el router: question/mixed vía tool loop,
    observation preservada cuando el modelo devuelve basura."""

    def _scripted_service_client(self, monkeypatch, replies: list[str | None]):
        client = _ScriptedClient(replies)
        monkeypatch.setattr("app.agent.service._client", client)
        return client

    def test_question_emite_tool_answer_done_sin_extraction(self, monkeypatch):
        self._scripted_service_client(
            monkeypatch,
            [
                "question",
                '{"action":"tool","tool":"list_equipment","args":{}}',
                '{"action":"final","answer_es":"Hay 3 equipos registrados."}',
            ],
        )
        request = _question_request()

        async def collect():
            return "".join([chunk async for chunk in service.handle_chat(request)])

        events = _parse_sse(run(collect()))
        types = [e["type"] for e in events]
        assert "extraction" not in types
        assert types.count("tool") == 1
        assert types[-2] == "answer"
        assert types[-1] == "done"
        answer = next(e for e in events if e["type"] == "answer")
        assert answer["text"] == "Hay 3 equipos registrados."

    def test_question_persiste_mensaje_sin_extraccion(self, monkeypatch):
        self._scripted_service_client(
            monkeypatch,
            ["question", '{"action":"final","answer_es":"Respuesta."}'],
        )
        saved = []

        async def fake_add(conversation_id, role, content, extraction=None):
            saved.append(
                {"cid": conversation_id, "role": role, "content": content, "extraction": extraction}
            )
            return None

        monkeypatch.setattr("app.agent.service.db.add_chat_message", fake_add)
        request = _question_request()

        async def collect():
            return "".join(
                [chunk async for chunk in service.handle_chat(request, conversation_id="conv-1")]
            )

        events = _parse_sse(run(collect()))
        done = events[-1]
        assert done["type"] == "done"
        assert done["conversation_id"] == "conv-1"
        assert saved and saved[-1]["role"] == "assistant"
        assert saved[-1]["content"] == "Respuesta."
        assert saved[-1]["extraction"] is None
        assert saved[-1]["cid"] == "conv-1"

    def test_mixed_via_handle_chat(self, monkeypatch):
        self._scripted_service_client(
            monkeypatch,
            [
                "mixed",
                '{"action":"tool","tool":"ingest_observation","args":{"text":"En el Hospital Aurora hay 1 tomógrafo GE de 4 años"}}',
                '{"action":"final","answer_es":"Registrado."}',
            ],
        )
        ingested = {}

        class FakeIngest:
            transaction_ids = [7]

        async def fake_ingest(ext, contributor, client_type, full_name=None):
            ingested["ext"] = ext
            return FakeIngest()

        monkeypatch.setattr("app.graph.engine.ingest_extraction", fake_ingest)
        monkeypatch.setattr("app.agent.assistant.rag.index_extraction", _noop_async)
        monkeypatch.setattr(
            "app.agent.assistant.sync_service.enqueue_extraction", _noop_async
        )
        request = _question_request("En el Hospital Aurora hay 1 tomógrafo GE, ¿cuántos CT hay?")

        async def collect():
            return "".join([chunk async for chunk in service.handle_chat(request)])

        events = _parse_sse(run(collect()))
        types = [e["type"] for e in events]
        assert "tool" in types and "answer" in types
        assert ingested["ext"].facility == "Hospital Aurora"

    def test_router_basura_preserva_pipeline_observacion(self, monkeypatch):
        # LLM que responde basura al router → observation → pipeline actual
        # (extractor por reglas) con sus eventos token/extraction/done.
        client = _ScriptedClient(["banana"])
        monkeypatch.setattr("app.agent.service._client", client)
        request = ChatRequest(
            message="Visité el Hospital Aurora en Panamá, vi 3 resonancias magnéticas",
            client_type="field_app",
        )

        async def collect():
            return "".join([chunk async for chunk in service.handle_chat(request)])

        events = _parse_sse(run(collect()))
        types = [e["type"] for e in events]
        assert "extraction" in types
        assert "answer" not in types
        extraction = next(e for e in events if e["type"] == "extraction")
        assert extraction["data"]["facility"] == "Hospital Aurora"
