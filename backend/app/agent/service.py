"""Chat pipeline: QVAC streaming LLM extraction with rule-based fallback.

Emits SSE payload dicts in contract order:
    token* -> extraction -> followup? -> done
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from app import db
from app.agent import extractor as rule_extractor
from app.agent.qvac import QvacClient, QvacError
from app.core.config import Settings
from app.core.metrics import InferenceMetrics, build_metrics
from app.graph import engine
from app.models import ChatRequest, EquipmentItem, ExtractionResult

logger = logging.getLogger("synapse.agent")

EXTRACTION_SYSTEM_PROMPT = """Eres el agente de SynapseCME, una plataforma de inteligencia \
sobre equipos médicos instalados en hospitales. Un ingeniero de campo te envía una \
observación en español sobre una visita a un hospital.

Extrae entidades estructuradas y responde ÚNICAMENTE con un objeto JSON (sin texto fuera \
del JSON) con esta forma exacta:
{
  "facility": "nombre del hospital o clínica",
  "city": "ciudad o null",
  "country": "país o null",
  "items": [
    {
      "modality": "MR|CT|XR|UL|MG|RF",
      "manufacturer": "fabricante o null",
      "model": "modelo o null",
      "quantity": 1,
      "age_years": null,
      "confidence": 0.0
    }
  ],
  "followup": "pregunta corta de seguimiento si falta un dato clave (fabricante de RM/TC), o null"
}

Códigos de modalidad: resonancia magnética=MR, tomógrafo/TC=CT, rayos X=XR, \
ultrasonido=UL, mamografía=MG, fluoroscopia/C-arm=RF. Usa null para lo desconocido. \
confidence entre 0 y 1 según claridad del dato.

Después del JSON no añadas nada más."""

FALLBACK_ACK = (
    "Entendido. Registré tu observación con el extractor local "
    "(el nodo de inferencia no respondió, así que usé reglas deterministas)."
)

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


async def handle_chat(request: ChatRequest, user: dict[str, Any] | None = None) -> AsyncIterator[str]:
    """Yield SSE-encoded strings for the /api/chat stream.

    ``user`` is the authenticated JWT identity. The client-supplied
    ``contributor`` field is intentionally ignored: the capturer identity
    everywhere (Contributor node, MADE_BY, transaction_log actor) is the
    authenticated user.
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
    used_fallback = False
    ext: ExtractionResult | None = None

    cold_start = False
    client = _client
    if client is not None:
        try:
            cold_start = not await client.is_model_loaded()
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo consultar /api/ps: %s", exc)

    # 1) Try the LLM pipeline ----------------------------------------------
    if client is not None:
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
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
                full_text += token
                yield _sse({"type": "token", "text": token})
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
                used_fallback = True
                ext = None
    else:
        used_fallback = True

    # 2) Deterministic fallback --------------------------------------------
    if used_fallback or ext is None:
        ext = rule_extractor.extract(request.message)
        ext.followup = ext.followup or rule_extractor.build_followup(ext)
        if used_fallback:
            yield _sse({"type": "token", "text": FALLBACK_ACK})

    yield _sse({"type": "extraction", "data": ext.model_dump()})

    # 3) Ingest into the graph ----------------------------------------------
    transaction_ids: list[int] = []
    try:
        ingest = await engine.ingest_extraction(
            ext, contributor, request.client_type, full_name=full_name
        )
        transaction_ids = ingest.transaction_ids
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

    yield _sse(
        {
            "type": "done",
            "transaction_id": transaction_ids[0] if transaction_ids else request_id,
        }
    )


def record_inference(request_id: str, metrics: InferenceMetrics) -> None:
    """Sync-ish helper kept for tests/other callers; schedules log_perf."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(db.log_perf(request_id, metrics))
    except RuntimeError:
        asyncio.run(db.log_perf(request_id, metrics))
