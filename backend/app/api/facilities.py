"""Facility, hierarchy and network-dump endpoints (viewer role and above)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.agent.qvac import QvacClient
from app.auth.deps import require_viewer
from app.core.config import settings
from app.graph import engine
from app.models import (
    CoreModelEntry,
    CoreNodeResponse,
    FacilityDetail,
    HierarchyResponse,
    NetworkResponse,
)

logger = logging.getLogger("synapse.api.facilities")
router = APIRouter(tags=["facilities"])


@router.get("/api/facility/{facility_id}", response_model=FacilityDetail)
async def get_facility(
    facility_id: str, user: dict[str, Any] = Depends(require_viewer)
) -> FacilityDetail:
    if engine.driver() is None:
        raise HTTPException(status_code=503, detail="Grafo no disponible")
    try:
        detail = await engine.get_facility_detail(facility_id)
    except Exception as exc:  # noqa: BLE001 - Neo4j down mid-request
        logger.warning("Lectura de facilidad falló: %s", exc)
        raise HTTPException(status_code=503, detail="Grafo no disponible") from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Facilidad no encontrada")
    return FacilityDetail(**detail)


@router.get("/api/hierarchy", response_model=HierarchyResponse)
async def get_hierarchy(user: dict[str, Any] = Depends(require_viewer)) -> HierarchyResponse:
    try:
        return HierarchyResponse(**await engine.get_hierarchy())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lectura de jerarquía falló: %s", exc)
        return HierarchyResponse(regions=[])


@router.get("/api/network", response_model=NetworkResponse)
async def get_network(user: dict[str, Any] = Depends(require_viewer)) -> NetworkResponse:
    try:
        return NetworkResponse(**await engine.get_network())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Volcado de red falló: %s", exc)
        return NetworkResponse(nodes=[], links=[])


@router.get("/api/network/core", response_model=CoreNodeResponse)
async def get_core_node(
    user: dict[str, Any] = Depends(require_viewer),
) -> CoreNodeResponse:
    """Qué está corriendo el nodo principal (núcleo + inferencia QVAC + STT)."""
    qvac = QvacClient(
        base_url=settings.qvac_base_url,
        model=settings.medpsy_model,
        embed_model=settings.embed_model,
        timeout=5.0,
    )
    try:
        models = await qvac.list_model_info()
    finally:
        await qvac.aclose()
    stt_up = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(settings.stt_base_url)
            stt_up = resp.status_code < 500
    except Exception:  # noqa: BLE001 - STT caído o inalcanzable
        stt_up = False
    try:
        counts = await engine.label_counts()
    except Exception as exc:  # noqa: BLE001 - Neo4j caído
        logger.warning("Conteo de etiquetas falló: %s", exc)
        counts = {}
    return CoreNodeResponse(
        name="Synapse Core",
        qvac_up=bool(models),
        qvac_url=settings.qvac_base_url,
        models=[CoreModelEntry(**m) for m in models],
        chat_model=settings.medpsy_model,
        embed_model=settings.embed_model,
        stt_model=settings.stt_model,
        stt_up=stt_up,
        graph_counts=counts,
    )
