"""Shared Pydantic models: extraction contract + API request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ParameterStatus = Literal["ok", "warning", "critical"]


class ParameterExtraction(BaseModel):
    name: str
    value: float | str | None = None
    unit: str | None = None
    status: ParameterStatus | None = None


class EquipmentItem(BaseModel):
    modality: str
    manufacturer: str | None = None
    model: str | None = None
    quantity: int = 1
    age_years: float | None = None
    confidence: float = 0.5
    parameters: list[ParameterExtraction] = Field(default_factory=list)


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
    # Optional anchor to an existing conversation (validated server-side:
    # it must exist and belong to the caller). Missing -> new conversation.
    conversation_id: str | None = None


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


class Parameter(BaseModel):
    id: str
    name: str
    value: float | str | None = None
    unit: str | None = None
    status: ParameterStatus | None = None
    source_observation_id: str
    created_at: str | None = None


class EquipmentDetail(BaseModel):
    equipment: dict[str, Any]
    observations: list[dict[str, Any]] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    parameter_history: list[Parameter] = Field(default_factory=list)


class EquipmentListItem(BaseModel):
    id: str
    modality: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    quantity: int | None = None
    age_years: float | None = None
    state: str | None = None
    facility_id: str | None = None
    facility_name: str | None = None
    city: str | None = None
    country: str | None = None
    has_issue: bool = False


class EquipmentListResponse(BaseModel):
    total: int
    items: list[EquipmentListItem] = Field(default_factory=list)
    limit: int = 100
    offset: int = 0


class HierarchyResponse(BaseModel):
    regions: list[dict[str, Any]]


class NetworkResponse(BaseModel):
    nodes: list[dict[str, Any]]
    links: list[dict[str, Any]]


class CoreModelEntry(BaseModel):
    id: str
    state: str | None = None


class CoreNodeResponse(BaseModel):
    """Estado del nodo principal: qué está corriendo el núcleo SynapseCME."""

    name: str
    qvac_up: bool
    qvac_url: str
    models: list[CoreModelEntry]
    chat_model: str
    embed_model: str
    stt_model: str
    stt_up: bool
    graph_counts: dict[str, int]


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
