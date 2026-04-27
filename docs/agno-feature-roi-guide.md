# Agno Feature ROI Guide

Last reviewed: 2026-04-27

This guide maps the current Agno documentation to Lumen's backend architecture and ranks the
features that are most likely to increase product value with the least implementation risk.

## Current Lumen Baseline

Lumen already uses Agno for persona identity and Postgres-backed session storage:

- `app/agents/kardec.py` creates an Agno `Agent` with `PostgresDb`.
- `app/agents/db.py` configures `lumen_sessions` as the Agno session table.
- `app/agents/sessions.py` manually reads `agent.get_chat_history()` and writes `AgentSession`
  records after the custom RAG stream finishes.
- Actual generation does not call `agent.run()`. It streams through `app/persona/rag.py` and
  `app/llm/engine.py`.

That split matters. Agno features that only depend on the database/session APIs can be adopted
quickly. Features that depend on `Agent.run()` need either an adapter layer or a later migration of
generation into Agno.

## Documentation Facts To Anchor Decisions

- Current PyPI release found online: `agno 2.5.17`, uploaded 2026-04-15. The project currently pins
  only `agno>=1.7`, so we should test and then pin a compatible `2.5.x` range before relying on the
  newest APIs.
- Agno sessions are multi-turn threads identified by `session_id`; a database is required for
  persistence across runs. Source: https://docs.agno.com/sessions/overview
- Adding a database to an agent automatically stores sessions, runs, state, metadata, metrics, and
  optional summaries in a session table. Source: https://docs.agno.com/database/session-storage
- Chat history can be injected with `add_history_to_context=True`, limited with
  `num_history_runs`, or retrieved programmatically with `get_chat_history()`. Source:
  https://docs.agno.com/database/chat-history
- User memory is separate from session history. Memory stores learned user facts and preferences;
  session history stores conversation continuity. Source: https://docs.agno.com/memory/overview
- Memory can be automatic with `update_memory_on_run=True` or agentic with
  `enable_agentic_memory=True`; do not enable both because agentic memory takes precedence. Source:
  https://docs.agno.com/memory/overview
- Session summaries reduce token growth in long conversations and can be mixed with recent history.
  Source: https://docs.agno.com/sessions/session-summaries
- Session state is persisted per session and can be exposed to the model with
  `add_session_state_to_context=True`; agentic state requires `enable_agentic_state=True`. Source:
  https://docs.agno.com/state/agent/overview
- Reasoning agents are enabled with `reasoning=True` and are best for complex multi-step tasks with
  validation. Source: https://docs.agno.com/reasoning/reasoning-agents
- `PostgresDb` supports custom tables for sessions, memories, metrics, evals, and knowledge. Source:
  https://docs.agno.com/reference/storage/postgres
- Agno's `OpenAIResponses` provider uses OpenAI's newer Responses API and supports advanced tool
  use, file processing, and knowledge retrieval. Source:
  https://docs.agno.com/models/providers/native/openai/responses/overview

## ROI Ranking

### 1. Session Summaries

ROI: very high. Cost and latency improve as conversations get longer, while continuity gets better.

Fit with current code: good, but not fully automatic because Lumen manually constructs sessions
instead of running `agent.run()`.

Implementation path:

1. Keep `load_history()` limited to the last 3 to 5 turns instead of 10.
2. Add a custom summary field in `conversation_sessions` or use Agno's session `summary` if the
   installed version exposes stable APIs for manual updates.
3. Generate or refresh the summary asynchronously after `persist_completed_turn()`, using a cheap
   model.
4. Inject the summary into `RAGOrchestrator.astream_response()` as a compact context block before
   recent history.

Do not wait for full Agno generation migration to do this. This is the fastest ROI feature.

### 2. User Memory

ROI: high. Lumen is a spiritual-study assistant; remembering language, study level, preferred
books, recurring doubts, and preferred answer style can make the product feel much more personal.

Fit with current code: medium. Agno's built-in automatic memory runs around `Agent.run()`, so the
current manual stream should start with a Lumen-owned memory service and later converge with Agno
tables.

Recommended memories:

- Language and tone preference: Portuguese, English, concise, scholarly, pastoral.
- Study profile: beginner, intermediate, advanced.
- Recurring themes: mediunidade, Evangelho, livre-arbitrio, sofrimento, reencarnacao.
- Citation preference: wants direct Livro dos Espiritos references, wants short excerpts, wants
  chapter-oriented study.
- Safety constraints: user is grieving, anxious, or asking sensitive personal guidance. Store this
  only if consent and privacy policy allow it.

Implementation path:

1. Configure `PostgresDb(memory_table="lumen_memories")` in `app/agents/db.py`.
2. Add an app-level `user_memories` service first: extract compact facts after each completed turn,
   store by `user_id`, `persona_id`, topic, confidence, and source session.
3. Retrieve the top 3 to 5 relevant memories before RAG generation and pass them into the system
   prompt as "user preferences", never as doctrine facts.
4. Add endpoints to list/delete memories. Memory must be user-controllable.
5. After generation moves through Agno, evaluate replacing the extractor with
   `update_memory_on_run=True`. Prefer automatic memory first; agentic memory has more autonomy and
   should wait until observability is strong.

