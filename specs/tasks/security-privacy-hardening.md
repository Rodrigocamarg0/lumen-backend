# Security and Privacy Hardening Tasks

> **Status:** Draft
> **Date:** 2026-04-27
> **Scope:** `backend/`, `frontend/`, `docker/`, CI, and production deployment docs
> **Source:** `docs/security-privacy-audit.md`
> **Goal:** Fix all security issues and production-readiness enhancements found in the audit while keeping local development simple and working.

---

## Implementation Rule

Security hardening must be environment-aware:

- **Local development must keep working** with `localhost` frontend/backend, simple `.env` files, and Docker Compose defaults where they are explicitly development-only.
- **Production must fail closed** when required security configuration is missing or unsafe.
- Do not hardcode production domains, secrets, or credentials in code.
- Add tests for both development and production behavior wherever practical.

Use an explicit setting such as `APP_ENV=local|test|production` or `ENVIRONMENT=local|test|production`. Production-only protections must be keyed off this setting and documented in `.env.example`.

---

## Production Gate

Lumen is not production-ready until all P0 tasks below are complete.

### P0 Blockers

- [x] SEC-001: Restrict CORS in production.
- [x] SEC-002: Authenticate or heavily public-limit `/api/search`.
- [ ] SEC-003: Remove default production database credentials.
- [ ] SEC-004: Add rate limits, concurrency limits, and OpenAI spend controls.
- [x] SEC-005: Stop leaking raw internal errors to clients.
- [ ] SEC-006: Make long-term memory extraction opt-in with retention controls.
- [ ] SEC-007: Protect plaintext chat/memory data with encryption or a documented production encryption posture.
- [ ] SEC-008: Add TLS/security headers for production.

---

## Task Breakdown

### Task 1 — Environment-Aware Security Configuration

**Path:** `backend/app/config.py`, `backend/app/main.py`, `backend/.env.example`, `docker/.env.example`, `docs/vps-deploy.md`

Implement a clear runtime environment model.

- [x] Add an environment setting: `APP_ENV=local|test|production`.
- [x] Add `BACKEND_CORS_ORIGINS` as a comma-separated list.
- [x] In `local` and `test`, allow `http://localhost:3000` and `http://127.0.0.1:3000` by default.
- [x] In `production`, require `BACKEND_CORS_ORIGINS` to be non-empty and reject wildcard origins.
- [x] Fail backend startup in production if dangerous defaults are detected:
  - wildcard CORS;
  - missing Supabase project URL;
  - missing/unsafe database URL;
  - missing OpenAI API key;
  - default database password.
- [x] Update `.env.example` files with safe local examples and production notes.

**Done when:**

- Local dev still works without extra production domain setup.
- Production startup fails fast for missing/unsafe security config.
- Tests cover local permissive defaults and production fail-closed behavior.

---

### Task 2 — CORS Hardening

**Path:** `backend/app/main.py`, backend tests

Replace the current wildcard CORS configuration.

- [x] Remove `"*"` from `allow_origins`.
- [x] Load allowed origins from settings.
- [x] Keep local defaults for Vite dev server.
- [x] Restrict allowed methods to the actual API methods if feasible.
- [x] Keep `Authorization` and `Content-Type` headers enabled.
- [x] Add tests:
  - local origin is allowed in local env;
  - unknown origin is rejected in production env;
  - wildcard origin is rejected at production startup.

**Done when:** Unknown browser origins cannot call authenticated APIs through CORS in production, while local frontend calls still work.

---

### Task 3 — Search Endpoint Access Control

**Path:** `backend/app/api/routes/search.py`, `frontend/src/lib/api.js`, backend tests

Close the anonymous `/api/search` access gap.

- [x] Decide product mode:
  - preferred: require `require_current_user` for `/api/search`;
  - alternative: keep public but add strict anonymous limits and remove full `texto`.
- [x] If authenticated, update frontend search helper to pass the bearer token.
- [x] Return excerpts by default. Only return full text where the UI needs it and the user is authenticated.
- [x] Add tests for missing token, invalid token, and valid token.
- [ ] Confirm no user-owned data is returned across account boundaries.

**Done when:** Search cannot be anonymously scraped in production.

---

### Task 4 — Rate Limits, Quotas, and Stream Concurrency

**Path:** `backend/app/`, `backend/app/api/routes/chat.py`, `backend/app/api/routes/search.py`, config, tests

Add abuse and cost controls.

- [ ] Add per-IP limits for anonymous/public routes.
- [ ] Add per-user limits for authenticated routes.
- [ ] Add chat-specific controls:
  - max concurrent streams per user;
  - max concurrent streams per IP;
  - daily token/request budget;
  - safe server-side max output token cap for production.
- [ ] Add search-specific controls:
  - request rate limit;
  - max `top_k`;
  - timeout guard.
- [ ] Make limits configurable with local-friendly defaults.
- [ ] In local dev, use relaxed defaults so manual testing is not painful.
- [ ] Add structured 429 responses with retry guidance.

