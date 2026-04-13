# Phase 2 — Agno Chat: Persistent History + Persona Agents

> **Goal:** Replace the current in-memory session store with Agno SDK-backed PostgreSQL session
> storage. Each writer/persona is modelled as an Agno `Agent` that owns its identity and session
> history. The existing RAG pipeline (`persona/rag.py`, FAISS, embeddings) is **unchanged** —
> Agno is responsible for session persistence and history retrieval only; generation still flows
> through `rag.astream_response()`. The frontend gains a session sidebar with full chat history.

---

## Architecture Overview

```
Frontend (React)
    │
    │  POST /api/chat       (SSE stream)
    │  GET  /api/sessions
    │  GET  /api/sessions/{id}
    │  DELETE /api/sessions/{id}
    ▼
FastAPI (backend)
    │
    ├─ agents/registry.py
    │       KardecAgent  (agno.Agent — identity + DB only, no agent.run())
    │       FutureAgent  (add more writers here)
    │       get_agent(persona_id) → Agent
    │
    ├─ agents/sessions.py
    │       load_history(agent, session_id)    → list[dict]  (feed into RAG)
    │       save_turn(agent, session_id, ...)  → persist run to Postgres
    │
    ├─ PostgresDb  (lumen_sessions table, auto-created by Agno on first use)
    │
    └─ persona/rag.py  ←  COMPLETELY UNCHANGED
            astream_response(persona_id, message, history, ...)
```

### Flow per request

```
POST /api/chat
  1. get_agent(persona_id)                         → KardecAgent
  2. load_history(agent, session_id, max_turns=10) → list[{"role","content"}]
  3. rag.astream_response(..., history=history)    → stream tokens + citations (RAG unchanged)
  4. buffer assistant tokens during stream
  5. save_turn(agent, session_id, user_msg, full_assistant_response)
  6. yield SSE events to client
```

### Key design decisions

| Decision | Choice | Reason |
|---|---|---|
| RAG pipeline | **Untouched** | `rag.py` + FAISS stays exactly as-is |
| Agno role | Session storage + persona identity only | No `agent.run()` call; generation is RAG's job |
| `model=` on Agent | Required by Agno constructor — set but never called | Set to configured OpenAI model or `OpenAILike`; never triggered |
| `add_datetime_to_context` | **False** (leave at default) | Known Agno bug: datetime serialization error with PostgresDb |
| Storage backend | PostgreSQL via `PostgresDb` | Single image serves sessions + future pgvector use |
| History loading | `agent.get_chat_history(session_id, last_n_runs=10)` | Official API — returns `List[Message]` user+assistant only |
| History saving | Build `RunOutput` → `session.upsert_run()` → `agent.asave_session()` | Official low-level API; no LLM call triggered |
| Session listing | `agent.db.get_all_sessions(agent_id=...)` | Confirmed available on PostgresDb |

---

## Confirmed Agno APIs Used

All APIs verified against official docs (`docs.agno.com`) and source inspection.

```python
# Read
agent.get_session(session_id: str) -> Optional[AgentSession]
agent.get_chat_history(session_id: str, last_n_runs: int) -> List[Message]
  # Message.role: "user" | "assistant" | "system" | "tool"
  # Message.content: str

# Write (no LLM call, pure storage)
AgentSession.upsert_run(run: RunOutput)     # add/update run in session
agent.save_session(session: AgentSession)   # sync persist
agent.asave_session(session: AgentSession)  # async persist  ← use this in FastAPI

# Session management
agent.delete_session(session_id: str)
agent.db.get_all_sessions(agent_id: str)    # list all sessions for an agent

# RunOutput constructor (minimal)
RunOutput(
    run_id=str,           # uuid
    agent_id=str,
    session_id=str,
    messages=List[Message],
    content=str,          # final assistant text
    status=RunStatus.completed,
    created_at=int,       # unix timestamp
)
```

---

## Task Breakdown

---

### Task 2.1 — Infrastructure: PostgreSQL in Docker Compose
**Path:** `docker/docker-compose.yml`
**Size:** Small

