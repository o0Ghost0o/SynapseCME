"""Chat pipeline: QVAC streaming LLM extraction with rule-based fallback.

Emits SSE payload dicts in contract order:
    token* -> extraction -> followup? -> done
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator

from app import db
from app.agent import assistant
from app.agent import extractor as rule_extractor
from app.agent import rag
from app.agent.qvac import QvacClient, QvacError
from app.core.config import Settings, settings
from app.core.metrics import InferenceMetrics, build_metrics
from app.graph import engine
from app.models import ChatRequest, EquipmentItem, ExtractionResult, ParameterExtraction
from app.sync import service as sync_service

logger = logging.getLogger("synapse.agent")

# Model-facing prompt in ENGLISH: MedPsy (qvac/MedPsy-1.7B) is an
# English-only model — Spanish system instructions degrade instruction
# following. The field observation itself stays in Spanish; MedPsy handles
# short entity-rich Spanish sentences fine. The follow-up question must be
# in Spanish because it is shown verbatim to the user.
EXTRACTION_SYSTEM_PROMPT = """You are the SynapseCME agent, an intelligence platform for \
medical equipment installed in hospitals. A field engineer sends you an observation in \
Spanish about a hospital visit.

Extract structured entities and reply with ONLY a JSON object (no text outside the \
JSON) with this exact shape:
{
  "facility": "hospital or clinic name",
  "city": "city or null",
  "country": "country or null",
  "items": [
    {
      "modality": "MR|CT|XR|UL|MG|RF",
      "manufacturer": "manufacturer or null",
      "model": "model or null",
      "quantity": 1,
      "age_years": null,
      "confidence": 0.0,
      "parameters": [
        {"name": "parameter name", "value": 0.0, "unit": "unit or null", "status": "ok|warning|critical|null"}
      ]
    }
  ],
  "followup": "short follow-up question in Spanish if a key datum is missing (MR/CT manufacturer), or null"
}

Modality codes: resonancia magnética/MRI=MR, tomógrafo/CT scanner=CT, rayos X/X-ray=XR, \
ultrasonido/ultrasound=UL, mamografía/mammography=MG, fluoroscopia/C-arm=RF. Use null for \
unknown fields. confidence between 0 and 1 reflecting how clear the datum is.

parameters: when an observation mentions technical magnitudes for an equipment unit \
(electric current, voltage, temperature, pressure, helium level, tube scan count, dose \
rate, uptime hours...), extract one entry per magnitude. "value" must be a number \
("45%" -> 45 with unit "%"); use a string only if it is not numeric. "name" in Spanish, \
short ("nivel de helio", "corriente del tubo", "cortes de tubo", "tasa de dosis"). \
"status" is INFERRED, never copied from the text: "nominal, correcto, dentro de rango, \
normal, estable" -> ok; "alto, bajo, inestable, fluctuante, desgastado" -> warning; \
"fuera de rango, falla, crítico, sobrecarga" -> critical; if it cannot be inferred, \
use null. Only include parameters actually mentioned; an empty list is fine.

