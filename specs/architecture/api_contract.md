# API Contract — Frontend ↔ Backend

> **Version:** 1.0
> **Date:** 2026-04-11
> **Assignee:** agente-claude (Research Agent)
> **Consumed by:** agente-codex — `backend/app/api/routes/`, `backend/app/api/models.py`, `frontend/index.html`
> **Companion documents:** [architecture.md](./architecture.md) · [requirements.md](../requirements/requirements.md)

---

## 1. Overview

The Lumen backend exposes a **FastAPI REST + SSE API** over HTTP. The frontend (`frontend/index.html`) communicates exclusively through this API — there is no shared state, no server-side rendering, and no WebSocket (SSE is used for streaming).

Base URL: `http://localhost:8000` (development) / configured via `frontend/config.js`

All request and response bodies use `Content-Type: application/json` except the SSE stream.

---

## 2. Endpoint Summary

| Method | Path | Description | Phase |
|---|---|---|---|
| `GET` | `/api/health` | Health and readiness check | Phase 1 |
| `POST` | `/api/chat` | Streamed persona response (SSE) | Phase 1 |
| `POST` | `/api/search` | Semantic corpus search | Phase 1 |

---

## 3. `GET /api/health`

### Request

No body. No query parameters.

### Response `200 OK`

```json
{
  "status": "ok",
  "model_loaded": true,
  "index_loaded": true,
  "persona_available": ["kardec"],
  "vram_used_mb": 4812,
  "vram_total_mb": 8192,
  "version": "1.0.0"
}
```

### Response Fields

| Field | Type | Description |
|---|---|---|
| `status` | `"ok" \| "degraded" \| "error"` | Overall readiness. `"degraded"` if model loaded but index missing. |
| `model_loaded` | `bool` | True if Gemma 4 E4B is fully loaded and ready. |
| `index_loaded` | `bool` | True if at least one FAISS index is available. |
| `persona_available` | `list[str]` | Persona IDs with both a system prompt and a loaded index. |
| `vram_used_mb` | `int \| null` | Current VRAM usage in MB. null if GPU metrics unavailable. |
| `vram_total_mb` | `int \| null` | Total VRAM of the primary GPU. null if GPU metrics unavailable. |
| `version` | `str` | API version string. |

### Error Response `503 Service Unavailable`

```json
{
  "status": "error",
  "detail": "Model not loaded — startup may still be in progress."
}
```

---

## 4. `POST /api/chat`

The primary endpoint. Sends a user message and streams back the persona response as Server-Sent Events.

### Request Body

```json
{
  "message": "O que é Deus segundo a doutrina espírita?",
  "persona_id": "kardec",
  "session_id": "sess_a1b2c3d4",
  "history": [
    {
      "role": "user",
      "content": "Boa tarde, Allan Kardec."
    },
    {
      "role": "assistant",
      "content": "Boa tarde. Em que posso ser-lhe útil?"
    }
  ],
  "options": {
    "max_new_tokens": 1024,
    "top_k_chunks": 5,
    "temperature": 0.7
  }
}
```

### Request Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `message` | `str` | Yes | — | The user's current message. Min 1 char, max 4096 chars. |
| `persona_id` | `str` | Yes | — | Persona to respond as. Must be in `health.persona_available`. |
| `session_id` | `str` | No | Auto-generated UUID | Identifies the session for KV cache persistence. |
| `history` | `list[Message]` | No | `[]` | Prior turns in the conversation. Used to build the prompt. Maximum 100 turns. |
| `options.max_new_tokens` | `int` | No | `1024` | Maximum tokens to generate. Range: 64–4096. |
| `options.top_k_chunks` | `int` | No | `5` | Number of RAG chunks to retrieve. Range: 1–20. |
| `options.temperature` | `float` | No | `0.7` | Sampling temperature. Range: 0.0–1.5. |

#### `Message` object

```json
{ "role": "user" | "assistant", "content": "..." }
```

### SSE Stream Response

The response uses `Content-Type: text/event-stream`. Tokens are emitted as they are generated. A final `[DONE]` event closes the stream.

#### Event types

| Event | When | `data` field |
|---|---|---|
| `token` | For each generated token | `{"token": "Deus"}` |
| `citations` | After generation completes | `{"citations": [...]}` |
| `stats` | After generation completes | `{"stats": {...}}` |
| `error` | If generation fails | `{"detail": "..."}` |
| `done` | End of stream | `"[DONE]"` |

