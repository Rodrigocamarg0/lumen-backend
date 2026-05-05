# Admin Dashboard — Implementation Plan

> **Goal:** Create a secure and comprehensive Admin Dashboard to monitor user engagement, trace LLM performance, and configure persona system prompts dynamically.
>
> **Outcome:** An admin user can log in to a dedicated interface (`/admin`) on the frontend to view usage statistics, inspect detailed LLM generation traces (using existing database tables), and edit the base system prompts of writers (like Allan Kardec) without needing to redeploy the code.

---

## 1. Features & Requirements

### 1.1 User Numbers (Analytics)
- **Active Users & Sessions:** Track Daily/Weekly/Monthly Active Users (DAU/WAU/MAU) and total conversation sessions.
- **System Load:** Monitor the number of concurrent sessions and total interactions.
- **LGPD Audit:** View the count of terms of service acceptances.

### 1.2 LLM Calls Traces (Observability)
- **Generation Metrics:** Surface the data already collected in `ConversationRun` (`tokens_generated`, `tokens_per_second`, `rag_latency_ms`, `generation_latency_ms`).
- **Context Inspection:** Allow admins to drill down into a trace to see the exact user `content`, the generated response, and the injected `citations` (stored in `ConversationMessage`).
- **Debugging Filters:** Filter traces by persona, model provider, latency thresholds, or errors to identify performance bottlenecks and style drift.

### 1.3 System Prompt Configuration
- **Dynamic Prompts:** Transition the hardcoded system prompts and few-shot examples from `app.persona.prompts` into the PostgreSQL database.
- **UI Editor:** Provide a rich text/markdown editor on the frontend to update the `SYSTEM_PROMPT` and a JSON-friendly editor for the `FEW_SHOT` examples.
- **Fallback:** Maintain the hardcoded prompts as fallback initialization if the database is empty.

---

## 2. Technical Architecture

### 2.1 Database Integration (PostgreSQL + SQLAlchemy)
The system already tracks sessions, users, and LLM traces efficiently in the PostgreSQL database.
- **Existing Tables to Query:** `users`, `conversation_sessions`, `conversation_messages`, `conversation_runs`, and `terms_acceptances`.
- **New Table (`persona_configs`):**
  Create a new SQLAlchemy model `PersonaConfig` in `backend/app/models/` containing:
  - `persona_id` (String, primary key)
  - `system_prompt` (Text)
  - `few_shot_examples` (JSONB)
  - `updated_at`, `updated_by`

### 2.2 Backend Updates (FastAPI)
- **Authentication:** Extend `verify_supabase_token` in `backend/app/auth/verifier.py` to support role-based access control (RBAC). Check if `claims.get("app_metadata", {}).get("role") == "admin"`.
- **Admin API Routes (`backend/app/api/routes/admin.py`):**
  - `GET /api/admin/stats` — Aggregate metrics from `users`, `conversation_sessions`, and `conversation_runs` (e.g., averages, counts grouped by day).
  - `GET /api/admin/traces` — Return paginated `ConversationRun` records joined with `ConversationMessage` to display complete traces.
  - `GET /api/admin/personas` — Return current persona configurations from `PersonaConfig`.
  - `PUT /api/admin/personas/{id}` — Update `system_prompt` and `few_shot_examples` for a specific persona.
- **Prompt Resolution:** Update `backend/app/persona/prompts.py` to attempt to load from the `PersonaConfig` table first, falling back to the static registry if not found.

### 2.3 Frontend Updates (React / Vite)
- **Routing & Auth Guards:** Add a `/admin` route protected by a Supabase auth wrapper that verifies the `admin` role.
- **Overview View:** Utilize a charting library (like Recharts) to render timeseries data (Tokens/sec over time, Requests per day, DAU).
- **Traces View:** A data table component for `ConversationRun` logs. Clicking a row opens a drawer/modal showing the user prompt, retrieved RAG citations, the LLM response, and latency breakdown.
- **Prompts View:** A UI form featuring a dropdown to select the persona (`kardec`, etc.), a large text area for the system prompt, and a structured editor for few-shot examples.

---

## 3. Task Breakdown

### Phase A: Security & Database Adjustments
- [ ] **Task A.1:** Update Supabase Auth logic (`verifier.py`) to expose a `require_admin` dependency for FastAPI routes.
- [ ] **Task A.2:** Create the `PersonaConfig` SQLAlchemy model.
- [ ] **Task A.3:** Add an Alembic migration (or column migration in `session.py`) to create the `persona_configs` table. Seed it using the existing data from `_KARDEC_SYSTEM_PROMPT`.

### Phase B: Backend API Endpoints
- [ ] **Task B.1:** Create `backend/app/api/routes/admin.py` and register it in `main.py`.
- [ ] **Task B.2:** Implement `GET /api/admin/stats` (using SQLAlchemy `func.count` and `func.avg` to aggregate runs and users).
- [ ] **Task B.3:** Implement `GET /api/admin/traces` with pagination and filtering (e.g., `?limit=50&offset=0&persona=kardec`).
- [ ] **Task B.4:** Implement `GET` and `PUT` for `/api/admin/personas/{id}`.
- [ ] **Task B.5:** Update `build_system_prompt` and `get_few_shot_examples` in `prompts.py` to fetch overrides from the database.

### Phase C: Frontend Admin Dashboard
- [ ] **Task C.1:** Scaffold `/admin` layout in React (Sidebar + Content area) and apply the `admin` role auth guard.
- [ ] **Task C.2:** Build the **Overview** dashboard (Charts for tokens/sec, latency, and session counts).
- [ ] **Task C.3:** Build the **Traces** table with expandable rows to inspect `ConversationMessage` JSON payloads (Citations and RAG context).
- [ ] **Task C.4:** Build the **Prompts Configurator** interface, saving changes to the `PUT` endpoint.

---

## 4. Key Considerations
- **Caching Prompts:** To avoid a database hit on every chat generation turn, `PersonaConfig` records should be cached in-memory (e.g., using `functools.lru_cache` or a simple dictionary) and invalidated when a `PUT` request updates them.
- **Supabase Roles:** The `admin` role must be manually assigned via the Supabase Dashboard (`app_metadata`) to the authorized administrative users.
- **Trace Payload Size:** Traces include full message content and RAG citations. Ensure the `GET /api/admin/traces` endpoint strictly paginates responses to avoid overloading the backend and frontend memory.
