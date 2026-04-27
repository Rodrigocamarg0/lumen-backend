# User Capabilities Plan — Supabase Auth, User Sessions, Conversation History, and Tracing

> **Status:** Draft
> **Date:** 2026-04-27
> **Scope:** `frontend/` + `backend/`
> **Purpose:** Define the first implementation plan for authenticated users, user-owned chat sessions, persistent conversation history, and Agno session/tracing integration.

---

## 1. Why This Work Is Needed

Today Lumen has:

- anonymous frontend state backed by `localStorage`
- persona-scoped Agno sessions in Postgres
- no trusted user identity on the backend
- no ownership model for chat history
- no first-class application tables for users, messages, or chat runs
- no trace strategy for the custom `rag.astream_response()` path

That is enough for a local single-user prototype, but not enough for:

- login with Google or email/password
- restoring a user’s own history across devices
- protecting sessions from other users
- supporting account settings and future billing tiers
- debugging chat executions with user/session/run trace correlation

This document plans the first version of those capabilities.

---

## 2. Important Scope Note

This expands beyond the current repository requirement that v1 is single-user and local deployment focused.

Before implementation starts, we should explicitly accept these product changes:

- Lumen will depend on Supabase Auth for identity.
- The app will no longer be fully offline after setup.
- Backend APIs will move from anonymous access to authenticated access for chat history features.
- Session persistence will become user-scoped, not only persona-scoped.

If that direction is confirmed, the plan below is the recommended path.

---

## 3. Recommended Architecture

### 3.1 Identity

- Use **Supabase Auth** as the identity provider.
- Support:
  - Google OAuth via Supabase
  - email/password sign up
  - email/password sign in
  - sign out
  - password reset

### 3.2 Frontend Responsibility

- The frontend owns the Supabase browser client.
- The frontend obtains the Supabase access token after login.
- Every authenticated API request to FastAPI sends:

```http
Authorization: Bearer <supabase_access_token>
```

### 3.3 Backend Responsibility

- FastAPI verifies the Supabase JWT and derives the authenticated user from the token.
- FastAPI owns all authorization decisions.
- FastAPI stores app-level entities for:
  - user profile
  - chat session
  - chat message
  - chat run metadata

### 3.4 Persistence

- Keep **Agno session storage** for runtime conversation history compatibility.
- Add **first-class relational tables** for product features and ownership queries.
- Recommended source of truth split:
  - Supabase Auth: identity
  - app tables: product data
  - Agno session tables: agent/session runtime persistence
  - Agno trace tables: observability

### 3.5 Core Rule

The backend must never trust `user_id`, `email`, or ownership fields from the frontend body or query string. User identity must come only from the verified token.

---

## 4. Current-State Gaps

### Frontend

Current frontend behavior:

- no auth UI
- no auth provider or session listener
- no bearer token injection in API helpers
- `localStorage` stores only `lumen-session-id`
- chat history sidebar assumes all sessions are globally readable

Relevant current files:

- `frontend/src/App.jsx`
- `frontend/src/hooks/useChat.js`
- `frontend/src/lib/api.js`

### Backend

Current backend behavior:

- `/api/chat` is anonymous
- `/api/sessions` lists sessions without a user filter
- Agno session lookup is persona-based only
- no user model, no ORM, no migrations
- CORS does not explicitly allow `Authorization`

Relevant current files:

- `backend/app/main.py`
- `backend/app/api/routes/chat.py`
- `backend/app/api/routes/sessions.py`
- `backend/app/agents/sessions.py`
- `backend/app/api/models.py`

---

## 5. Key Design Decisions

### Decision 1 — Keep FastAPI as the application backend

Do not move application logic into Supabase Edge Functions.

Reason:

- model inference and RAG already live in FastAPI
- Agno and local model orchestration are already wired there
- ownership, chat history, and trace correlation belong close to the chat pipeline

### Decision 2 — Use Supabase Auth, not Supabase as the only application API

Supabase should provide authentication, but FastAPI should remain the main product API.

Reason:

- chat is already streamed through FastAPI SSE
- session ownership and persona logic are backend concerns
- future quotas, billing, and access policies are easier to enforce in one app backend