Add a `postgres` service and wire it to the backend:

```yaml
services:
  postgres:
    image: agnohq/pgvector:16
    environment:
      POSTGRES_DB: ai
      POSTGRES_USER: ai
      POSTGRES_PASSWORD: ai
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5532:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ai -d ai"]
      interval: 10s
      retries: 5

  backend:
    # existing config...
    environment:
      - DATABASE_URL=postgresql+psycopg://ai:ai@postgres:5432/ai
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
  model-cache:  # existing
```

**Done when:** `docker compose up postgres` is healthy; `psql` connects.

---

### Task 2.2 — Backend: Add Agno + DB Dependencies
**Path:** `backend/requirements.txt`

```
agno>=1.7
sqlalchemy>=2.0
psycopg[binary]>=3.1
```

**Done when:** `pip install -r requirements.txt` succeeds; `python -c "import agno"` works.

---

### Task 2.3 — Backend: `config.py` — Add DATABASE_URL
**Path:** `backend/app/config.py`

Add to `Settings`:
```python
DATABASE_URL: str = "postgresql+psycopg://ai:ai@localhost:5532/ai"
```

**Done when:** `settings.DATABASE_URL` accessible everywhere.

---

### Task 2.4 — Backend: Agno Agent Definitions
**Path:** `backend/app/agents/` (new directory)

```
backend/app/agents/
├── __init__.py
├── db.py          ← PostgresDb singleton
├── kardec.py      ← KardecAgent
└── registry.py    ← get_agent() / build_registry()
```

#### `db.py`
```python
from agno.db.postgres import PostgresDb
from app.config import settings

_db: PostgresDb | None = None

def get_db() -> PostgresDb:
    global _db
    if _db is None:
        _db = PostgresDb(
            db_url=settings.DATABASE_URL,
            session_table="lumen_sessions",
        )
    return _db
```

#### `kardec.py`
```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.openai.like import OpenAILike
from app.agents.db import get_db
from app.config import settings
from app.persona.prompts import get_prompt

def make_kardec_agent() -> Agent:
    # model= is required by Agno but never called for inference here —
    # generation happens in rag.astream_response().
    model = (
        OpenAIChat(id=settings.OPENAI_MODEL)
        if settings.LLM_PROVIDER == "openai"
        else OpenAILike(
            id=settings.MODEL_ID,
            base_url="http://localhost:8000/v1",
            api_key="local",
        )
    )
    return Agent(
        name="kardec",
        agent_id="kardec",
        model=model,
        description="Allan Kardec — codificador da Doutrina Espírita",
        instructions=get_prompt("kardec"),
        db=get_db(),
        add_history_to_context=False,   # we inject history manually into RAG
        add_datetime_to_context=False,  # avoid known Postgres datetime serialization bug
    )
```

#### `registry.py`
```python
from agno.agent import Agent
from app.agents.kardec import make_kardec_agent

_registry: dict[str, Agent] = {}

def build_registry() -> None:
    """Call once at app startup after RAG and model are ready."""
    _registry["kardec"] = make_kardec_agent()

def get_agent(persona_id: str) -> Agent:
    if persona_id not in _registry:
        raise KeyError(f"Unknown persona: {persona_id!r}")
    return _registry[persona_id]

def list_persona_ids() -> list[str]:
    return list(_registry.keys())
```

**Done when:** `build_registry()` runs without error; `get_agent("kardec")` returns an Agent.

---

### Task 2.5 — Backend: Session Helpers (Load / Save)
**Path:** `backend/app/agents/sessions.py` (new)

