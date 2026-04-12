# Phase 1 — MVP: Local Model + Allan Kardec 5 Books

> **Goal:** A working end-to-end system where a user can chat with an Allan Kardec persona grounded in all 5 of his books, running fully locally.
>
> **Outcome:** User opens the frontend, selects Kardec, asks a question → backend retrieves relevant passages from the 5 books → LLM generates a grounded, styled response with citations.

---

## Overview

This phase focuses on getting the **core loop working**: corpus ingestion → vector search → LLM generation → chat UI. TurboQuant compression is deferred to Phase 2 — this phase uses standard FP16/BF16 vectors and default KV cache to validate the pipeline before adding compression.

---

## Task Breakdown

### 1. Backend Foundation

#### Task 1.1 — Project Scaffolding
**Path:** `backend/`

- [ ] Initialize Python project with `pyproject.toml` (Python 3.11+)
- [ ] Set up dependency management (pip/uv)
- [ ] Create package structure:
  ```
  backend/
  ├── pyproject.toml
  ├── requirements.txt
  ├── app/
  │   ├── __init__.py
  │   ├── main.py              ← FastAPI entry point
  │   ├── config.py            ← Settings, paths, model config
  │   ├── api/
  │   │   ├── __init__.py
  │   │   ├── routes/
  │   │   │   ├── chat.py      ← POST /api/chat
  │   │   │   ├── search.py    ← POST /api/search
  │   │   │   └── health.py    ← GET /api/health
  │   │   └── models.py        ← Pydantic request/response schemas
  │   ├── corpus/
  │   │   ├── __init__.py
  │   │   ├── parser.py        ← Text parsing for Kardec works
  │   │   ├── chunker.py       ← Semantic chunking logic
  │   │   ├── embedder.py      ← Embedding generation
  │   │   └── indexer.py       ← FAISS index builder
  │   ├── persona/
  │   │   ├── __init__.py
  │   │   ├── prompts.py       ← System prompts per persona
  │   │   └── rag.py           ← RAG retrieval + context injection
  │   ├── llm/
  │   │   ├── __init__.py
  │   │   └── engine.py        ← Model loading + inference
  │   └── utils/
  │       ├── __init__.py
  │       └── logging.py       ← Structured logging
  └── tests/
      └── ...
  ```
- [ ] Configure logging with structured JSON output
- [ ] Create `.env.example` with required environment variables

**Done when:** `uvicorn app.main:app` starts without errors; `GET /api/health` returns `{"status": "ok"}`

---

#### Task 1.2 — LLM Engine (Model Loading & Inference)
**Path:** `backend/app/llm/engine.py`

- [ ] Load Gemma 4 E4B (4-bit quantized weights) via HuggingFace Transformers
- [ ] Implement `generate(prompt, max_tokens, temperature)` function
- [ ] Handle model warmup on startup
- [ ] Memory monitoring: log VRAM usage after model load
- [ ] Graceful error handling for OOM conditions
- [ ] Support streaming responses (yield tokens as generated)

**Dependencies:** None (first task after scaffolding)

**Done when:** Model loads in < 60s, generates coherent text, VRAM < 6 GB logged

---

### 2. Corpus Pipeline (Allan Kardec — 5 Books)

#### Task 2.1 — Source Text Acquisition & Preparation
**Path:** `backend/data/kardec/`

- [x] Obtain public domain texts for all 5 books (already available in `/books` directory):
  1. **O Livro dos Espíritos**
  2. **O Livro dos Médiuns**
  3. **O Evangelho Segundo o Espiritismo**
  4. **O Céu e o Inferno**
  5. **A Gênese**
  *Plus extras: Obras Póstumas and O que é o Espiritismo.*
- [ ] Clean text: parse PDFs directly from the `/books` folder, remove OCR artifacts, normalize encoding (UTF-8), standardize formatting
- [ ] Store processed texts in `backend/data/kardec/raw/`
- [ ] Create a manifest file `backend/data/kardec/manifest.json` listing all source files with metadata

**Done when:** All books from `/books` are parsed into clean text files in UTF-8, manifest file present

---

#### Task 2.2 — Text Parser & Chunker
**Path:** `backend/app/corpus/parser.py`, `backend/app/corpus/chunker.py`

- [ ] **O Livro dos Espíritos** parser:
  - Extract 1,019 numbered Q&A units
  - One chunk per question (question + answer + commentary)
  - Metadata: `{id, autor, obra, parte, capitulo, questao, texto, edicao_referencia}`
- [ ] **O Livro dos Médiuns** parser:
  - Extract 334 articles/sections
  - One chunk per article
  - Metadata: `{id, autor, obra, parte, capitulo, artigo, texto}`
