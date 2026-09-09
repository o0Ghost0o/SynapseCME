"""GET /api/metrics — latest inference perf rows (viewer role and above)."""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends

from app import db
from app.auth.deps import require_viewer
from app.models import MetricsResponse, PerfEntry

router = APIRouter(tags=["metrics"])


@router.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics(user: dict[str, Any] = Depends(require_viewer)) -> MetricsResponse:
    rows = await db.recent_perf(limit=100)
    return MetricsResponse(entries=[PerfEntry(**r) for r in rows])