**Done when:** A single user/IP cannot exhaust OpenAI spend or service capacity.

---

### Task 5 — Safe Error Handling and Trace IDs

**Path:** `backend/app/api/routes/chat.py`, `backend/app/main.py`, route helpers, tests

Prevent internal details from reaching clients.

- [x] Add a request/response trace ID strategy.
- [x] Include `trace_id` in chat SSE session/error events.
- [x] Replace `str(exc)` in client-facing responses with generic messages.
- [x] Store detailed errors only in protected logs or sanitized DB fields.
- [ ] Redact secrets, DSNs, tokens, and provider payloads from logs.
- [ ] Add tests that provider exceptions do not leak raw text to clients.

**Done when:** Client-facing errors contain no stack traces, DSNs, provider internals, or secret-adjacent values.

---

### Task 6 — Memory Consent and Privacy Controls

**Path:** `backend/app/agents/context.py`, `backend/app/api/routes/memories.py`, `backend/app/models/`, `frontend/src/`, tests

Make long-term memory safe and user-controlled.

- [ ] Add a user setting for memory extraction consent.
- [ ] Default memory extraction to **off** for existing and new users unless explicitly enabled.
- [ ] Do not run `update_context_after_turn()` unless consent is enabled.
- [ ] Add frontend controls to:
  - enable/disable memory;
  - list memories;
  - delete memories;
  - explain what memory stores in plain language.
- [ ] Add backend endpoints for memory settings.
- [ ] Add deterministic sensitive-data filters before storing memories.
- [ ] Add a retention policy for memories.
- [ ] Add tests for disabled consent, enabled consent, delete, and ownership.

**Done when:** The product can keep conversation history without silently creating long-term memories.

---

### Task 7 — Data Retention, Deletion, and Export

**Path:** `backend/app/db/`, `backend/app/api/routes/`, `frontend/src/`, docs, tests

Implement user data lifecycle controls.

- [ ] Define retention periods for:
  - active sessions;
  - deleted sessions;
  - failed run records;
  - summaries;
  - memories;
  - logs.
- [ ] Add hard-delete job or management command for expired deleted records.
- [ ] Add user data export endpoint for sessions/messages/memories/profile metadata.
- [ ] Add account deletion workflow or documented Supabase-backed process.
- [ ] Ensure session deletion removes or anonymizes related summaries and memories.
- [ ] Add tests for hard-delete and export ownership.

**Done when:** Users can understand, export, delete, and expire their stored data.

---

### Task 8 — Data Encryption and Storage Hardening

**Path:** `backend/app/models/`, `backend/app/db/`, deployment docs

Protect stored chat and memory data.

- [ ] Decide and document the production encryption model:
  - managed Postgres encryption at rest plus strict DB access controls; or
  - app-level field encryption for chat/memory/summary fields.
- [ ] If using app-level encryption, add key management via production secrets.
- [ ] Never store encryption keys in repo or Docker images.
- [ ] Add migration/backfill plan for existing plaintext data.
- [ ] Add tests for encrypt/decrypt and key-missing production startup failure.

**Done when:** Production has a defensible encryption posture for user conversation and memory data.

---

### Task 9 — Production Docker and Database Secrets

**Path:** `docker/docker-compose.prod.yml`, `docker/backend.Dockerfile`, `docker/frontend.Dockerfile`, `docker/.env.example`, docs

Remove unsafe production defaults.

- [ ] Replace hardcoded `POSTGRES_PASSWORD=ai` with required env var.
- [ ] Build `DATABASE_URL` from required production variables or inject a single required secret.
- [ ] Fail production compose if DB credentials are missing.
- [ ] Keep development compose convenient, but clearly label dev-only defaults.
- [ ] Run backend container as non-root.
- [ ] Run frontend/nginx container as non-root where possible.
- [ ] Add `cap_drop`, `security_opt`, and read-only filesystem settings where compatible.
- [ ] Pin or regularly scan base images.

**Done when:** Production deploy cannot accidentally use `ai:ai` or root-default containers without an explicit exception.

---

### Task 10 — Nginx, TLS, and Browser Security Headers

**Path:** `docker/nginx.conf`, production docs

Add production web hardening without breaking local Docker.

- [ ] Add production security headers:
  - `Content-Security-Policy`;
  - `X-Content-Type-Options`;
  - `Referrer-Policy`;
  - `Permissions-Policy`;
  - `X-Frame-Options` or CSP `frame-ancestors`;
  - HSTS when HTTPS is used.
- [ ] Document local behavior separately from production behavior.
- [ ] Add TLS termination guidance:
  - reverse proxy with certificates; or
  - managed platform/load balancer.
- [ ] Ensure SSE streaming still works through nginx after header changes.
- [ ] Validate frontend still loads Supabase and app assets under CSP.

**Done when:** Production responses include security headers and HTTPS is required.

---

### Task 11 — JWT Verification Hardening

**Path:** `backend/app/auth/verifier.py`, tests

Tighten Supabase token validation.

