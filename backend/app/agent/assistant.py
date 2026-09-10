"""Agentic assistant: intent router + tool loop for questions (Fase 5).

MedPsy 1.7B is English-only and weak, so both prompts are strict English
JSON-only contracts with few-shot examples, temperature 0. The router
classifies each user message; observations keep the existing extraction
pipeline, while questions/mixed run a bounded tool loop that reuses the
graph engine, RAG retrieval and graph context (never free Cypher).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from app.agent import extractor as rule_extractor
from app.agent import rag
from app.agent.qvac import QvacClient
from app.graph import engine
from app.graph.context import graph_context
from app.sync import service as sync_service

logger = logging.getLogger("synapse.agent")

MAX_TOOL_ITERATIONS = 3
MAX_TOOL_RESULT_CHARS = 1500
LIST_EQUIPMENT_LIMIT = 20

INTENT_QUESTION = "question"
INTENT_OBSERVATION = "observation"
INTENT_MIXED = "mixed"

# Fallback when the loop exhausts its iterations without a final answer.
APOLOGY_ANSWER = (
    "Lo siento, no pude completar la consulta con la información disponible. "
    "Inténtalo de nuevo con más detalle."
)

TOOL_SYSTEM_PROMPT = """You are the SynapseCME assistant, answering in Spanish questions about medical \
equipment installed in hospitals. You can call tools. Reply with ONLY one JSON object per turn, \
no text outside the JSON:
{"action":"tool","tool":"<tool name>","args":{...}}  to call a tool
{"action":"final","answer_es":"<your answer in Spanish>"}  when you have enough information

Tools:
- list_equipment(args: modality?, manufacturer?, state?, country?, facility?, has_issue?) -> list of \
equipment units matching the filters. modality is a code: MR, CT, XR, UL, MG, RF. Use has_issue=true \
to list only units with parameters in warning or critical status.
- get_equipment_detail(args: id) -> one equipment unit with its parameters (with status) and recent observations.
- search_observations(args: query) -> past field observations similar to the query (texts).
- get_facility_info(args: name) -> equipment known at a facility.
- ingest_observation(args: text) -> registers a new field observation into the database. Use ONLY when \
the user's message reports new field data; pass the reported text.

Rules:
- Call at most one tool per turn. After each tool result, call another tool or answer.
- NEVER invent equipment, numbers or facts: only use information returned by tools.
- If the tools found nothing, say so honestly in the answer.
- answer_es must be a short, complete answer in Spanish.
- Always reply with valid JSON only.

Example:
User: Cuantas resonancias hay en Valencia?
{"action":"tool","tool":"list_equipment","args":{"modality":"MR","facility":"Valencia"}}
{"action":"final","answer_es":"Hay 3 resonancias registradas en Valencia."}"""


@dataclass
class AssistantResult:
    """Buffered tool-loop output: SSE event dicts + the final Spanish answer."""

    events: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    generated: str = ""  # texto crudo acumulado de las llamadas al modelo (métricas)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of an LLM reply (fenced or bare)."""
    if "```" in text:
        start = text.find("{", text.find("```"))
    else:
        start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# MedPsy is a reasoning model: even short routing calls burn most tokens on
# reasoning_content and the label arrives late or never, adding ~30-60s of
# latency to every message. Intent routing is therefore deterministic:
# - "?" or an interrogative start => the user asks something (question)
# - digits in the message => the user reports field data (observation/mixed)
_QUESTION_MARK_RE = re.compile(r"[?¿]")
_INTERROGATIVE_START_RE = re.compile(
    r"^\s*(qu[ée]|cu[áa]l|cu[áa]nt\w*|c[óo]mo|d[óo]nde|cu[áa]ndo|qui[ée]n)\b",
    re.IGNORECASE,
)


def classify_intent(client: QvacClient | None, message: str) -> str:
    """question | observation | mixed, via deterministic Spanish heuristics.

    ``client`` is kept for signature compatibility; routing no longer calls
    the LLM (see module note above). Anything that is not clearly a question
    is treated as an observation, preserving the historical capture flow.
    """
    text = message or ""
    has_question = bool(_QUESTION_MARK_RE.search(text)) or bool(
        _INTERROGATIVE_START_RE.match(text)
    )
    has_field_data = any(ch.isdigit() for ch in text)
    if has_question and has_field_data:
        return INTENT_MIXED
    if has_question:
        return INTENT_QUESTION
    return INTENT_OBSERVATION


