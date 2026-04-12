# Lumen — Requirements Specification

> **Version:** 1.0-draft
> **Date:** 2026-04-11
> **Status:** Draft — Pending Review
> **Source documents:** [LUMEN_CONTEXT.md](file:///Users/Rodrigo/CMP/lumen/LUMEN_CONTEXT.md), [project_instructions.md](file:///Users/Rodrigo/CMP/lumen/project_instructions.md)

---

## 1. Product Vision

Lumen is a system that enables users to **converse with and simulate the writing style of deceased authors** (the "dead writers" use case). It combines:

1. **TurboQuant-compressed vector quantization** for memory-efficient long sessions
2. **RAG over the author's complete corpus** for factual fidelity and stylistic grounding
3. **Gemma 4 E4B as the base LLM** running locally on consumer hardware

The core promise: a user can hold a **2-hour, 128K-token conversation** with the persona of a historical author — Machado de Assis, Allan Kardec, or Emmanuel via Chico Xavier — without degradation in style coherence, factual accuracy, or system responsiveness, all running on a single consumer GPU.

---

## 2. Stakeholders

| Role | Interest |
|---|---|
| **End User** | Engage in natural, stylistically faithful conversations with literary personas; perform semantic search across author corpora |
| **System Administrator** | Deploy and maintain the system on WSL2/Docker with consumer GPU; manage corpus ingestion |
| **Corpus Curator** | Prepare, chunk, and validate author texts for ingestion; verify licensing compliance |
| **Developer / AI Engineer** | Implement and maintain the TurboQuant integration, RAG pipeline, and persona layer |

---

## 3. User Stories

### 3.1 Conversation & Persona

| ID | Story | Priority |
|---|---|---|
| US-01 | As a user, I want to select a deceased author persona (e.g., "Machado de Assis") and start a conversation in their characteristic style, so that I can experience their literary voice interactively. | **P0** |
| US-02 | As a user, I want to converse with an author persona for up to 2 hours (128K tokens) without noticeable degradation in style or coherence, so that long exploratory sessions remain immersive. | **P0** |
| US-03 | As a user, I want the persona to ground its responses in the author's actual works (citing specific books, chapters, or questions), so that I can trust the factual basis of the conversation. | **P0** |
| US-04 | As a user, I want to switch between author personas within the same session, so that I can compare perspectives (e.g., Kardec vs. Emmanuel on the same topic). | **P1** |

### 3.2 Corpus & Search

| ID | Story | Priority |
|---|---|---|
| US-05 | As a user, I want to perform semantic search across the complete corpus of an author, so that I can find relevant passages by meaning rather than keyword. | **P0** |
| US-06 | As a corpus curator, I want to ingest a new author's works via a structured pipeline (text → chunks → embeddings → compressed index), so that the system can be extended to new authors without code changes. | **P0** |
| US-07 | As a user, I want search results to include precise citations (work, chapter, question number), so that I can locate the original source text. | **P0** |

### 3.3 System & Operations

| ID | Story | Priority |
|---|---|---|
| US-08 | As a system administrator, I want to deploy the entire system via Docker Compose on a machine with WSL2 + consumer GPU (6–8 GB VRAM), so that no cloud infrastructure is required. | **P0** |
| US-09 | As a developer, I want to run a validation suite that checks TurboQuant distortion bounds against the paper's theoretical limits, so that quantization correctness is verified before deployment. | **P0** |
| US-10 | As a system administrator, I want to monitor KV cache memory usage during sessions, so that I can verify compression ratios and detect memory anomalies. | **P1** |

### 3.4 Optional / Future

| ID | Story | Priority |
|---|---|---|
| US-11 | As a user, I want to hear the persona's responses spoken aloud in a synthesized voice appropriate to the author's era and style. | **P2** |
| US-12 | As a user, I want to export a conversation session as a formatted document (Markdown or PDF), so that I can preserve and share the dialogue. | **P2** |

---

## 4. Acceptance Criteria (Technical)

### 4.1 Session Length & Coherence

| Criterion | Target | Measurement |
|---|---|---|
| Maximum session length | **128K tokens** without out-of-memory or quality collapse | End-to-end session test |
| Style coherence over session | **< 5% degradation** in n-gram overlap with author corpus between turn 1 and turn 50+ | `persona_eval.py` |
| Needle-in-haystack recall | **> 95%** at 4K, 16K, 64K, and 128K token context lengths | `kv_cache_eval.py` |

### 4.2 KV Cache Compression

| Criterion | Target | Source |
|---|---|---|
| Memory compression ratio | **≥ 5x** vs FP16 baseline | Gemma 4 benchmarks: 5.22x confirmed |
| Perplexity degradation at 3.5-bit | **< 1%** (zero-loss target) | TurboQuant paper + mlx-vlm benchmarks |
| MSE distortion at 3-bit (d=256) | **≤ 0.035** (within 1.2x of paper bound 0.030) | Paper Table 1 |
| MSE distortion at 4-bit (d=256) | **≤ 0.011** (within 1.2x of paper bound 0.009) | Paper Table 1 |

### 4.3 RAG Pipeline

| Criterion | Target | Measurement |
|---|---|---|
| Retrieval recall@10 | **> 0.90** on author corpus | `persona_eval.py` |
| Citation precision | **> 90%** on 50 known Kardec questions (LdE → correct question number) | `kv_cache_eval.py` |
| Embedding compression | TurboQuantMSE at 3.5-bit on FAISS index | Memory measurement |
| Search latency (single query) | **< 200 ms** at corpus scale (10K+ chunks) | Latency benchmark |

### 4.4 Algorithm Validation

| Criterion | Target | Method |
|---|---|---|
| `validate_algorithms.py` | **30/30 checks passing** | OmarHory/turboquant benchmark suite |
| Inner product error (TurboQuantMSE) | Within paper bounds for d=256 | Custom benchmark |
| Codebook verification | Lloyd-Max codebooks precomputed for d=256 (not reused from d=128) | Unit test |

---

## 5. Constraints

### 5.1 Hardware & Runtime

| Constraint | Detail |
|---|---|
| **Runtime environment** | WSL2 + Docker + NVIDIA GPU (consumer-grade) |
| **VRAM budget** | 4–6 GB at 4-bit model weights + TurboQuant 3.5-bit KV cache |
| **Base model** | Gemma 4 E4B (Dense, not MoE; head_dim=256; 128K context) |
| **No fine-tuning at runtime** | Persona behavior achieved through system prompt + RAG, not model adaptation |
| **Offline operation** | System must function without internet after initial setup and model download |

### 5.2 Algorithm & Implementation

| Constraint | Detail |
|---|---|
| **Quantizer** | `TurboQuantMSE` for both K and V vectors — `TurboQuantProd` is **not** used unless explicitly justified (Finding 2: MSE beats Prod in practice) |
| **Bit allocation** | 3.5-bit uniform for Gemma 4 E4B (K/V ratio ≈ 1x on global layers) |
| **Mixed precision** | Outlier channels (top 5–20% by RMS) at 8-bit; rest at 3-bit; effective average ≈ 3.6 bits |
| **Search metric** | FAISS inner product (not cosine) — aligns with TurboQuant's inner product preservation design |
| **Speedup expectations** | Real quantized attention speedup is **~1.85x** (not 8x reported in paper — authors' optimized CUDA kernels not released) |
| **Head dimension** | Lloyd-Max codebooks must be precomputed for **d=256** — d=128 codebooks from other models cannot be reused |

### 5.3 Corpus & Licensing

| Constraint | Detail |
|---|---|
| **Public domain works** | Allan Kardec's complete pentateuch + Revista Espírita (1858–1869) — freely redistributable |
| **Licensed works** | Joanna de Angelis / Divaldo Franco (LEAL Editora) and Emmanuel / Chico Xavier (FEB) — **license must be verified before distributing indices** |
| **Chunking granularity** | O Livro dos Espíritos: question-level (1,019 units); Narrative works: paragraph-level with 2-paragraph overlap |

---

## 6. Feature List

### 6.1 Feature F1 — Corpus Ingestion Pipeline

**Description:** Structured pipeline to ingest, chunk, embed, and index author works.

| Sub-feature | Detail |
|---|---|
| F1.1 — Text parsing | Parse structured works (Q&A and narrative) into semantic chunks with metadata |
| F1.2 — Metadata schema | Each chunk carries: `id`, `autor`, `medium`, `obra`, `parte`, `capitulo`, `questao`, `texto`, `edicao_referencia` |
| F1.3 — Embedding generation | Generate dense embeddings for each chunk using the model's embedding layer (or a dedicated encoder) |
| F1.4 — Extensibility | New authors added by providing text + metadata mapping — no code changes required |

**Example chunk (O Livro dos Espíritos):**
```json
{
  "id": "lde-q223",
  "autor": "Allan Kardec",
  "medium": null,
  "obra": "O Livro dos Espíritos",
  "parte": "Parte Segunda — Do Mundo Espírita",
  "capitulo": "I — Os Espíritos",
  "questao": 223,
  "texto": "...",
  "edicao_referencia": "FEB, 2013"
}
```

### 6.2 Feature F2 — Compressed Vector Store

**Description:** TurboQuant-compressed FAISS index for memory-efficient semantic search over author corpora.

| Sub-feature | Detail |
|---|---|
| F2.1 — TurboQuantMSE compression | Compress embedding vectors using TurboQuantMSE at 3.5-bit per coordinate |
| F2.2 — FAISS inner product index | Build FAISS index using inner product similarity (not cosine) |
| F2.3 — Retrieval API | Query interface returning top-K chunks with scores and full citation metadata |
| F2.4 — Index persistence | Save/load compressed indices to disk for fast startup |

### 6.3 Feature F3 — Quantized KV Cache

**Description:** TurboQuant-compressed KV cache for Gemma 4 E4B, enabling 128K-token sessions on consumer GPU.

| Sub-feature | Detail |
|---|---|
| F3.1 — `TurboQuantCache` | Drop-in HuggingFace `DynamicCache`-compatible cache using TurboQuantMSE |
| F3.2 — Outlier-aware mixed precision | Detect high-RMS channels per layer; route to 8-bit; regular channels at 3-bit |
| F3.3 — Quantized attention | Compute Q@K^T directly on compressed indices via `QuantizedAttention` — no dequantization for intermediate operations |
| F3.4 — Memory monitoring | Runtime reporting of KV cache memory usage, compression ratio, and per-layer statistics |

### 6.4 Feature F4 — Persona Generation Layer

**Description:** Stylistically faithful response generation grounded in author's corpus via RAG.

| Sub-feature | Detail |
|---|---|
| F4.1 — System prompt per persona | Curated system prompts capturing each author's voice, vocabulary, era, and philosophical stance |
| F4.2 — RAG retrieval per turn | For each user message, retrieve top-K relevant corpus chunks and inject into context |
| F4.3 — Citation injection | Responses include inline citations referencing specific works, chapters, or numbered questions |
| F4.4 — Multi-persona support | Switch between author personas within or across sessions |
| F4.5 — Style consistency tracking | Monitor n-gram overlap with corpus across session to detect style drift |

### 6.5 Feature F5 — Text-to-Speech (Optional)

**Description:** Synthesize persona responses as spoken audio, optionally matching the author's era/style.

| Sub-feature | Detail |
|---|---|
| F5.1 — TTS integration | Connect to a TTS engine for basic speech synthesis of responses |
| F5.2 — Voice cloning (if available) | If audio recordings of the author exist, use voice cloning for higher fidelity |

---

## 7. Non-Functional Requirements

### 7.1 Performance

| Requirement | Target |
|---|---|
| Time-to-first-token | **< 3 seconds** for typical user messages at any point in session |
| Token generation throughput | **≥ 15 tokens/second** on consumer GPU (Gemma 4 E4B at 4-bit) |
| RAG retrieval latency | **< 200 ms** per query at corpus scale |
| System startup (model load + index load) | **< 60 seconds** |

### 7.2 Memory & Resources

| Requirement | Target |
|---|---|
| Peak VRAM usage | **≤ 6 GB** (4-bit weights + TurboQuant KV at 128K context) |
| System RAM | **≤ 16 GB** for FAISS index + application overhead |
| Disk storage | Model weights (~5 GB) + FAISS indices + corpus texts |

### 7.3 Reliability

| Requirement | Target |
|---|---|
| Session stability | No OOM crashes at 128K context with TurboQuant enabled |
| Graceful degradation | If memory pressure detected, warn user before truncating context |
| Data integrity | Corpus indices are read-only during sessions; corruption requires explicit re-indexing |

### 7.4 Observability

| Requirement | Detail |
|---|---|
| Logging | Structured logs for ingestion, retrieval, generation, and cache metrics |
| Metrics | KV cache size, compression ratio, retrieval recall, session token count |
| Health checks | API endpoint reporting model loaded, index loaded, VRAM available |

### 7.5 Security & Privacy

| Requirement | Detail |
|---|---|
| Local execution | All inference and data processing happens locally — no data sent to external services |
| Corpus licensing | System must track and display licensing status of each author's works |
| No PII in logs | User conversation content is not persisted in logs by default |

---

## 8. Out of Scope (v1.0)

The following are explicitly **not** in scope for the initial release:

| Item | Rationale |
|---|---|
| Fine-tuning or LoRA adaptation | Persona achieved via prompt + RAG; fine-tuning adds complexity without proven benefit for this use case |
| Multi-user / multi-tenant | v1.0 is single-user, local deployment |
| Cloud deployment | Target is local WSL2/Docker; cloud hosting is a future concern |
| Real-time voice conversation | TTS (F5) is optional and one-directional; real-time voice-in/voice-out is deferred |
| Gemma 4 26B or larger | E4B fits consumer GPU; larger models require different hardware planning |
| `TurboQuantProd` for K/V | Empirically inferior for this use case (see LUMEN_CONTEXT.md §4 Finding 2) |
| Automatic corpus scraping | Corpus is provided locally as PDFs in the `/books` directory; web scraping is not included |

---

## 9. Glossary

| Term | Definition |
|---|---|
| **TurboQuant** | Online vector quantization algorithm (ICLR 2026) that compresses vectors to 2.5–4 bits with near-zero distortion |
| **TurboQuantMSE** | MSE-optimal variant of TurboQuant — uses random rotation + Lloyd-Max scalar quantizer |
| **TurboQuantProd** | Inner-product-optimal variant — two-stage (MSE + QJL residual correction); not recommended for Lumen |
| **QJL** | Quantized Johnson-Lindenstrauss — 1-bit projection for unbiased inner product estimation |
| **KV Cache** | Key-Value cache storing attention states during LLM inference; grows linearly with sequence length |
| **FAISS** | Facebook AI Similarity Search — library for dense vector similarity search |
| **RAG** | Retrieval-Augmented Generation — grounding LLM responses in retrieved documents |
| **Lloyd-Max Quantizer** | Optimal scalar quantizer minimizing MSE for a known distribution |
| **Gemma 4 E4B** | Google's 4B-parameter dense LLM with head_dim=256 and 128K context window |
| **head_dim** | Dimensionality of each attention head's key/value vectors |
| **K/V Ratio** | Ratio of Key to Value vector magnitudes — determines optimal bit allocation strategy |
| **Outlier channels** | K vector channels with RMS 10–100x larger than median; require higher bit precision |
| **Persona** | The simulated identity and writing style of a deceased author |
| **LdE** | O Livro dos Espíritos (The Spirits' Book) by Allan Kardec |

---

## 10. References

| Document | Path / URL |
|---|---|
| Lumen Technical Context | [LUMEN_CONTEXT.md](file:///Users/Rodrigo/CMP/lumen/LUMEN_CONTEXT.md) |
| Project Instructions | [project_instructions.md](file:///Users/Rodrigo/CMP/lumen/project_instructions.md) |
| TurboQuant Paper | [arXiv 2504.19874](https://arxiv.org/abs/2504.19874) |
| OmarHory/turboquant (GPU impl.) | [GitHub](https://github.com/OmarHory/turboquant) |
| scos-lab/turboquant (reference) | [GitHub](https://github.com/scos-lab/turboquant) |
| turboquant-mlx (Apple Silicon) | [GitHub](https://github.com/sharpner/turboquant-mlx) |
| Gemma 4 Documentation | [Google AI](https://ai.google.dev/gemma/docs/core) |