#### Example SSE stream

```
event: token
data: {"token": "Deus"}

event: token
data: {"token": " é"}

event: token
data: {"token": " a"}

event: token
data: {"token": " inteligência"}

... (more tokens) ...

event: citations
data: {
  "citations": [
    {
      "id": "lde-q0001",
      "obra": "O Livro dos Espíritos",
      "parte": "Parte Primeira — Das Causas Primárias",
      "capitulo": "I — Deus",
      "questao": 1,
      "label": "L.E. Q.1",
      "score": 0.923,
      "excerpt": "Deus é a inteligência suprema, causa primária de todas as coisas."
    },
    {
      "id": "lde-q0003",
      "obra": "O Livro dos Espíritos",
      "parte": "Parte Primeira — Das Causas Primárias",
      "capitulo": "I — Deus",
      "questao": 3,
      "label": "L.E. Q.3",
      "score": 0.871,
      "excerpt": "Deus é infinito em suas perfeições."
    }
  ]
}

event: stats
data: {
  "stats": {
    "session_id": "sess_a1b2c3d4",
    "tokens_generated": 247,
    "tokens_per_second": 18.4,
    "kv_cache_tokens": 512,
    "kv_cache_mb": 6.2,
    "rag_latency_ms": 87,
    "generation_latency_ms": 13400
  }
}

event: done
data: [DONE]
```

### Citation Object Fields

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Chunk ID (e.g., `"lde-q0001"`) |
| `obra` | `str` | Full work title |
| `parte` | `str \| null` | Part/section heading |
| `capitulo` | `str \| null` | Chapter heading |
| `questao` | `int \| null` | Question number (null for narrative works) |
| `label` | `str` | Human-readable citation label (e.g., `"L.E. Q.1"`) |
| `score` | `float` | FAISS inner product similarity score (higher = more relevant) |
| `excerpt` | `str` | First 200 characters of the chunk text |

### Stats Object Fields

| Field | Type | Description |
|---|---|---|
| `session_id` | `str` | Session identifier |
| `tokens_generated` | `int` | Number of tokens generated in this turn |
| `tokens_per_second` | `float` | Generation throughput |
| `kv_cache_tokens` | `int` | Total tokens in the compressed KV cache after this turn |
| `kv_cache_mb` | `float` | KV cache memory usage in MB |
| `rag_latency_ms` | `int` | Time spent on FAISS retrieval (ms) |
| `generation_latency_ms` | `int` | Total generation wall time (ms) |

### Error Responses

