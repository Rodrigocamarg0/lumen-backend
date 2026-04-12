# Claude Agent Tasks — Phase 1 (MVP)

> **Assignee:** `agente-claude` (Research & Architecture Agent)
> **Goal:** Provide the theoretical groundwork, prompt engineering, and parsing strategies needed by the implementation agent for Phase 1.

---

## Task C1: Corpus Structure Analysis & Extraction Rules
**Goal:** Define exactly how to extract and chunk the text from the 5 Kardec PDFs in `/books`.

1. **Analyze PDF Layouts:**
   - Investigate the structure of `WEB-Livro-dos-Espíritos-Guillon-1.pdf`. Identify the regex or logic required to isolate the 1,019 questions, answers, and Kardec's commentaries.
   - Investigate the narrative books (`O Evangelho Segundo o Espiritismo`, `A Gênese`, etc.) and define the heuristic for paragraph-level chunking with a 2-paragraph overlap.
2. **Output Required:**
   - Create a document `specs/architecture/parsing_strategy.md`.
   - Provide exact pseudo-code, regex patterns, or Python extraction logic for the implementation agent (`agente-codex`).
   - Define the final JSON metadata schema for the chunks.

---

## Task C2: Persona System Prompt Engineering
**Goal:** Craft the definitive System Prompt for the Allan Kardec persona.

1. **Persona Design:**
   - Tone: 19th-century French-Brazilian intellectual, didactic, methodical, focused on the scientific method and observational rigor.
   - Grounding Rules: Must strictly base answers on the retrieved RAG context.
   - Citation Formatting: Must instruct the LLM on how to inline citations (e.g., "[L.E. Q.223]").
2. **Output Required:**
   - Write the prompt in `backend/app/persona/prompts.py` (or provide it to Codex to implement).
   - Provide 3-5 example few-shot interactions to guide the LLM's style.

---

## Task C3: API Payload & Citation Schema Definition
**Goal:** Design the contract between the Frontend and Backend.

1. **API Design:**
   - Define the exact JSON schema for `POST /api/chat` and `POST /api/search`.
   - Define how Server-Sent Events (SSE) will stream the tokens and append the citation metadata at the end of the stream.
2. **Output Required:**
   - Create `specs/architecture/api_contract.md` detailing the request/response models.

---

## Task C4: Evaluation Baselines (LdE 50 Questions)
**Goal:** Create the ground truth dataset for testing RAG precision.

1. **Dataset Creation:**
   - Curate a list of 50 common questions related to Spiritism that are explicitly answered in *O Livro dos Espíritos*.
   - Map each question to its correct expected ID (e.g., `lde-q132`).
2. **Output Required:**
   - Create `evals/data/lde-50-questions.json` with the format: `[{"query": "O que é Deus?", "expected_chunk_id": "lde-q001"}]`.