```python
from __future__ import annotations

import time
import uuid

from agno.agent import Agent
from agno.agent.session import AgentSession
from agno.models.message import Message
from agno.run.response import RunOutput, RunStatus


def load_history(
    agent: Agent,
    session_id: str,
    max_turns: int = 10,
) -> list[dict[str, str]]:
    """
    Load the last `max_turns` user+assistant exchanges from Agno's PostgresDB.
    Returns dicts compatible with rag.astream_response(history=...).
    """
    messages: list[Message] = agent.get_chat_history(
        session_id=session_id,
        last_n_runs=max_turns,
    )
    return [
        {"role": m.role, "content": m.content}
        for m in messages
        if m.role in ("user", "assistant") and m.content
    ]


async def save_turn(
    agent: Agent,
    session_id: str,
    user_message: str,
    assistant_content: str,
) -> None:
    """
    Persist one completed user→assistant exchange to Agno's PostgresDB.
    Builds a RunOutput directly — no LLM call is triggered.
    """
    session: AgentSession | None = agent.get_session(session_id=session_id)
    if session is None:
        session = AgentSession(
            session_id=session_id,
            agent_id=agent.agent_id,
            agent_data={"agent_id": agent.agent_id, "name": agent.name},
        )

    run = RunOutput(
        run_id=str(uuid.uuid4()),
        agent_id=agent.agent_id,
        session_id=session_id,
        messages=[
            Message(role="user", content=user_message),
            Message(role="assistant", content=assistant_content),
        ],
        content=assistant_content,
        status=RunStatus.completed,
        created_at=int(time.time()),
    )
    session.upsert_run(run)
    await agent.asave_session(session)
```

**Done when:** `load_history` returns correct turns; `save_turn` round-trips through a real DB row.

---

### Task 2.6 — Backend: App State + Startup
**Path:** `backend/app/main.py`

In the lifespan, after existing startup (model load + RAG index):
```python
from app.agents.registry import build_registry
build_registry()
logger.info("[agents] registry built")
```

Update `chat.py`'s `_VALID_PERSONAS` to use `list_persona_ids()` instead of the hardcoded set.

**Done when:** `GET /api/health` still returns 200; startup log shows `[agents] registry built`.

---

### Task 2.7 — Backend: Update Chat Route
**Path:** `backend/app/api/routes/chat.py`

Replace manual history tracking with Agno load/save. `rag.astream_response()` signature is **unchanged**.

```python
import asyncio
import uuid

from app.agents.registry import get_agent, list_persona_ids
from app.agents.sessions import load_history, save_turn

_VALID_PERSONAS = None  # resolved lazily from registry

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    from app.agents.registry import list_persona_ids
    if request.persona_id not in list_persona_ids():
        raise HTTPException(status_code=404, detail=f"Persona '{request.persona_id}' not found.")

    # ... existing model/index checks ...

    agent = get_agent(request.persona_id)
    sid = request.session_id or str(uuid.uuid4())
    history = load_history(agent, sid, max_turns=10)

    assistant_buffer: list[str] = []

    async def generate_stream():
        async for event_type, payload in state.rag.astream_response(
            persona_id=request.persona_id,
            message=request.message,
            session_id=sid,
            history=history,           # ← from Agno/Postgres (replaces in-memory dict)
            max_new_tokens=request.options.max_new_tokens,
            top_k_chunks=request.options.top_k_chunks,
            temperature=request.options.temperature,
        ):
            if event_type == "token":
                assistant_buffer.append(payload)
                yield f"event: token\ndata: {json.dumps({'token': payload})}\n\n"
            elif event_type == "citations":
                yield f"event: citations\ndata: {json.dumps({'citations': payload})}\n\n"
            elif event_type == "stats":
                yield f"event: stats\ndata: {json.dumps({'stats': payload})}\n\n"
            elif event_type == "error":
                yield f"event: error\ndata: {json.dumps({'detail': payload})}\n\n"
                return
            elif event_type == "done":
                # persist after stream is complete
                await save_turn(agent, sid, request.message, "".join(assistant_buffer))
                yield "event: done\ndata: [DONE]\n\n"
        ...

    return StreamingResponse(generate_stream(), media_type="text/event-stream", ...)
```

After this lands, remove the `_sessions: dict[str, dict]` from `rag.py` — it is dead code.

**Done when:** Two-turn `curl` conversation shows turn 2 has context from turn 1; `lumen_sessions` row exists in Postgres.

---

### Task 2.8 — Backend: Session Management API
**Path:** `backend/app/api/routes/sessions.py` (new)