Do not add anything after the JSON."""

FALLBACK_ACK = (
    "Entendido. Registré tu observación con el extractor local "
    "(el nodo de inferencia no respondió, así que usé reglas deterministas)."
)

RAG_INSTRUCTIONS = (
    "The block above is prior knowledge retrieved from the database; "
    "it may be incomplete. Use it to disambiguate facilities and equipment, "
    "but never invent equipment that does not appear in the message or in that context."
)

# Conversación titles (Fase 4): one short non-streaming call after the first
# exchange. English-only model; the title itself must be Spanish.
TITLE_SYSTEM_PROMPT = (
    "You generate very short conversation titles. Reply with only the title: "
    "no quotes, no trailing punctuation, no explanation."
)
TITLE_USER_TEMPLATE = (
    "Generate a 3-6 word Spanish title summarizing this exchange. "
    "Reply with only the title.\nUser: {message}\nAssistant: {response}"
)

_title_tasks: set[asyncio.Task[None]] = set()


async def generate_conversation_title(
    client: QvacClient | None,
    conversation_id: str,
    user_message: str,
    assistant_text: str = "",
) -> str | None:
    """Set the conversation title once (first exchange only).

    LLM title when QVAC answers; deterministic fallback (first 6 words of the
    user's message) otherwise. Returns the applied title or None when the
    conversation already had one / the update failed.
    """
    existing = await db.get_conversation(conversation_id)
    if existing is None or existing.get("title"):
        return None
    title = ""
    if client is not None:
        try:
            reply = await client.chat(
                [
                    {"role": "system", "content": TITLE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": TITLE_USER_TEMPLATE.format(
                            message=user_message, response=assistant_text or "…"
                        ),
                    },
                ],
                temperature=0.0,
                # MedPsy is a reasoning model: it thinks before answering, so
                # the budget must cover the reasoning trace plus the title.
                max_tokens=256,
            )
            if reply:
                title = reply.strip().strip('"').strip()
                if "\n" in title:
                    title = title.splitlines()[-1].strip().strip('"').strip()
        except Exception as exc:  # noqa: BLE001 - titles must never break chat
            logger.warning("Generación de título falló; usando fallback: %s", exc)
    if not title:
        title = " ".join(user_message.split()[:6])
    if await db.set_conversation_title(conversation_id, title):
        return title
    return None


def _schedule_title(
    client: QvacClient | None,
    conversation_id: str,
    user_message: str,
    assistant_text: str,
) -> None:
    """Fire-and-forget title generation; keeps a strong ref until it finishes."""
    task = asyncio.create_task(
        generate_conversation_title(client, conversation_id, user_message, assistant_text)
    )
    _title_tasks.add(task)
    task.add_done_callback(_title_tasks.discard)

_client: QvacClient | None = None


def init_client(settings: Settings) -> QvacClient:
    global _client
    _client = QvacClient(
        base_url=settings.qvac_base_url,
        model=settings.medpsy_model,
        embed_model=settings.embed_model,
    )
    return _client


def get_client() -> QvacClient | None:
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def parse_llm_json(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of an LLM reply (fenced or bare)."""
    fenced = text.find("```")
    if fenced != -1:
        start = text.find("{", fenced)
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start : end + 1]
        else:
            candidate = None
    else:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else None

    if not candidate:
        return None
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # try to repair truncated JSON: cut to last complete key-value pair
        try:
            last_brace = candidate.rfind("}")
            data = json.loads(candidate[: last_brace + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return data if isinstance(data, dict) else None


_VALID_STATUSES = ("ok", "warning", "critical")


def _coerce_parameter_value(value: Any) -> tuple[float | str | None, str | None]:
    """Normalise an LLM-supplied value: "45%" -> (45, "%"), strings stay text."""
    if value is None or isinstance(value, (int, float)):
        return value, None
    text = str(value).strip()
    match = re.fullmatch(r"(-?\d+(?:[.,]\d+)?)\s*(%|[a-zA-Zµ°/]+)?", text)
    if match:
        number = float(match.group(1).replace(",", "."))
        return (int(number) if number.is_integer() else number), match.group(2)
    return text or None, None


def _parse_parameters(raw: Any) -> list[ParameterExtraction]:
    params: list[ParameterExtraction] = []
    if not isinstance(raw, list):
        return params
    for p in raw:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        status = p.get("status")
        value, unit_suffix = _coerce_parameter_value(p.get("value"))
        unit = p.get("unit") or unit_suffix
        params.append(
            ParameterExtraction(
                name=str(p["name"]).strip(),
                value=value,
                unit=str(unit).strip() if unit else None,
                status=status if status in _VALID_STATUSES else None,
            )
        )
    return params


def _extraction_from_llm(data: dict[str, Any], raw: str) -> ExtractionResult | None:
    if not isinstance(data, dict) or "items" not in data:
        return None
    try:
        items = [
            EquipmentItem(
                modality=str(i.get("modality", "")).upper()[:2] or "OT",
                manufacturer=i.get("manufacturer"),
                model=i.get("model"),
                quantity=max(int(i.get("quantity") or 1), 1),
                age_years=i.get("age_years"),
                confidence=float(i.get("confidence") or 0.5),
                parameters=_parse_parameters(i.get("parameters")),
            )
            for i in data.get("items") or []
            if isinstance(i, dict)
        ]
        ext = ExtractionResult(
            facility=data.get("facility"),
            city=data.get("city"),
            country=data.get("country"),
            items=items,
            confidence=0.75,
            raw=raw,
            extractor="llm",
        )
        ext.followup = data.get("followup") or rule_extractor.build_followup(ext)
        ext.missing_fields = [
            f for f in ("facility", "country", "manufacturer") if f not in data
        ]
        return ext
    except (TypeError, ValueError):
        return None


async def handle_chat(
    request: ChatRequest,
    user: dict[str, Any] | None = None,
    *,
    conversation_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield SSE-encoded strings for the /api/chat stream.

    ``user`` is the authenticated JWT identity. The client-supplied
    ``contributor`` field is intentionally ignored: the capturer identity
    everywhere (Contributor node, MADE_BY, transaction_log actor) is the
    authenticated user.

    ``conversation_id`` is the already-validated Postgres conversation this
    exchange belongs to (validated in the endpoint; the user's message has
    been persisted there before streaming starts). The assistant message is
    persisted after the pipeline and the ``done`` event carries the id so the
    client can anchor its session list. The conversation title is generated
    asynchronously after ``done`` (fire-and-forget): clients refresh the list
    via GET /api/conversations.
    """
    request_id = uuid.uuid4().hex[:12]
    if user is not None:
        contributor = user["username"]
        full_name = user.get("full_name")
    else:
        contributor = f"anon-{request.client_type or 'web'}"
        full_name = None
    started = time.perf_counter()
    ttft_ms: int | None = None
    usage: dict[str, Any] | None = None
    full_text = ""
    emitted_text = ""  # texto realmente mostrado al usuario como tokens
    used_fallback = False
    ext: ExtractionResult | None = None

    cold_start = False  # kept for build_metrics signature stability; QVAC preloads models
    client = _client

    # 0) Intent routing (Fase 5): questions go to the bounded tool loop;
    # observations (default, also when the model is unreachable) keep the
    # extraction pipeline below unchanged.
    intent = assistant.INTENT_OBSERVATION
    if client is not None:
        intent = assistant.classify_intent(client, request.message)
    if intent in (assistant.INTENT_QUESTION, assistant.INTENT_MIXED) and client is not None:
        async for chunk in _handle_question(
            request, conversation_id, client, contributor, full_name, started, intent
        ):
            yield chunk
        return

    system_prompt = EXTRACTION_SYSTEM_PROMPT
    if client is not None:
        try:
            context_text = await rag.build_context(
                client,
                request.message,
                data_dir=settings.rag_dir,
                top_k=settings.rag_top_k,
            )
            if context_text:
                system_prompt = (
                    f"{EXTRACTION_SYSTEM_PROMPT}\n\n{context_text}\n\n{RAG_INSTRUCTIONS}"
                )
        except Exception as exc:  # noqa: BLE001 - retrieval must not kill the stream
            logger.warning("Recuperación de contexto RAG falló; se continúa sin ella: %s", exc)

    # 1) Try the LLM pipeline ----------------------------------------------
    if client is not None:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message},
        ]
        try:
            async for event in client.stream_chat(messages):
                now_ms = int((time.perf_counter() - started) * 1000)
                if event.get("done"):
                    usage = event.get("usage")
                    continue
                token = event.get("token", "")
                if ttft_ms is None:
                    ttft_ms = now_ms
                # Los tokens del LLM NO se retransmiten: el contrato pide
                # JSON puro, así que el stream de tokens sería el JSON crudo
                # de extracción renderizado como mensaje. Se acumulan y solo
                # se emiten como texto si la respuesta no es JSON de extracción.
                full_text += token
        except QvacError as exc:
            logger.warning("Extractor con reglas activado: %s", exc)
            used_fallback = True

        if not used_fallback:
            data = parse_llm_json(full_text)
            ext = _extraction_from_llm(data, request.message) if data else None
            if ext is None or not ext.items:
                logger.warning(
                    "La respuesta del modelo no trajo JSON válido; "
                    "usando extractor por reglas"
                )
                if data is None and full_text.strip():
                    # Texto libre (no JSON): sí es contenido para el usuario.
                    emitted_text = full_text
                    yield _sse({"type": "token", "text": full_text})
                used_fallback = True
                ext = None
    else:
        used_fallback = True

    # 2) Deterministic fallback --------------------------------------------
    if used_fallback or ext is None:
        ext = rule_extractor.extract(request.message)
        ext.followup = ext.followup or rule_extractor.build_followup(ext)
        if used_fallback:
            emitted_text = FALLBACK_ACK
            yield _sse({"type": "token", "text": FALLBACK_ACK})

    yield _sse({"type": "extraction", "data": ext.model_dump()})

    # 3) Ingest into the graph ----------------------------------------------
    transaction_ids: list[int] = []
    try:
        ingest = await engine.ingest_extraction(
            ext, contributor, request.client_type, full_name=full_name
        )
        transaction_ids = ingest.transaction_ids
        try:
            await sync_service.enqueue_extraction(ext, contributor, request.client_type)
        except Exception:  # noqa: BLE001 - sync must never affect the stream
            pass
        if client is not None:
            try:
                await rag.index_extraction(client, ext, data_dir=settings.rag_dir)
            except Exception as exc:  # noqa: BLE001 - indexing must not kill the stream
                logger.warning("No se pudo indexar la observación: %s", exc)
    except Exception as exc:  # noqa: BLE001 - ingestion must not kill the stream
        logger.exception("Error al ingerir la extracción en el grafo: %s", exc)

    # 4) Follow-up question ---------------------------------------------------
    if ext.followup:
        yield _sse({"type": "followup", "question": ext.followup})

    # 5) Metrics (fire and forget) --------------------------------------------
    total_ms = int((time.perf_counter() - started) * 1000)
    metrics = build_metrics(
        model=client.model if client else "rule-fallback",
        ttft_ms=ttft_ms if ttft_ms is not None else total_ms,
        total_ms=total_ms,
        prompt_text=request.message + EXTRACTION_SYSTEM_PROMPT,
        generated_text=full_text,
        usage=usage,
        cold_start=cold_start,
    )
    try:
        await db.log_perf(request_id, metrics)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo guardar perf_log: %s", exc)

    # 6) Persist the assistant turn (never blocks/affects the stream) --------
    if conversation_id is not None:
        try:
            await db.add_chat_message(
                conversation_id,
                "assistant",
                emitted_text,
                extraction=ext.model_dump(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo persistir el mensaje del asistente: %s", exc)

    done_payload: dict[str, Any] = {
        "type": "done",
        "transaction_id": transaction_ids[0] if transaction_ids else request_id,
    }
    if conversation_id is not None:
        done_payload["conversation_id"] = conversation_id
    yield _sse(done_payload)

    # 7) Title for new conversations: fire-and-forget after `done`. The
    # client refreshes its list via GET /api/conversations (the title lands
    # seconds later); never block the SSE on this call.
    if conversation_id is not None:
        _schedule_title(client, conversation_id, request.message, emitted_text)


async def _handle_question(
    request: ChatRequest,
    conversation_id: str | None,
    client: QvacClient,
    contributor: str,
    full_name: str | None,
    started: float,
    intent: str,
) -> AsyncIterator[str]:
    """SSE stream for question/mixed intents: bounded tool loop (assistant.py).

    Emits the new backwards-compatible events ``tool`` (one per tool call) and
    ``answer`` (final Spanish answer), then ``done`` with the same
    conversation anchoring as the observation pipeline. The assistant message
    is persisted with ``extraction=None``; the title is scheduled
    fire-and-forget exactly like the observation path.
    """
    request_id = uuid.uuid4().hex[:12]
    result = await assistant.answer_question(
        client,
        request.message,
        intent=intent,
        contributor=contributor,
        client_type=request.client_type,
        full_name=full_name,
        data_dir=settings.rag_dir,
    )
    emitted_text = ""
    for event in result.events:
        if event.get("type") == "answer":
            emitted_text = str(event.get("text") or "")
        yield _sse(event)

    total_ms = int((time.perf_counter() - started) * 1000)
    metrics = build_metrics(
        model=client.model,
        ttft_ms=total_ms,
        total_ms=total_ms,
        prompt_text=request.message + assistant.TOOL_SYSTEM_PROMPT,
        generated_text=result.generated,
        usage=None,
        cold_start=False,
    )
    try:
        await db.log_perf(request_id, metrics)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo guardar perf_log: %s", exc)

    if conversation_id is not None:
        try:
            await db.add_chat_message(
                conversation_id, "assistant", emitted_text, extraction=None
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo persistir el mensaje del asistente: %s", exc)

    done_payload: dict[str, Any] = {"type": "done", "transaction_id": request_id}
    if conversation_id is not None:
        done_payload["conversation_id"] = conversation_id
    yield _sse(done_payload)

    if conversation_id is not None:
        _schedule_title(client, conversation_id, request.message, emitted_text)


def record_inference(request_id: str, metrics: InferenceMetrics) -> None:
    """Sync-ish helper kept for tests/other callers; schedules log_perf."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(db.log_perf(request_id, metrics))
    except RuntimeError:
        asyncio.run(db.log_perf(request_id, metrics))
