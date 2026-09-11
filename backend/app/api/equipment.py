"""Equipment detail and flat filtered listing endpoints (viewer role and above)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.agent import service
from app.auth.deps import require_capturer, require_viewer
from app.graph import engine
from app.models import (
    EquipmentChatRequest,
    EquipmentDetail,
    EquipmentListResponse,
    EquipmentPatchRequest,
)

logger = logging.getLogger("synapse.api.equipment")
router = APIRouter(tags=["equipment"])


def _graph_or_503() -> None:
    if engine.driver() is None:
        raise HTTPException(status_code=503, detail="Grafo no disponible")


@router.get("/api/equipment/{equipment_id}", response_model=EquipmentDetail)
async def get_equipment(
    equipment_id: str, user: dict[str, Any] = Depends(require_viewer)
) -> EquipmentDetail:
    _graph_or_503()
    try:
        detail = await engine.get_equipment_detail(equipment_id)
    except Exception as exc:  # noqa: BLE001 - Neo4j down mid-request
        logger.warning("Lectura de equipo falló: %s", exc)
        raise HTTPException(status_code=503, detail="Grafo no disponible") from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return EquipmentDetail(**detail)


@router.patch("/api/equipment/{equipment_id}", response_model=EquipmentDetail)
async def patch_equipment(
    equipment_id: str,
    patch: EquipmentPatchRequest,
    user: dict[str, Any] = Depends(require_capturer),
) -> EquipmentDetail:
    """Actualización manual directa de campos y/o parámetros técnicos de un equipo."""
    _graph_or_503()
    try:
        detail = await engine.patch_equipment(
            equipment_id,
            patch,
            contributor=user["username"],
            client_type="field_app",
            full_name=user.get("full_name"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Actualización manual de equipo falló: %s", exc)
        raise HTTPException(status_code=503, detail="Grafo no disponible") from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return EquipmentDetail(**detail)


@router.post("/api/equipment/{equipment_id}/chat")
async def equipment_chat(
    equipment_id: str,
    request: EquipmentChatRequest,
    user: dict[str, Any] = Depends(require_capturer),
) -> StreamingResponse:
    """Mini-chat de revisión anclado al equipo (mismo contrato SSE que /api/chat)."""
    _graph_or_503()
    try:
        ctx = await engine.get_equipment_context(equipment_id)
    except Exception as exc:  # noqa: BLE001 - Neo4j down mid-request
        logger.warning("Contexto de equipo falló: %s", exc)
        raise HTTPException(status_code=503, detail="Grafo no disponible") from exc
    if ctx is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    kwargs: dict[str, Any] = {}
    if request.client_timestamp is not None:
        kwargs["client_timestamp"] = request.client_timestamp
    if request.client_timezone is not None:
        kwargs["client_timezone"] = request.client_timezone
    return StreamingResponse(
        service.handle_equipment_chat(
            request.message,
            equipment_id,
            user,
            request.client_type,
            **kwargs,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/equipments", response_model=EquipmentListResponse)
async def list_equipments(
    modality: str | None = Query(default=None),
    manufacturer: str | None = Query(default=None),
    state: str | None = Query(default=None),
    country: str | None = Query(default=None),
    facility: str | None = Query(default=None),
    q: str | None = Query(default=None),
    has_issue: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(require_viewer),
) -> EquipmentListResponse:
    _graph_or_503()
    try:
        result = await engine.list_equipments(
            modality=modality,
            manufacturer=manufacturer,
            state=state,
            country=country,
            facility=facility,
            q=q,
            has_issue=has_issue,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:  # noqa: BLE001 - Neo4j down mid-request
        logger.warning("Listado de equipos falló: %s", exc)
        raise HTTPException(status_code=503, detail="Grafo no disponible") from exc
    return EquipmentListResponse(**result)