def _truncate(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


def _as_str(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in ("true", "1", "yes", "sí", "si")


async def _tool_list_equipment(args: dict[str, Any]) -> str:
    result = await engine.list_equipments(
        modality=_as_str(args.get("modality")),
        manufacturer=_as_str(args.get("manufacturer")),
        state=_as_str(args.get("state")),
        country=_as_str(args.get("country")),
        facility=_as_str(args.get("facility")),
        has_issue=_as_bool(args.get("has_issue")),
        limit=LIST_EQUIPMENT_LIMIT,
    )
    total = int(result.get("total") or 0)
    items = result.get("items") or []
    if not total:
        return "No equipment units matched the filters."
    lines = [f"{total} equipment unit(s) matched. First {len(items)}:"]
    for it in items:
        label = " ".join(
            str(it[k]) for k in ("modality", "manufacturer", "model") if it.get(k)
        ) or "unknown equipment"
        extras = []
        if it.get("state"):
            extras.append(f"state={it['state']}")
        if it.get("age_years") is not None:
            extras.append(f"age={it['age_years']}y")
        if it.get("facility_name"):
            extras.append(f"facility={it['facility_name']}")
        if it.get("country"):
            extras.append(f"country={it['country']}")
        if it.get("has_issue"):
            extras.append("HAS ISSUE (warning/critical parameter)")
        lines.append(f"- {label} ({', '.join(extras)})" if extras else f"- {label}")
    if total > len(items):
        lines.append(f"... and {total - len(items)} more.")
    return _truncate("\n".join(lines))


async def _tool_get_equipment_detail(args: dict[str, Any]) -> str:
    eid = _as_str(args.get("id"))
    if eid is None:
        return "Error: get_equipment_detail requires args.id (the equipment id)."
    detail = await engine.get_equipment_detail(eid)
    if detail is None:
        return f"No equipment found with id '{eid}'."
    eq = detail["equipment"]
    lines = [
        " ".join(str(eq[k]) for k in ("modality", "manufacturer", "model") if eq.get(k))
        or "unknown equipment"
    ]
    if eq.get("facility_name"):
        loc = ", ".join(str(x) for x in (eq.get("city"), eq.get("country")) if x)
        lines.append(f"facility: {eq['facility_name']}{f' ({loc})' if loc else ''}")
    if eq.get("state"):
        lines.append(f"state: {eq['state']}")
    if eq.get("quantity"):
        lines.append(f"quantity: {eq['quantity']}")
    if eq.get("age_years") is not None:
        lines.append(f"age: {eq['age_years']} years")
    params = detail.get("parameters") or []
    if params:
        lines.append("Parameters (latest):")
        for p in params:
            value = " ".join(
                str(x) for x in (p.get("value"), p.get("unit")) if x is not None
            )
            status = p.get("status") or "unknown"
            lines.append(f"- {p['name']}: {value or '—'} (status: {status})")
    else:
        lines.append("Parameters: none recorded.")
    observations = [o for o in (detail.get("observations") or []) if o.get("text")]
    if observations:
        lines.append("Recent observations:")
        for o in observations[:5]:
            lines.append(f"- {str(o['text'])[:160]}")
    return _truncate("\n".join(lines))


async def _tool_search_observations(args: dict[str, Any], ctx: Any) -> str:
    query = _as_str(args.get("query"))
    if query is None:
        return "Error: search_observations requires args.query."
    rows = await rag.retrieve(ctx.client, query, data_dir=ctx.data_dir, top_k=5)
    if not rows:
        return "No similar past observations found."
    lines = []
    for row in rows:
        parts = [str(row[k]) for k in ("facility",) if row.get(k)]
        if row.get("extractor"):
            parts.append(f"extractor={row['extractor']}")
        prefix = f"[{', '.join(parts)}] " if parts else ""
        lines.append(f"- {prefix}{str(row.get('text') or '')[:300]}")
    return _truncate("\n".join(lines))


async def _tool_get_facility_info(args: dict[str, Any]) -> str:
    name = _as_str(args.get("name"))
    if name is None:
        return "Error: get_facility_info requires args.name (the facility name)."
    context = await graph_context(name)
    if not context:
        return f"No facility named '{name}' is known."
    return _truncate(f"Equipment known at {name}:\n{context}")


async def _tool_ingest_observation(args: dict[str, Any], ctx: Any) -> str:
    text = _as_str(args.get("text"))
    if text is None:
        return "Error: ingest_observation requires args.text (the observation text)."
    ext = rule_extractor.extract(text)
    ext.followup = ext.followup or rule_extractor.build_followup(ext)
    if not ext.items:
        return "Could not extract any equipment from that text; nothing was registered."
    ingest = await engine.ingest_extraction(
        ext, ctx.contributor, ctx.client_type, full_name=ctx.full_name
    )
    try:
        await sync_service.enqueue_extraction(ext, ctx.contributor, ctx.client_type)
    except Exception as exc:  # noqa: BLE001 - sync must never affect the loop
        logger.warning("No se pudo encolar la sincronización: %s", exc)
    try:
        await rag.index_extraction(ctx.client, ext, data_dir=ctx.data_dir)
    except Exception as exc:  # noqa: BLE001 - indexing must not kill the loop
        logger.warning("No se pudo indexar la observación: %s", exc)
    n_params = sum(len(i.parameters) for i in ext.items)
    summary = (
        f"Registered observation. facility={ext.facility}, "
        f"{len(ext.items)} equipment unit(s), {n_params} parameter(s), "
        f"{len(ingest.transaction_ids)} transaction(s)."
    )
    return summary


_TOOL_NAMES = (
    "list_equipment",
    "get_equipment_detail",
    "search_observations",
    "get_facility_info",
    "ingest_observation",
)


async def _exec_tool(name: str, args: dict[str, Any], ctx: Any) -> str:
    if name == "list_equipment":
        return await _tool_list_equipment(args)
    if name == "get_equipment_detail":
        return await _tool_get_equipment_detail(args)
    if name == "search_observations":
        return await _tool_search_observations(args, ctx)
    if name == "get_facility_info":
        return await _tool_get_facility_info(args)
    if name == "ingest_observation":
        return await _tool_ingest_observation(args, ctx)
    return (
        f"Error: unknown tool '{name}'. Available tools: {', '.join(_TOOL_NAMES)}."
    )


_INVALID_JSON_NUDGE = (
    "That was not a valid JSON action. Reply with ONLY one JSON object: "
    '{"action":"tool","tool":"<name>","args":{...}} or '
    '{"action":"final","answer_es":"<answer in Spanish>"}.'
)


async def answer_question(
    client: QvacClient,
    message: str,
    *,
    intent: str,
    contributor: str,
    client_type: str | None = None,
    full_name: str | None = None,
    data_dir: str = "",
) -> AssistantResult:
    """Bounded tool loop for question/mixed intents.

    Returns the buffered SSE events (tool*, answer) plus the final Spanish
    answer. Model errors, invalid args and tool failures are re-injected as
    tool results so the model can correct itself; without a ``final`` after
    MAX_TOOL_ITERATIONS the answer is a Spanish apology.
    """
    ctx = SimpleNamespace(
        client=client,
        contributor=contributor,
        client_type=client_type,
        full_name=full_name,
        data_dir=data_dir,
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": TOOL_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    result = AssistantResult(answer=APOLOGY_ANSWER)
    replies: list[str] = []
    events: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            reply = await client.chat(messages, temperature=0.0, max_tokens=800)
        except Exception as exc:  # noqa: BLE001 - a dead model must not kill chat
            logger.warning("Tool loop: llamada al modelo falló: %s", exc)
            break
        if not reply:
            break
        replies.append(reply)
        data = parse_json_object(reply)

        if not isinstance(data, dict):
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": _INVALID_JSON_NUDGE})
            continue

        action = str(data.get("action", "")).strip().lower()
        if action == "final":
            answer = data.get("answer_es")
            if isinstance(answer, str) and answer.strip():
                result.answer = answer.strip()
            events.append({"type": "answer", "text": result.answer})
            result.events = events
            result.generated = "\n".join(replies)
            return result

        if action == "tool":
            name = str(data.get("tool", "")).strip()
            raw_args = data.get("args")
            args = raw_args if isinstance(raw_args, dict) else {}
            if name == "ingest_observation" and intent != INTENT_MIXED:
                tool_result = (
                    "Error: ingest_observation is only available when the user "
                    "message reports new field data. Answer with the information "
                    "you already have."
                )
            else:
                try:
                    tool_result = await _exec_tool(name, args, ctx)
                except Exception as exc:  # noqa: BLE001 - tool errors feed the model
                    logger.warning("Tool %s falló: %s", name, exc)
                    tool_result = (
                        f"Error executing {name}: {exc}. "
                        "Fix the arguments and try again."
                    )
            events.append({"type": "tool", "name": name})
            messages.append({"role": "assistant", "content": reply})
            # role "user" con prefijo explícito: el template de MedPsy solo
            # garantiza system/user/assistant, así que el resultado de la tool
            # se re-inyecta como mensaje de usuario etiquetado.
            messages.append(
                {"role": "user", "content": f"TOOL RESULT {name}:\n{_truncate(tool_result)}"}
            )
            continue

        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": _INVALID_JSON_NUDGE})

    result.events = [*events, {"type": "answer", "text": result.answer}]
    result.generated = "\n".join(replies)
    return result