### Decision 3 — Add first-class app tables instead of relying only on Agno tables

Agno session storage is not enough as the only product database.

Reason:

- product screens need queryable user/session/message metadata
- session ownership should be explicit in app tables
- exports, analytics, and moderation become easier
- Agno formats may change independently of product requirements

### Decision 4 — Keep one conversation ID across app and Agno

Recommended:

- `conversation_sessions.id == agno session_id`

Reason:

- avoids mapping complexity
- makes trace correlation simpler
- reduces chances of session duplication bugs

### Decision 5 — Do not depend on automatic Agno tracing alone

Important constraint:

- current chat generation does **not** use `agent.run()`
- it uses `rag.astream_response()` directly

Implication:

- Agno tracing will not fully cover the current chat pipeline automatically

Recommended approach:

- keep Agno session storage
- add manual OpenTelemetry spans around:
  - auth resolution
  - history load
  - RAG retrieval
  - generation
  - persistence
- store `trace_id` on the app chat run row

Optional future step:

- later refactor chat orchestration into an Agno workflow if we want deeper native tracing

---

## 6. Proposed Data Model

Use SQLAlchemy + Alembic for application tables.

### 6.1 `users`

Mirrors the authenticated user at the app layer.

```text
users
- id uuid pk                     # same as Supabase auth.users.id
- email text not null unique
- full_name text null
- avatar_url text null
- auth_provider text null        # google, email, etc.
- is_active boolean not null default true
- created_at timestamptz not null
- updated_at timestamptz not null
- last_seen_at timestamptz null
```

### 6.2 `conversation_sessions`

```text
conversation_sessions
- id uuid pk                     # also used as Agno session_id
- user_id uuid not null fk users.id
- persona_id text not null
- title text null
- status text not null           # active, archived, deleted
- last_message_at timestamptz null
- created_at timestamptz not null
- updated_at timestamptz not null
```

### 6.3 `conversation_messages`

```text
conversation_messages
- id uuid pk
- session_id uuid not null fk conversation_sessions.id
- user_id uuid not null fk users.id
- role text not null             # user, assistant, system
- content text not null
- citations jsonb null
- stats jsonb null
- message_index int not null
- created_at timestamptz not null
```

### 6.4 `conversation_runs`

One row per completed or failed assistant turn.

```text
conversation_runs
- id uuid pk
- session_id uuid not null fk conversation_sessions.id
- user_id uuid not null fk users.id
- persona_id text not null
- agno_run_id text null
- trace_id text null
- model_provider text not null
- model_id text not null
- status text not null           # completed, failed, cancelled
- error_detail text null
- tokens_generated int null
- tokens_per_second float null
- rag_latency_ms int null
- generation_latency_ms int null
- created_at timestamptz not null
- completed_at timestamptz null
```

### 6.5 Optional `user_preferences`

Not required for the first slice, but likely useful soon.

```text
user_preferences
- user_id uuid pk fk users.id
- theme text null
- default_persona_id text null
- created_at timestamptz not null
- updated_at timestamptz not null
```

---

## 7. Supabase Configuration Plan

### 7.1 Frontend Environment

Add to frontend env:

```text
VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
VITE_SUPABASE_REDIRECT_URL=
```

### 7.2 Supabase Dashboard Setup

Configure:

- Email provider enabled
- Google provider enabled
- allowed redirect URLs for local and production frontend origins
- site URL for the app
- email confirmation rules
- password reset redirect URL

### 7.3 Local and Production Topology

Recommended rollout:

- local development:
  - frontend talks to Supabase Auth
  - backend continues to run locally
  - backend DB can remain local Postgres for first implementation
- production/staging:
  - backend can point to Supabase Postgres or another managed Postgres

This avoids blocking local model development on a full Supabase local stack migration.

### 7.4 Security Rules

- Frontend only receives the publishable key.
- Never expose the service role key in the browser.
- Backend service role usage should be avoided unless an admin-only workflow requires it.

---

## 8. Backend Auth Plan

### 8.1 New Modules

Recommended new backend modules:

