"""Shared Pydantic models: extraction contract + API request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EquipmentItem(BaseModel):
    modality: str
    manufacturer: str | None = None
    model: str | None = None
    quantity: int = 1
    age_years: float | None = None
    confidence: float = 0.5


class ExtractionResult(BaseModel):
    facility: str | None = None
    city: str | None = None
    country: str | None = None
    items: list[EquipmentItem] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    raw: str | None = None
    extractor: str = "rule"
    followup: str | None = None


class ChatRequest(BaseModel):
    message: str
    contributor: str | None = None
    client_type: str | None = None


class IngestResult(BaseModel):
    facility_created: bool = False
    facility_id: str | None = None
    equipment_ids: list[str] = Field(default_factory=list)
    transaction_ids: list[int] = Field(default_factory=list)
    mutation_summary: str = ""


class HealthResponse(BaseModel):
    status: str
    models: list[str] = Field(default_factory=list)
    qvac: str = "down"


class TransactionEntry(BaseModel):
    id: int
    actor: str
    client_type: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    state_transition: str | None = None
    created_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TransactionsResponse(BaseModel):
    entries: list[TransactionEntry]


class PerfEntry(BaseModel):
    model: str
    model_load_ms: int | None = None
    prompt_tokens: int | None = None
    generation_tokens: int | None = None
    ttft_ms: int | None = None
    total_ms: int | None = None
    throughput_tps: float | None = None
    created_at: str | None = None


class MetricsResponse(BaseModel):
    entries: list[PerfEntry]


class FacilityDetail(BaseModel):
    facility: dict[str, Any]
    equipment: list[dict[str, Any]]


class HierarchyResponse(BaseModel):
    regions: list[dict[str, Any]]


class NetworkResponse(BaseModel):
    nodes: list[dict[str, Any]]
    links: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=128)
    role: Literal["admin", "capturer", "viewer"]


class UserOut(BaseModel):
    username: str
    full_name: str
    role: Literal["admin", "capturer", "viewer"]
    disabled: bool | None = None
    created_at: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UsersResponse(BaseModel):
    entries: list[UserOut]
