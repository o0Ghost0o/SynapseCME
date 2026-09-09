"""GET /api/metrics — latest inference perf rows."""

from __future__ import annotations

from fastapi import APIRouter

from app import db
from app.models import MetricsResponse, PerfEntry

router = APIRouter(tags=["metrics"])


@router.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics() -> MetricsResponse:
    rows = await db.recent_perf(limit=100)
    return MetricsResponse(entries=[PerfEntry(**r) for r in rows])