```text
backend/app/auth/
├── __init__.py
├── models.py          # token claims / current user models
├── verifier.py        # JWT verification against Supabase
├── dependencies.py    # require_current_user()
└── service.py         # upsert user from claims
```

### 8.2 Verification Strategy

Preferred backend behavior:

- verify Supabase access tokens server-side
- resolve the authenticated user from token `sub`
- cache JWKS / signing keys

If local key verification is awkward during early setup, a temporary fallback can call Supabase user verification APIs, but the steady-state target should be local JWT verification plus key caching.

### 8.3 User Bootstrap

On the first authenticated request:

- extract `sub`, `email`, provider metadata from claims
- upsert `users` row
- return a normalized current-user object for the request lifecycle

### 8.4 Request Protection

Require auth for:

- `POST /api/chat`
- `GET /api/sessions`
- `GET /api/sessions/{id}`
- `DELETE /api/sessions/{id}`

Keep anonymous access only where explicitly intended, such as health checks.

---

## 9. API Changes

### 9.1 New or Updated Endpoints

```text
GET    /api/me
POST   /api/chat
GET    /api/sessions
POST   /api/sessions              # optional explicit session creation
GET    /api/sessions/{id}
DELETE /api/sessions/{id}
PATCH  /api/sessions/{id}         # optional rename/archive
```

### 9.2 `POST /api/chat`

Changes:

- require bearer auth
- `session_id` becomes user-owned
- if no `session_id`, backend creates a new `conversation_sessions` row
- before loading history, verify that the session belongs to the current user
- persist both:
  - Agno session history
  - app `conversation_messages` and `conversation_runs`

### 9.3 `GET /api/sessions`

Changes:

- return only sessions for the current user
- support optional filters:
  - `persona_id`
  - `status`

### 9.4 `GET /api/sessions/{id}`

Changes:

- return only if `session.user_id == current_user.id`
- include normalized message history for the frontend

---

## 10. Agno Integration Plan

### 10.1 Keep Current Persona-Agent Registry

Do not create one Agno `Agent` per user.

Keep:

- one agent per persona

Add:

- user-aware session ownership at the app layer

### 10.2 History Loading

Current flow:

- `load_history(agent, session_id)`

Required change:

- first validate `session_id` belongs to `current_user.id`
- then load Agno history

### 10.3 History Persistence

When a turn completes:

1. append messages to Agno session storage
2. insert two app message rows:
   - user message
   - assistant message
3. insert or update a run row with stats and result state
4. update session `last_message_at` and `updated_at`

### 10.4 Trace Correlation

Each chat execution should produce:

- one app run row
- one `trace_id`
- one Agno session update

Store these identifiers together:

- `conversation_runs.trace_id`
- `conversation_runs.agno_run_id`
- `conversation_runs.session_id`
- `conversation_runs.user_id`

### 10.5 Tracing Strategy

Recommended first version:

- initialize Agno/OpenTelemetry tracing once at startup
- create manual spans for the custom chat pipeline
- record `user_id`, `session_id`, `persona_id`, and `run_id` as span attributes

This gives usable tracing now without forcing a risky rewrite of the chat pipeline into `agent.run()`.

---

## 11. Frontend Implementation Plan

### 11.1 New Frontend Modules

```text
frontend/src/
├── auth/
│   ├── AuthProvider.jsx
│   ├── useAuth.js
│   └── AuthGate.jsx
├── lib/
│   ├── supabase.js
│   └── api.js
└── components/
    ├── AuthScreen.jsx
    ├── LoginForm.jsx
    ├── SignupForm.jsx
    └── UserMenu.jsx
```

### 11.2 Auth UX

Minimum UX:

- email/password sign in form
- email/password sign up form
- Google sign in button
- sign out action
- loading state while session restores
- friendly empty state for new users with no conversations

### 11.3 Auth State Handling

Frontend should:

- initialize Supabase once
- restore auth session on load
- subscribe to auth state changes
- clear local chat state on sign out
- stop relying on anonymous `localStorage` session continuity

### 11.4 API Client Changes

Update `frontend/src/lib/api.js` so every authenticated request:

- reads the current Supabase access token
- sends `Authorization: Bearer ...`
- handles `401` by redirecting to auth UI or refreshing session state

