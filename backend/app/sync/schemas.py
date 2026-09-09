"""Pydantic schemas for node-to-node observation sync.

Local to this package on purpose: app/models/ is shared with another branch.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.models import ExtractionResult


class SyncPayload(BaseModel):
    node_id: str
    contributor: str
    client_type: str | None = None
    extraction: ExtractionResult


class SyncAck(BaseModel):
    ignored: bool
    facility_id: str | None = None
    transactions: int = 0
