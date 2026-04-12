"""
Pydantic request / response models for the Lumen API.
Spec: specs/architecture/api_contract.md §6
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatOptions(BaseModel):
    max_new_tokens: int = Field(1024, ge=64, le=4096)
    top_k_chunks: int = Field(5, ge=1, le=20)
    temperature: float = Field(0.7, ge=0.0, le=1.5)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)
    persona_id: str
    session_id: str | None = None
    history: list[Message] = Field(default_factory=list, max_length=100)
    options: ChatOptions = Field(default_factory=ChatOptions)


class Citation(BaseModel):
    id: str
    obra: str
    parte: str | None
    capitulo: str | None
    questao: int | None
    label: str
    score: float
    excerpt: str


class GenerationStats(BaseModel):
    session_id: str
    tokens_generated: int
    tokens_per_second: float
    kv_cache_tokens: int
    kv_cache_mb: float
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
    model_loaded: bool
    index_loaded: bool
    persona_available: list[str]
    vram_used_mb: int | None
    vram_total_mb: int | None
    version: str