### 11.5 Chat UX Changes

Required behavior:

- a new user starts with no history
- session list shows only the logged-in user’s conversations
- switching accounts clears the prior user’s in-memory chat state
- `lumen-session-id` localStorage key should be retired or namespaced by user

---

## 12. Backend Implementation Plan

### Phase A — Foundation

- add SQLAlchemy and Alembic
- add auth package
- add DB session management for app tables
- add current-user dependency

### Phase B — User Model and Session Ownership

- create `users`, `conversation_sessions`, `conversation_messages`, `conversation_runs`
- upsert user on authenticated requests
- require ownership checks on session endpoints

### Phase C — Chat Persistence

- update `/api/chat` to create or validate a user-owned session
- persist app messages and run metadata
- continue persisting Agno session history

### Phase D — Frontend Auth

- add Supabase client
- implement auth screens
- wire bearer auth into API calls
- protect chat UI behind authenticated state

### Phase E — Tracing

- enable tracing startup configuration
- add manual spans to chat flow
- persist `trace_id` on app run rows

### Phase F — Cleanup

- remove anonymous-only assumptions
- remove global session listing behavior
- retire unused `history` request handling if no longer needed

---

## 13. Suggested File-Level Change List

### Backend

Modify:

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/api/models.py`
- `backend/app/api/routes/chat.py`
- `backend/app/api/routes/sessions.py`
- `backend/app/agents/sessions.py`

Create:

- `backend/app/auth/*`
- `backend/app/db/*`
- `backend/app/models/*`
- `backend/alembic/*`

### Frontend

Modify:

- `frontend/src/App.jsx`
- `frontend/src/hooks/useChat.js`
- `frontend/src/lib/api.js`

Create:

- `frontend/src/lib/supabase.js`
- `frontend/src/auth/*`
- auth UI components

---

## 14. Risks and Open Questions

### Risk 1 — Product direction change

Current repository docs describe a single-user local-first product. Supabase Auth introduces an internet dependency and a multi-user direction.

### Risk 2 — Two persistence layers

If we use both Agno tables and app tables, they can drift unless writes are coordinated in one transactional flow as much as possible.

### Risk 3 — Tracing expectations

Agno’s strongest automatic tracing is built around `agent.run()` paths. Our current custom RAG flow will need manual instrumentation for complete coverage.

### Risk 4 — Supabase redirect setup

Google OAuth is sensitive to exact origin and redirect configuration. Localhost, preview, and production URLs need to be planned early.

### Risk 5 — Local development ergonomics

We need to decide whether local development will:

- use a hosted Supabase project
- adopt Supabase CLI locally
- or temporarily mix Supabase Auth with local Postgres

---

## 15. Recommended Delivery Order

1. Backend auth verification and current-user dependency
2. App database layer and migrations
3. User-owned session/message persistence
4. Frontend Supabase auth integration
5. Protected session history UI
6. Trace instrumentation and run correlation

This order keeps the ownership model correct before the frontend starts relying on it.

---

## 16. Definition of Done for This Feature Slice

The first user-capabilities milestone is complete when:

- a user can sign up with email/password
- a user can sign in with email/password
- a user can sign in with Google
- the frontend restores the Supabase session on reload
- authenticated chat requests include a bearer token
- the backend verifies the token and resolves the current user
- chat sessions are visible only to their owner
- each chat turn is stored in both:
  - app-level message/run tables
  - Agno session storage
- each chat run has a correlated `trace_id`
- sign out clears local authenticated chat state

---

## 17. Recommended Next Step

After this planning document is approved, the next implementation document should be a narrower task breakdown for:

- backend auth + schema foundation first
- frontend auth second
- user-scoped chat persistence third

That sequence will reduce rework and keep the authorization boundary correct from the start.

---

## 18. Reference Notes

This plan is aligned with the current official docs at the time of writing:

- Supabase Auth supports Google OAuth and email/password flows in `supabase-js`.
- Supabase access tokens are JWTs and can be verified server-side.
- Agno session storage persists sessions in Postgres-backed tables.
- Agno tracing is OpenTelemetry-based and supports user/session/run correlation, but custom orchestration paths need manual instrumentation for full coverage.