**`400 Bad Request`** — invalid fields:
```json
{
  "detail": [
    {"loc": ["body", "message"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

**`404 Not Found`** — unknown persona:
```json
{
  "detail": "Persona 'unknown_persona' not found. Available: ['kardec']"
}
```

**`503 Service Unavailable`** — model not ready:
```json
{
  "detail": "Model is still loading. Retry after /api/health reports model_loaded=true."
}
```

---

## 5. `POST /api/search`

Semantic corpus search without persona generation. Used for direct passage retrieval.

### Request Body

```json
{
  "query": "Qual a condição das almas das crianças que morrem em tenra idade?",
  "persona_id": "kardec",
  "top_k": 10,
  "min_score": 0.5
}
```

### Request Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | `str` | Yes | — | The search query text. Min 1 char, max 2048 chars. |
| `persona_id` | `str` | Yes | — | Selects which corpus index to search. |
| `top_k` | `int` | No | `10` | Number of results to return. Range: 1–50. |
| `min_score` | `float` | No | `0.0` | Minimum similarity score to include in results. Range: 0.0–1.0. |

### Response `200 OK`

```json
{
  "query": "Qual a condição das almas das crianças que morrem em tenra idade?",
  "results": [
    {
      "id": "lde-q0197",
      "obra": "O Livro dos Espíritos",
      "parte": "Parte Segunda — Do Mundo Espírita",
      "capitulo": "IV — Pluralidade das Existências",
      "questao": 197,
      "label": "L.E. Q.197",
      "score": 0.912,
      "excerpt": "A criança que morre em tenra idade não teve tempo de praticar o mal...",
      "texto": "..."
    }
  ],
  "latency_ms": 43,
  "index_size": 1019
}
```

### Response Fields

| Field | Type | Description |
|---|---|---|
| `query` | `str` | The original query (echoed back for logging) |
| `results` | `list[SearchResult]` | Ranked list of matching chunks |
| `latency_ms` | `int` | FAISS search latency in milliseconds |
| `index_size` | `int` | Total number of chunks in the searched index |

#### `SearchResult` Object

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Chunk ID |
| `obra` | `str` | Full work title |
| `parte` | `str \| null` | Part/section heading |
| `capitulo` | `str \| null` | Chapter heading |
| `questao` | `int \| null` | Question number (null for narrative works) |
| `label` | `str` | Human-readable citation label |
| `score` | `float` | FAISS inner product similarity score |
| `excerpt` | `str` | First 200 characters of chunk text (preview) |
| `texto` | `str` | Full chunk text |

### Error Responses

Same pattern as `/api/chat`: `400` for validation errors, `404` for unknown persona, `503` if index not loaded.

---

## 6. Pydantic Models Reference

These schemas should be implemented in `backend/app/api/models.py`:

```python
from pydantic import BaseModel, Field
from typing import Literal

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
```

---

## 7. SSE Stream Implementation Notes

### 7.1 FastAPI SSE Pattern

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json

router = APIRouter()

@router.post("/chat")
async def chat(request: ChatRequest):
    async def generate_stream():
        # 1. Retrieve RAG chunks
        chunks = await retriever.retrieve(request.message, k=request.options.top_k_chunks)

        # 2. Build prompt
        system_prompt = build_system_prompt(request.persona_id, chunks)

        # 3. Stream tokens
        async for token in llm.stream(system_prompt, request.history, request.message):
            yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"

        # 4. Emit citations after generation completes
        citations = [chunk_to_citation(c) for c in chunks]
        yield f"event: citations\ndata: {json.dumps({'citations': [c.dict() for c in citations]})}\n\n"

        # 5. Emit stats
        stats = collect_stats(session_id, ...)
        yield f"event: stats\ndata: {json.dumps({'stats': stats.dict()})}\n\n"

        # 6. Done
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx buffering
        }
    )
```

### 7.2 Frontend EventSource Pattern

```javascript
// frontend/index.html (or a JS module)

async function sendMessage(message, personaId, sessionId, history) {
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            message,
            persona_id: personaId,
            session_id: sessionId,
            history
        })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullText = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop();  // keep incomplete line in buffer

        let eventType = null;
        for (const line of lines) {
            if (line.startsWith('event: ')) {
                eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
                const dataStr = line.slice(6).trim();
                if (dataStr === '[DONE]') {
                    onStreamComplete(fullText);
                    return;
                }
                const data = JSON.parse(dataStr);
                if (eventType === 'token') {
                    fullText += data.token;
                    onToken(data.token);        // append to UI
                } else if (eventType === 'citations') {
                    onCitations(data.citations); // render citation panel
                } else if (eventType === 'stats') {
                    onStats(data.stats);         // update stats display
                } else if (eventType === 'error') {
                    onError(data.detail);
                    return;
                }
                eventType = null;
            }
        }
    }
}
```

---

## 8. CORS Configuration

During development, the backend must allow cross-origin requests from the frontend dev server:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

In production (Docker Compose), the frontend is served by nginx on the same origin — CORS is not needed.

---

## 9. Session Management

Session IDs link requests to a persistent KV cache on the backend:

- If `session_id` is omitted, the backend generates a UUID v4 and returns it in the SSE `stats` event.
- The frontend must store the `session_id` and pass it in subsequent turns to maintain KV cache continuity.
- Sessions expire after **30 minutes of inactivity** (configurable via `SESSION_TIMEOUT_SECONDS` env var).
- Maximum concurrent sessions: limited by available VRAM (1 session ≈ 3–6 GB KV cache at 128K tokens).

---

## 10. API Version and Stability

- All endpoints are prefixed `/api/` and versioned implicitly by the server version.
- Breaking changes will bump the server version and be documented here.
- The `/api/health` endpoint is guaranteed stable across versions.

---

## 11. References

| Document | Link |
|---|---|
| Architecture | [architecture.md](./architecture.md) |
| Requirements | [requirements.md](../requirements/requirements.md) |
| FastAPI docs | https://fastapi.tiangolo.com/tutorial/bigger-applications/ |
| SSE specification | https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events |
| Pydantic v2 docs | https://docs.pydantic.dev/latest/ |