- [ ] **O Evangelho Segundo o Espiritismo** parser:
  - 28 chapters, paragraph-level chunks
  - 2-paragraph overlap between chunks
  - Metadata: `{id, autor, obra, capitulo, paragrafo_inicio, texto}`
- [ ] **O Céu e o Inferno** parser:
  - 2 parts, paragraph-level chunks with 2-paragraph overlap
  - Metadata: `{id, autor, obra, parte, capitulo, texto}`
- [ ] **A Gênese** parser:
  - 18 chapters, paragraph-level chunks with 2-paragraph overlap
  - Metadata: `{id, autor, obra, capitulo, texto}`
- [ ] Output chunked data as JSON files in `backend/data/kardec/chunks/`
- [ ] CLI command: `python -m app.corpus.parser --source data/kardec/raw/ --output data/kardec/chunks/`
- [ ] Validation: count of chunks per book matches expected structure

**Done when:** All 5 books chunked with metadata; chunk counts validated; CLI works end-to-end

---

#### Task 2.3 — Embedding Generation
**Path:** `backend/app/corpus/embedder.py`

- [ ] Select embedding model (e.g., `sentence-transformers/all-MiniLM-L6-v2` or `intfloat/multilingual-e5-large` for Portuguese)
- [ ] Generate dense embeddings for each chunk
- [ ] Save embeddings alongside chunk metadata
- [ ] Output: `backend/data/kardec/embeddings/` with numpy arrays + metadata index
- [ ] CLI command: `python -m app.corpus.embedder --chunks data/kardec/chunks/ --output data/kardec/embeddings/`

**Dependencies:** Task 2.2 (chunks must exist)

**Done when:** Embeddings generated for all chunks; dimensions match model spec; files saved

---

#### Task 2.4 — FAISS Index Builder
**Path:** `backend/app/corpus/indexer.py`

- [ ] Build FAISS `IndexFlatIP` (inner product) from chunk embeddings
- [ ] Save index to disk: `backend/data/kardec/index/kardec.faiss`
- [ ] Save metadata mapping (index position → chunk metadata): `backend/data/kardec/index/metadata.json`
- [ ] Implement search function: `search(query_embedding, top_k) → List[ChunkResult]`
- [ ] CLI command: `python -m app.corpus.indexer --embeddings data/kardec/embeddings/ --output data/kardec/index/`
- [ ] Benchmark: latency < 200ms at corpus scale

**Dependencies:** Task 2.3 (embeddings must exist)

**Done when:** Index loads; search returns relevant results; latency < 200ms

---

### 3. Persona & RAG Layer

#### Task 3.1 — Allan Kardec System Prompt
**Path:** `backend/app/persona/prompts.py`

- [ ] Craft Kardec persona system prompt:
  - Didactic, methodical tone
  - 19th century French-Brazilian intellectual vocabulary
  - References to the scientific method and observational rigor
  - Cross-references between the 5 books
  - Instructions for citation format (e.g., "L.E. Q.223", "L.M. §12")
- [ ] Template system for injecting RAG context into the prompt
- [ ] Token budget management: ensure system prompt + RAG context + user message fits within context window

**Done when:** Prompt produces stylistically Kardec-like responses; citations appear naturally

---

#### Task 3.2 — RAG Retrieval Pipeline
**Path:** `backend/app/persona/rag.py`

- [ ] For each user message:
  1. Embed the user query using the same embedding model
  2. Search FAISS index for top-K relevant chunks (K=5 default)
  3. Format retrieved chunks with citation metadata
  4. Inject into prompt template between system prompt and user message
- [ ] Implement relevance threshold: skip injection if top score is below threshold
- [ ] Return citations alongside the generated response

**Dependencies:** Task 2.4 (index), Task 3.1 (prompts), Task 1.2 (LLM engine)

**Done when:** RAG retrieves relevant Kardec passages for test queries; citations are accurate

---

### 4. API Integration

#### Task 4.1 — Chat Endpoint
**Path:** `backend/app/api/routes/chat.py`

- [ ] `POST /api/chat` endpoint:
  ```json
  // Request
  {
    "message": "O que é reencarnação?",
    "persona": "kardec",
    "session_id": "optional-session-id",
    "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
  }

  // Response
  {
    "response": "A reencarnação é lei de Natureza...",
    "citations": [
      {"id": "lde-q132", "obra": "O Livro dos Espíritos", "questao": 132, "texto": "..."}
    ],
    "session_id": "generated-or-existing-session-id"
  }
  ```
- [ ] Support streaming via Server-Sent Events (SSE) for token-by-token delivery
- [ ] Conversation history tracking (in-memory for Phase 1)
- [ ] Error handling: model not loaded, empty message, etc.

**Dependencies:** Task 3.2 (RAG pipeline complete)

**Done when:** Endpoint returns grounded responses with citations; SSE streaming works

---

#### Task 4.2 — Search Endpoint
**Path:** `backend/app/api/routes/search.py`

- [ ] `POST /api/search` endpoint:
  ```json
  // Request
  { "query": "alma imortalidade", "top_k": 10 }

  // Response
  {
    "results": [
      {"id": "lde-q150", "obra": "O Livro dos Espíritos", "questao": 150, "texto": "...", "score": 0.87}
    ]
  }
  ```

**Dependencies:** Task 2.4 (FAISS index)

**Done when:** Search returns relevant, scored results with full citation metadata

---

### 5. Frontend Integration

#### Task 5.1 — Connect Frontend to Backend
**Path:** `frontend/`

- [ ] Replace mock `generateResponse()` with real `fetch('/api/chat', ...)` calls
- [ ] Implement SSE streaming to show tokens as they arrive
- [ ] Display citations from API response (link to specific book/question)
- [ ] Show loading state while backend processes
- [ ] Error handling: backend offline, timeout, model loading
- [ ] Add `frontend/config.js` with API base URL configuration

**Dependencies:** Task 4.1 (chat endpoint working)

**Done when:** User types question → real LLM response appears with citations from the books

---

#### Task 5.2 — Search UI
**Path:** `frontend/`

- [ ] Add search mode (separate from chat) in the UI
- [ ] Connect to `POST /api/search`
- [ ] Display search results with book/chapter/question metadata
- [ ] Click-to-expand full passage text

**Dependencies:** Task 4.2 (search endpoint)

**Done when:** User can search across all 5 Kardec books by semantic meaning

---

### 6. Docker & Local Deployment

#### Task 6.1 — Dockerize Backend
**Path:** `docker/`

- [ ] Create `docker/backend.Dockerfile`:
  - Python 3.11+ base
  - NVIDIA CUDA runtime for GPU inference
  - Install dependencies
  - Model download on first run (or mount volume)
- [ ] Create `docker/docker-compose.yml`:
  ```yaml
  services:
    backend:
      build:
        context: ..
        dockerfile: docker/backend.Dockerfile
      ports:
        - "8000:8000"
      volumes:
        - ../backend/data:/app/data
        - model-cache:/root/.cache/huggingface
      deploy:
        resources:
          reservations:
            devices:
              - capabilities: [gpu]
    frontend:
      image: nginx:alpine
      ports:
        - "3000:80"
      volumes:
        - ../frontend:/usr/share/nginx/html:ro
  volumes:
    model-cache:
  ```
- [ ] Create `docker/.env.example`
- [ ] Test: `docker compose up` → both services start → GPU visible → chat works

**Done when:** `docker compose up` starts both services; full chat flow works end-to-end

---

## Acceptance Criteria for Phase 1 Completion

| Criterion | Target |
|---|---|
| All 5 Kardec books ingested | Chunks created with correct metadata for all 5 books |
| FAISS index operational | Inner product search returns relevant results |
| Search latency | < 200ms per query |
| LLM generates responses | Gemma 4 E4B loads and generates coherent text |
| RAG grounding | Responses cite specific books/questions from the corpus |
| Chat UI functional | Frontend sends messages → receives streamed responses with citations |
| Docker deployment | `docker compose up` runs the entire stack |
| VRAM usage | ≤ 6 GB (4-bit model weights + standard KV cache) |

---

## Out of Scope for Phase 1

| Item | Deferred To |
|---|---|
| TurboQuant KV cache compression | Phase 2 |
| TurboQuant embedding compression | Phase 2 |
| Multiple personas (Emmanuel, Joanna, André Luiz) | Phase 3 |
| Session persistence (database) | Phase 3 |
| Needle-in-haystack tests | Phase 2 |
| TTS / voice synthesis | Phase 4 |
| Conversation export | Phase 4 |

---

## Dependencies & Execution Order

```
Task 1.1 (scaffolding) ──→ Task 1.2 (LLM engine) ──────────────────┐
                                                                      │
Task 2.1 (text prep) ──→ Task 2.2 (parser) ──→ Task 2.3 (embed) ──→ Task 2.4 (FAISS)
                                                                      │
Task 3.1 (prompts) ─────────────────────────────────────────────────→ Task 3.2 (RAG)
                                                                      │
                                                                      ↓
                                                              Task 4.1 (chat API)
                                                              Task 4.2 (search API)
                                                                      │
                                                                      ↓
                                                              Task 5.1 (frontend integration)
                                                              Task 5.2 (search UI)
                                                                      │
                                                                      ↓
                                                              Task 6.1 (Docker)
```

Parallelizable:
- Task 1.1 + Task 2.1 can run simultaneously
- Task 1.2 + Task 2.2 can run simultaneously
- Task 3.1 can start anytime
- Task 5.1 + Task 5.2 can run simultaneously once APIs are ready
