"""Facility, hierarchy and network-dump endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.graph import engine
from app.models import FacilityDetail, HierarchyResponse, NetworkResponse

logger = logging.getLogger("synapse.api.facilities")
router = APIRouter(tags=["facilities"])


@router.get("/api/facility/{facility_id}", response_model=FacilityDetail)
async def get_facility(facility_id: str) -> FacilityDetail:
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
async def get_hierarchy() -> HierarchyResponse:
    try:
        return HierarchyResponse(**await engine.get_hierarchy())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lectura de jerarquía falló: %s", exc)
        return HierarchyResponse(regions=[])


@router.get("/api/network", response_model=NetworkResponse)
async def get_network() -> NetworkResponse:
    try:
        return NetworkResponse(**await engine.get_network())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Volcado de red falló: %s", exc)
        return NetworkResponse(nodes=[], links=[])