### 3. Better Session History

ROI: high. This is already partly implemented, but can be made cheaper and more reliable.

Fit with current code: excellent. The backend already calls `get_chat_history()` directly.

Implementation path:

1. Change the default history window from 10 turns to 3 to 5.
2. Combine recent history with the session summary.
3. Preserve the app-level `conversation_sessions` tables for ownership, UI listing, soft delete, and
   audit. Use Agno's `lumen_sessions` as the model-facing transcript store.
4. Always pass `user_id` when using Agno APIs where available. Current manual save does not attach
   `user_id` to the Agno session, which weakens multi-user isolation inside Agno.

### 4. Session State

ROI: medium-high once the product has workflows. It is less important than memory and summaries for
pure chat.

Good Lumen uses:

- Current study plan.
- Preferred corpus filter.
- Session goal, such as "prepare a talk" or "study chapter 5".
- User-selected answer mode: short answer, Socratic tutor, citation-heavy, pastoral.

Implementation path:

1. Start with app-owned state in `conversation_sessions.metadata`, because generation is manual.
2. Inject state into `build_system_prompt()` separately from memory and RAG context.
3. If moving to `agent.run()`, use Agno `session_state`, `add_session_state_to_context=True`, and
   explicit tools for updates.
4. Do not enable `enable_agentic_state` until the state schema is stable.

### 5. Reasoning / Thinking

ROI: medium for normal chat, high for specific tasks like comparing doctrine passages, creating
study plans, resolving apparent contradictions, or checking citation fidelity.

Fit with current code: mixed. Agno `reasoning=True` is designed around `Agent.run()`. Lumen already
has `OPENAI_REASONING_EFFORT` for OpenAI reasoning models in the custom engine, which may be cheaper
than a full Agno reasoning-agent migration.

Implementation path:

1. Keep normal chat on the fast path.
2. Add a request option such as `reasoning_mode: "off" | "model" | "agno"` later.
3. First implement `"model"` by routing `OPENAI_REASONING_EFFORT` to OpenAI reasoning-capable
   models in `app/llm/engine.py`.
4. Implement Agno `reasoning=True` only in a separate non-streaming or tool-heavy endpoint after
   deciding to call `agent.run()`.
5. Never stream private chain-of-thought to users. Expose a concise reasoning summary or validation
   status instead.

### 6. Context Compression

ROI: medium later. It helps most when tool calls return large payloads. Lumen's current context is
mostly curated RAG chunks, so summaries and tighter `top_k_chunks` are better first.

Implementation path:

1. Add token accounting for system prompt, RAG chunks, history, memory, and answer.
2. Trim or summarize oversized RAG snippets before adding a generic compression layer.
3. Revisit Agno context compression when Lumen has tools that return verbose data.

### 7. AgentOS / Metrics / Evals

ROI: medium. Useful for observability, debugging, and improving answer quality, but not the first
personalization win.

Implementation path:

1. Configure `metrics_table` and `eval_table` in `PostgresDb` once on Agno 2.5.x.
2. Keep Lumen's existing `ConversationRun` table as the product audit trail.
3. Add evals around citation precision, answer faithfulness, and refusal/safety behavior.

## Recommended Phase 1 Implementation Plan

1. Upgrade and pin Agno after compatibility testing:
   `agno>=2.5.17,<2.6`.
2. Update `app/agents/db.py`:
   - `session_table="lumen_sessions"`
   - `memory_table="lumen_memories"`
   - `metrics_table="lumen_metrics"`
   - `eval_table="lumen_evals"`
3. Add summary support:
   - new summary generation helper
   - `summary` injection into `RAGOrchestrator`
   - history window reduced to 3 to 5 turns
4. Add app-owned user memory:
   - extractor after completed turns
   - retrieval before prompt build
   - delete/list API for user control
5. Add session state only for explicit product controls:
   - answer mode
   - active study goal
   - corpus preferences
6. Add reasoning mode only after the above:
   - start with OpenAI model reasoning effort
   - add Agno reasoning endpoint later if tool-heavy workflows justify it

## Target Prompt Assembly Order

Keep these context types separated so the model does not confuse user preference with doctrine:

1. Persona and safety instructions.
2. Session state: current mode, study goal, selected corpus filters.
3. User memory: preferences and stable user facts.
4. Session summary: compact conversation continuity.
5. Recent history: last 3 to 5 turns.
6. RAG context: authoritative Kardec corpus chunks with citations.
7. Current user message.

## Data Privacy Rules

- Memory must be visible, editable, and deletable by the user.
- Do not store sensitive emotional or spiritual disclosures unless the product explicitly asks
  consent or the memory is essential for safety.
- Treat memories as personalization hints, not factual sources.
- Never let cross-session memory override retrieved doctrine citations.
- Soft-deleting a session should also delete or detach Agno session rows and generated summaries for
  that session.

## Acceptance Criteria

- A 20-turn conversation costs materially fewer input tokens after summaries are enabled.
- The assistant can remember a user's preferred answer style across sessions.
- The user can list and delete stored memories.
- Session ownership remains enforced by Lumen's existing authenticated user model.
- Citation quality does not regress when summaries and memories are injected.
- Default chat latency does not increase for simple questions.
