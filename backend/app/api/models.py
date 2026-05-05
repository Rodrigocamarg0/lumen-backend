"""
Pydantic request / response models for the Lumen API.
Spec: specs/architecture/api_contract.md §6
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    id: str
    obra: str
    parte: str | None
    capitulo: str | None
    questao: int | None
    label: str
    score: float
    excerpt: str


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)
    citations: list[Citation] | list[dict] | None = None


class ChatOptions(BaseModel):
    max_new_tokens: int = Field(1024, ge=64, le=4096)
    top_k_chunks: int = Field(10, ge=1, le=20)
    temperature: float = Field(0.7, ge=0.0, le=1.5)
    reasoning_effort: Literal["off", "low", "medium", "high", "xhigh"] = "off"
    answer_mode: Literal[
        "default",
        "concise",
        "scholarly",
        "pastoral",
        "socratic",
        "citation_heavy",
    ] = "default"
    study_goal: str | None = Field(default=None, max_length=500)
    incognito: bool = False


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)
    persona_id: str
    session_id: str | None = None
    history: list[Message] = Field(default_factory=list, max_length=100)
    options: ChatOptions = Field(default_factory=ChatOptions)


class GenerationStats(BaseModel):
    session_id: str
    tokens_generated: int
    tokens_per_second: float
    rag_latency_ms: int
    generation_latency_ms: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048)
    persona_id: str
    top_k: int = Field(10, ge=1, le=50)
    min_score: float = Field(0.0, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    id: str
    obra: str
    parte: str | None
    capitulo: str | None
    questao: int | None
    label: str
    score: float
    excerpt: str
    texto: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    latency_ms: int
    index_size: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    llm_provider: str
    model_loaded: bool
    index_loaded: bool
    persona_available: list[str]
    vram_used_mb: int | None
    vram_total_mb: int | None
    version: str


class PersonaResponse(BaseModel):
    id: str
    name: str
    subtitle: str
    description: str


# ---------------------------------------------------------------------------
# Session models (Phase 2 — Agno persistent history)
# ---------------------------------------------------------------------------


class SessionSummary(BaseModel):
    session_id: str
    persona_id: str
    created_at: int
    updated_at: int
    turn_count: int
    preview: str
    title: str | None = None
    status: str = "active"

    @classmethod
    def from_agno(cls, session: object, persona_id: str) -> SessionSummary:
        turn_count = 0
        last_user = ""
        for run in getattr(session, "runs", None) or []:
            for msg in getattr(run, "messages", None) or []:
                if getattr(msg, "role", None) == "user":
                    last_user = (getattr(msg, "content", "") or "")[:120]
                    turn_count += 1
        return cls(
            session_id=getattr(session, "session_id", ""),
            persona_id=persona_id,
            created_at=getattr(session, "created_at", 0) or 0,
            updated_at=getattr(session, "updated_at", 0) or 0,
            turn_count=turn_count,
            preview=last_user,
        )


class SessionDetail(BaseModel):
    session_id: str
    persona_id: str
    turns: list[Message]


class UserMemoryResponse(BaseModel):
    id: str
    persona_id: str
    memory: str
    topics: list[str] = Field(default_factory=list)
    confidence: float
    source_session_id: str | None
    created_at: int
    updated_at: int


class AdminMetricPoint(BaseModel):
    date: str
    users: int = 0
    sessions: int = 0
    runs: int = 0
    avg_tokens_per_second: float | None = None
    avg_generation_latency_ms: float | None = None


class AdminStatsResponse(BaseModel):
    total_users: int
    daily_active_users: int
    weekly_active_users: int
    monthly_active_users: int
    total_sessions: int
    active_sessions: int
    concurrent_sessions: int
    total_interactions: int
    terms_acceptances: int
    avg_tokens_per_second: float | None
    avg_rag_latency_ms: float | None
    avg_generation_latency_ms: float | None
    series: list[AdminMetricPoint]


class AdminTraceMessage(BaseModel):
    role: str
    content: str
    citations: list | dict | None = None


class AdminTrace(BaseModel):
    id: str
    session_id: str
    user_id: str
    persona_id: str
    model_provider: str
    model_id: str
    status: str
    error_detail: str | None
    tokens_generated: int | None
    tokens_per_second: float | None
    rag_latency_ms: int | None
    generation_latency_ms: int | None
    created_at: int
    completed_at: int
    messages: list[AdminTraceMessage] = Field(default_factory=list)


class AdminTracesResponse(BaseModel):
    items: list[AdminTrace]
    limit: int
    offset: int
    total: int


class PersonaConfigResponse(BaseModel):
    persona_id: str
    system_prompt: str
    few_shot_examples: list[dict]
    updated_at: int
    updated_by: str | None = None


class PersonaConfigUpdate(BaseModel):
    system_prompt: str = Field(..., min_length=1)
    few_shot_examples: list[dict] = Field(default_factory=list)