```python
from fastapi import APIRouter, HTTPException
from app.agents.registry import get_agent, list_persona_ids
from app.api.models import SessionSummary, SessionDetail, Message

router = APIRouter()

@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(persona_id: str | None = None):
    ids = [persona_id] if persona_id else list_persona_ids()
    results = []
    for pid in ids:
        agent = get_agent(pid)
        for session in agent.db.get_all_sessions(agent_id=pid):
            results.append(SessionSummary.from_agno(session, pid))
    return results

@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str):
    # try each agent until we find the session
    for pid in list_persona_ids():
        agent = get_agent(pid)
        session = agent.get_session(session_id=session_id)
        if session:
            turns = [
                Message(role=m.role, content=m.content)
                for m in session.get_chat_history()
                if m.role in ("user", "assistant")
            ]
            return SessionDetail(session_id=session_id, persona_id=pid, turns=turns)
    raise HTTPException(status_code=404, detail="Session not found")

@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    for pid in list_persona_ids():
        agent = get_agent(pid)
        if agent.get_session(session_id=session_id):
            agent.delete_session(session_id=session_id)
            return
    raise HTTPException(status_code=404, detail="Session not found")
```

Register router in `main.py`: `app.include_router(sessions_router, prefix="/api")`.

**Done when:** Postman/curl: sessions survive a server restart; DELETE removes the row.

---

### Task 2.9 — Backend: Pydantic Model Updates
**Path:** `backend/app/api/models.py`

Add:
```python
class SessionSummary(BaseModel):
    session_id: str
    persona_id: str
    created_at: int
    updated_at: int
    turn_count: int
    preview: str   # first 120 chars of last user message

    @classmethod
    def from_agno(cls, session: "AgentSession", persona_id: str) -> "SessionSummary":
        last_user = ""
        turn_count = 0
        for run in (session.runs or []):
            for msg in (run.messages or []):
                if msg.role == "user":
                    last_user = (msg.content or "")[:120]
                    turn_count += 1
        return cls(
            session_id=session.session_id,
            persona_id=persona_id,
            created_at=session.created_at or 0,
            updated_at=session.updated_at or 0,
            turn_count=turn_count,
            preview=last_user,
        )

class SessionDetail(BaseModel):
    session_id: str
    persona_id: str
    turns: list[Message]
```

**Done when:** `pyright` passes with zero errors on all modified files.

---

### Task 2.10 — Frontend: Session Sidebar
**Path:** `frontend/src/components/SessionSidebar.jsx` (new)
**Size:** Medium

**What to build:**
- Collapsible left sidebar listing past sessions grouped by persona.
- Each item shows: persona name, relative date, last message preview.
- Click → `GET /api/sessions/{id}` → load turns into chat view.
- "New Chat" button → generate fresh UUID, clear chat.
- Trash icon → `DELETE /api/sessions/{id}` → remove from list.

**Hooks:**
- `useSessions(personaId)` — `GET /api/sessions?persona_id=...`, refetch after each completed turn.
- `useCurrentSession()` — holds `session_id`, persisted in `localStorage`.
- On load: restore `session_id` from `localStorage`, else generate new UUID.

**Done when:** Refreshing the page restores the last conversation; sidebar lists all sessions.

---

### Task 2.11 — Frontend: Update Chat Message Flow
**Path:** `frontend/src/hooks/useChat.js` (or equivalent)
**Size:** Small

**Changes:**
- Remove client-side `history` array from the request body (Agno owns history server-side).
- Send `session_id` (from `useCurrentSession`) in every `POST /api/chat` request.
- After receiving the `done` SSE event, call `useSessions` refetch.

**Done when:** Multi-turn chat works end-to-end without any history sent from the client.

---

### Task 2.12 — Docker: Full Stack Integration Test
**Path:** `docker/docker-compose.yml` (already updated in 2.1)

- Smoke test: `docker compose up` → chat two turns → `docker compose restart backend` → session still in sidebar, history intact.
- Confirm `lumen_sessions` table auto-created by Agno on first request.

**Done when:** Full stack passes smoke test via Docker.

---

## Phase Gate

