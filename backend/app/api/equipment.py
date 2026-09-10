"""Equipment detail and flat filtered listing endpoints (viewer role and above)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require_viewer
from app.graph import engine
from app.models import EquipmentDetail, EquipmentListResponse

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
