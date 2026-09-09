"""Transaction log endpoints: JSON list + CSV export."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app import db
from app.models import TransactionEntry, TransactionsResponse

router = APIRouter(tags=["transactions"])

CSV_COLUMNS = [
    "id", "actor", "client_type", "action", "target_type",
    "target_id", "target_name", "state_transition", "created_at", "payload",
]


@router.get("/api/transactions", response_model=TransactionsResponse)
async def get_transactions(
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> TransactionsResponse:
    rows = await db.recent_transactions(action=action, limit=limit)
    return TransactionsResponse(entries=[TransactionEntry(**r) for r in rows])


@router.get("/api/transactions/export.csv")
async def export_transactions_csv() -> StreamingResponse:
    rows = await db.all_transactions_for_export()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        row = dict(row)
        import json

        row["payload"] = json.dumps(row.get("payload") or {}, ensure_ascii=False)
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )
