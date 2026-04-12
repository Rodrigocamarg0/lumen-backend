# Codex Agent Tasks — Phase 1 (MVP)

> **Assignee:** `agente-codex` (Implementation Agent)
> **Goal:** Write the code to bring the Lumen Phase 1 pipeline to life, strictly following the architectural decisions and Claude's extraction rules.

---

## Task D1: Backend Scaffolding & Environment Setup
**Goal:** Initialize the FastAPI project and Docker configuration.

1. **Implementation:**
   - Create `backend/pyproject.toml` or `requirements.txt` with FastAPI, Uvicorn, FAISS, PyPDF2/pdfplumber, sentence-transformers, transformers, bitsandbytes.
   - Create the `backend/app/` directory structure as defined in `phase-1-mvp.md`.
   - Write `docker/backend.Dockerfile` and `docker/docker-compose.yml` supporting NVIDIA GPU passthrough.
2. **Done When:** `docker compose up` starts a FastAPI server returning `{"status": "ok"}` on `GET /api/health`.

---

## Task D2: PDF Parsing & Corpus Ingestion
**Goal:** Implement the extraction pipeline to convert PDFs in `/books` to chunked JSON.

1. **Implementation:**
   - Read `specs/architecture/parsing_strategy.md` (provided by Claude).
   - Write `backend/app/corpus/parser.py` using a PDF parsing library.
   - Implement the chunking logic in `backend/app/corpus/chunker.py` (Q&A for LdE, overlapping paragraphs for narrative works).
   - Save the output to `backend/data/kardec/chunks/`.
2. **Done When:** A CLI command successfully processes all 5 PDFs and outputs perfectly formatted JSON chunk files with correct metadata.

---

## Task D3: Embedding & FAISS Indexing
**Goal:** Convert text chunks into a searchable vector index.

1. **Implementation:**
   - Write `backend/app/corpus/embedder.py` using `sentence-transformers` (e.g., multilingual-e5-large or all-MiniLM-L6-v2).
   - Write `backend/app/corpus/indexer.py` to build a `faiss.IndexFlatIP` (Inner Product, NOT Cosine).
   - Implement the `search(query_embedding, top_k)` method.
2. **Done When:** The FAISS index is saved to disk and a test script can successfully retrieve the top 5 relevant chunks for a test query in under 200ms.

---

## Task D4: LLM Engine & RAG Integration
**Goal:** Load Gemma 4 E4B and hook up the RAG context.

1. **Implementation:**
   - Write `backend/app/llm/engine.py` to load `google/gemma-4-E4B-it` via HuggingFace in 4-bit quantization.
   - Write `backend/app/persona/rag.py` to orchestrate: User Query $\rightarrow$ FAISS Search $\rightarrow$ Context Formatting $\rightarrow$ Claude's System Prompt $\rightarrow$ LLM Generation.
2. **Done When:** A Python script can generate a stylistically accurate response grounded in the Kardec corpus.

---

## Task D5: API Routes & Streaming
**Goal:** Expose the LLM and RAG pipeline via REST APIs.

1. **Implementation:**
   - Read `specs/architecture/api_contract.md`.
   - Implement `POST /api/chat` using FastAPI `StreamingResponse` (SSE) to stream tokens.
   - Implement `POST /api/search` for direct corpus search.
2. **Done When:** Endpoints successfully handle requests and stream tokenized responses to curl/Postman.

---

## Task D6: Frontend UI Implementation
**Goal:** Build the static chat interface.

1. **Implementation:**
   - Create `frontend/index.html` and `frontend/app.js` using vanilla JS and TailwindCSS via CDN.
   - Implement SSE consumption to render the streaming chat response.
   - Render the citations nicely below each response.
2. **Done When:** The user can open `localhost:3000` in the browser, type a question, and see Kardec answering token-by-token with citations.