**Phase 2 is complete when ALL of the following pass:**

- [ ] Multi-turn conversation: turn 2 has context from turn 1 (history loaded from Postgres)
- [ ] Server restart: session history survives (Postgres persistence confirmed)
- [ ] `GET /api/sessions` returns all past sessions
- [ ] Session restore: clicking a session in the sidebar loads full chat history
- [ ] Adding a new persona = add prompt + `agents/newpersona.py` + register in `registry.py`; zero API changes
- [ ] `rag.py` and all `persona/` files are **unmodified** from Phase 1
- [ ] `pre-commit run --all-files` passes
- [ ] `pyright` passes with zero errors on `backend/app/agents/`

---

## Implementation Order

```
2.1 → 2.2 → 2.3    (infra + deps — can be done together)
              ↓
           2.4 → 2.5 → 2.6 → 2.7 → 2.8   (backend, sequential)
                                     ↓
                                2.9 → 2.10  (frontend, after backend is stable)
                                     ↓
                                   2.12      (integration smoke test)
```

Tasks 2.1–2.3 are independent and can be done in parallel.

---

## Files to Create or Modify

| File | Action | Notes |
|---|---|---|
| `docker/docker-compose.yml` | Modify | Add `postgres` service + `pgdata` volume |
| `backend/requirements.txt` | Modify | Add agno, sqlalchemy, psycopg |
| `backend/app/config.py` | Modify | Add `DATABASE_URL` |
| `backend/app/main.py` | Modify | Call `build_registry()` in lifespan |
| `backend/app/api/routes/chat.py` | Modify | Use Agno load/save history; call RAG unchanged |
| `backend/app/api/routes/sessions.py` | **Create** | Session list / detail / delete |
| `backend/app/api/models.py` | Modify | Add `SessionSummary`, `SessionDetail` |
| `backend/app/agents/__init__.py` | **Create** | |
| `backend/app/agents/db.py` | **Create** | PostgresDb singleton |
| `backend/app/agents/kardec.py` | **Create** | KardecAgent (identity + storage) |
| `backend/app/agents/registry.py` | **Create** | `get_agent()` / `build_registry()` |
| `backend/app/agents/sessions.py` | **Create** | `load_history()` / `save_turn()` |
| `backend/app/persona/rag.py` | **Do not touch** | |
| `frontend/src/hooks/useChat.js` | Modify | Remove client history; pass session_id |
| `frontend/src/components/SessionSidebar.jsx` | **Create** | Session list UI |
| `frontend/src/App.jsx` | Modify | Include sidebar |

---

## Known Risks

| Risk | Mitigation |
|---|---|
| `add_datetime_to_context=True` causes `datetime is not JSON serializable` on PostgresDb | Already disabled in `kardec.py`; don't set it on any agent |
| `agent.db.get_all_sessions(agent_id=...)` signature — `agent_id` param confirmed by async Postgres storage docs but worth verifying at runtime | Log warning + fall back to `get_all_session_ids()` then `get_session()` per-id if needed |
| `rag.py _sessions` dict removal — may cause test breakage if any test imports it | Search for `_sessions` in tests before removing |
| `ChatRequest.history` — client may still send it; safely ignored server-side | Keep field in Pydantic model; remove in Phase 3 cleanup |

---

## Sources

- [AgentSession reference — docs.agno.com](https://docs.agno.com/reference/agents/session)
- [Session Management — docs.agno.com](https://docs.agno.com/sessions/session-management)
- [Agent with Storage — docs.agno.com](https://docs.agno.com/agents/usage/agent-with-storage)
- [PostgreSQL Storage — docs.agno.com](https://docs.agno.com/database/providers/postgres/overview)
- [Agent API (FastAPI + Postgres reference app) — github.com/agno-agi/agent-api](https://github.com/agno-agi/agent-api)
- [Async Postgres storage issue — github.com/agno-agi/agno #3125](https://github.com/agno-agi/agno/issues/3125)
- [datetime serialization bug — github.com/agno-agi/agno #5661](https://github.com/agno-agi/agno/issues/5661)