- [ ] Split HS256 shared-secret verification from JWKS verification.
- [ ] In JWKS mode, remove `HS256` from accepted algorithms.
- [ ] Require issuer verification in production.
- [ ] Require audience verification in production.
- [ ] Add tests for:
  - wrong issuer;
  - wrong audience;
  - unsupported algorithm;
  - missing required claims.

**Done when:** Tokens are accepted only from the configured Supabase project and expected algorithm family.

---

### Task 12 — Frontend XSS and Markdown Link Safety

**Path:** `frontend/src/components/ChatArea.jsx`, frontend tests if available

Reduce XSS impact in assistant-rendered content.

- [ ] Filter rendered Markdown links by scheme.
- [ ] Allow only:
  - `http:`;
  - `https:`;
  - `mailto:`;
  - internal `citation://`.
- [ ] Block `javascript:`, `data:`, and unknown schemes.
- [ ] Keep `rel="noopener noreferrer"` for external links.
- [ ] Verify Supabase persisted browser sessions still work under CSP.
- [ ] Remove unused tracked legacy files if they are no longer served:
  - `frontend/app.js`;
  - `frontend/original_index.html`.

**Done when:** Model-generated Markdown cannot create unsafe browser links.

---

### Task 13 — Chain-of-Thought and Hidden Reasoning Filtering

**Path:** `backend/app/llm/engine.py`, `backend/app/persona/rag.py`, `frontend/src/components/ChatArea.jsx`, tests

Do not expose model hidden reasoning.

- [ ] Filter known reasoning markers server-side before streaming to the client.
- [ ] Remove or disable UI that displays `<|channel>thought` content in production.
- [ ] Add tests using mocked model output containing thought markers.
- [ ] Keep local debugging possible behind an explicit non-production debug flag if needed.

**Done when:** Production users never receive or store hidden reasoning text.

---

### Task 14 — CI Security Checks

**Path:** `.github/workflows/`, `.pre-commit-config.yaml`, docs

Add automated security checks.

- [ ] Add secret scanning with Gitleaks or equivalent.
- [ ] Add Python dependency vulnerability scanning.
- [ ] Add npm audit or equivalent frontend dependency scanning.
- [ ] Add Docker image scan in CI or deployment pipeline.
- [ ] Run a one-time Git history secret scan before production.
- [ ] Document how to rotate secrets if a leak is found.

**Done when:** Pull requests fail on newly introduced secrets or known high-risk dependency vulnerabilities.

---

### Task 15 — Database Migrations and Production Schema Governance

**Path:** `backend/`, `pyproject.toml`, docs

Replace implicit production schema mutation with migrations.

- [ ] Add Alembic.
- [ ] Generate an initial migration for current SQLAlchemy models.
- [ ] Keep `create_all()` only for local/test or remove it after migrations are wired.
- [ ] Add deployment steps for migration execution.
- [ ] Add migration check in CI.

**Done when:** Production schema changes are explicit, reviewed, and reproducible.

---

### Task 16 — Privacy and Incident Documentation

**Path:** `docs/`

Document operational privacy requirements.

- [ ] Add privacy policy draft covering:
  - Supabase Auth;
  - OpenAI processing;
  - stored chat history;
  - summaries;
  - memories;
  - retention;
  - deletion/export;
  - subprocessors.
- [ ] Add data classification document.
- [ ] Add incident response runbook.
- [ ] Add backup/restore runbook.
- [ ] Add production access policy for database/logs.

**Done when:** Production operators and users have clear privacy/security expectations.

---

## Suggested Agent Ownership

Split work across agents by file ownership to reduce conflicts:

- **Backend security agent:** Tasks 1-8, 11, 13, 15.
- **Frontend security agent:** Tasks 6, 7 frontend pieces, 10 validation, 12, 13 UI pieces.
- **Infrastructure agent:** Tasks 9, 10, 14, 16.
- **QA/security validation agent:** cross-cutting tests, abuse cases, and production gate validation.

Agents must not weaken local development flows. Any production-only security requirement should be controlled by environment settings and documented in `.env.example`.

---

## Final Acceptance Checklist

- [ ] Local: `frontend` dev server can call local backend without custom production domains.
- [ ] Local: Docker Compose dev can start with documented development defaults.
- [ ] Production: backend rejects wildcard CORS and unsafe defaults.
- [ ] Production: all user-data endpoints require valid auth or have documented public limits.
- [ ] Production: rate limits and token budgets are active.
- [ ] Production: no raw internal errors reach clients.
- [ ] Production: memory extraction is opt-in and user-controllable.
- [ ] Production: data retention, export, and deletion are implemented.
- [ ] Production: database credentials are strong and not hardcoded.
- [ ] Production: TLS and security headers are configured.
- [ ] Production: JWT validation is strict.
- [ ] Production: unsafe Markdown links are blocked.
- [ ] Production: hidden reasoning is not streamed, displayed, or stored.
- [ ] CI: secret/dependency/container security checks run.
- [ ] Docs: privacy policy, incident response, and backup/restore runbooks exist.
