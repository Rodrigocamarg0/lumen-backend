# Security and Data Privacy Audit

Date: 2026-04-27

Scope: repository-level review of the FastAPI backend, React/Vite frontend, Docker deployment files, authentication, persistence, LLM/RAG flows, and privacy controls. This is a source inspection, not a penetration test.

## Executive Summary

Lumen is not production-ready from a security and privacy standpoint. The most urgent blockers are permissive CORS, unauthenticated search access, default database credentials in production compose, no rate limiting, broad error disclosure, missing browser security headers, and automatic long-term user memory extraction without an explicit consent/retention model.

The project already has good foundations: Supabase bearer authentication is used for chat/session/memory APIs, session ownership checks exist, local `.env` files appear ignored by Git, and user memory list/delete endpoints exist. Production hardening should focus on tightening trust boundaries, reducing data exposure, adding abuse controls, and formalizing privacy obligations before any public launch.

## Production Blockers

| ID | Severity | Finding | Evidence | Required action |
|---|---:|---|---|---|
| SEC-001 | Critical | CORS allows any origin. A hostile website can call browser-accessible API endpoints from a logged-in user's browser if it can obtain or trigger authenticated requests. | `backend/app/main.py:136-140` includes `"*"` in `allow_origins`. | Make CORS environment-specific. In production allow only the real app origin(s), remove `"*"`, and add tests that reject unknown origins. |
| SEC-002 | High | `/api/search` is unauthenticated and returns full corpus text. This exposes backend retrieval capacity and all indexed content to anonymous scraping and automated abuse. | `backend/app/api/routes/search.py:19-60` has no `require_current_user`; response includes `texto`. | Require auth or deliberately mark as public with separate rate limits. Return excerpts by default; expose full text only where needed. |
| SEC-003 | High | Production Docker uses default Postgres credentials (`ai:ai`) and hardcodes the same DSN into the backend. | `docker/docker-compose.prod.yml:5-8`, `docker/docker-compose.prod.yml:30-32`. | Move DB user/password/database into required secrets/env vars. Fail startup if defaults are used in production. Rotate any deployed DB credentials. |
| SEC-004 | High | No API rate limiting, quota, body-rate controls, or concurrency controls were found. Chat and search can burn OpenAI spend, create DB growth, and degrade service. | No limiter middleware/dependency in route registration; chat accepts up to 4096 input chars and 4096 output tokens in `backend/app/api/models.py:16-24`. | Add per-user and per-IP limits for auth, chat, search, sessions, and memories. Add concurrent stream limits and max requests per billing window. |
| SEC-005 | High | Raw internal exception messages are streamed to clients and persisted. This can leak provider errors, stack-adjacent details, or infrastructure information. | `backend/app/api/routes/chat.py:152-165` sends `str(exc)` in SSE and stores it as `error_detail`. Startup logs also include exception text in `backend/app/main.py:73-117`. | Return generic user-facing errors with `trace_id`; keep detailed errors only in protected logs with secret redaction. |
| SEC-006 | High | Automatic summaries and long-term memories are generated from private chat without explicit consent, retention policy, or sensitive-data guardrails enforced in code. | `backend/app/api/routes/chat.py:142-150` schedules context update; `backend/app/agents/context.py:22-50` summarizes and stores memories; `backend/app/llm/context.py:55-117` extracts memories. | Add opt-in consent, visible controls, retention windows, memory review/edit/delete, sensitive-data filters, and privacy policy text before enabling this in production. |
| SEC-007 | High | Chat content, generated summaries, user memories, and run errors are stored in plaintext. | `backend/app/models/conversation.py` stores `content`, `summary`, `memory`, and `error_detail` in text/JSONB columns. | Decide data classification. Add encryption at rest for sensitive fields or use managed DB encryption plus app-level field encryption for chat/memory content. |
| SEC-008 | Medium | Nginx production config lacks security headers and serves over plain HTTP in the provided compose. | `docker/nginx.conf:1-24` has no HSTS, CSP, frame, content-type, referrer, permissions-policy headers. `docker/docker-compose.prod.yml:48-49` exposes port 80. | Terminate TLS and add HSTS. Add CSP, `X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`, and `Permissions-Policy`. |
| SEC-009 | Medium | Containers run as root by default and do not set runtime security restrictions. | `docker/backend.Dockerfile:1-22`, `docker/frontend.Dockerfile:23-26`, compose files have no `user`, `read_only`, `cap_drop`, or `security_opt`. | Run non-root users, drop Linux capabilities, use read-only filesystems where possible, and mount only required writable paths. |
| SEC-010 | Medium | JWT verification allows `HS256` in the JWKS verification path. That is not appropriate for asymmetric JWKS validation and broadens accepted algorithms. | `backend/app/auth/verifier.py:45-53` accepts `["RS256", "ES256", "HS256"]` with a JWKS key. | Split HS256 shared-secret mode from JWKS mode. For Supabase JWKS, allow only the project-supported asymmetric algorithms. |

## Detailed Findings

### Authentication and Authorization

1. Authenticated routes are inconsistently applied. Chat, sessions, `/me`, and memories require `require_current_user`, but search does not. If search is meant to be part of the signed-in product, this is a direct access-control bug.

2. Session ownership checks are present and useful. `get_owned_session()` scopes session reads/deletes to `user_id`, which is the right pattern. Keep this as the standard for every user-owned object.

3. The memory API is authenticated and user-scoped, but only supports list/delete. Production privacy controls should include explicit opt-in, edit, export, and a "disable future memory extraction" setting.

4. Supabase token verification should be stricter. Avoid fallback behavior that tries multiple verification modes for the same token in production. Configure one expected issuer, audience, algorithm family, and project URL.

### Data Privacy

1. Stored data includes user email, full name, avatar URL, chat messages, assistant messages, citations, generation stats, summaries, and inferred memories. This is personal data and, depending on chat content, may include sensitive data.

2. The automatic memory extractor asks the model not to store sensitive data, but that is prompt policy rather than an enforceable privacy control. Add deterministic filters and require user consent before storing inferred preferences or facts.

3. Deleting a session is a soft delete for app sessions. It also deletes summaries and soft-deletes memories sourced from that session, which is good, but production needs a retention job that hard-deletes deleted records after a defined period.

4. There is no documented data retention schedule, export path, account deletion path, breach-response process, or subprocessors/vendor disclosure for OpenAI and Supabase.

5. OpenAI receives the user message, assistant context, summaries, and memory extraction prompts. The privacy policy must disclose this processing, and high-risk content should be minimized before sending.

### API and Abuse Resistance

1. Add rate limits for:
   - login/signup/password-reset flows via Supabase configuration;
   - `/api/chat` by user, IP, and concurrent stream;
   - `/api/search` by user/IP;
   - session and memory list endpoints.

2. Add cost controls:
   - per-user daily/monthly token budgets;
   - hard cap on concurrent OpenAI calls;
   - server-side max output tokens lower than client-controllable defaults for public tiers;
   - alerting for spend anomalies.

3. Add request logging that records trace IDs, user ID hash, route, status, latency, token counts, and model ID without storing full prompts in normal application logs.

4. Add response hardening:
   - generic 500/503 messages;
   - no raw provider errors to browser;
   - trace ID in every error response.

### Frontend Security

1. React rendering mostly avoids raw HTML in `src/`, but generated assistant Markdown can create external links. `rel="noopener noreferrer"` is present, which is good. Add URL scheme filtering so only `http:`, `https:`, `mailto:`, and internal `citation://` links are rendered.

2. Supabase browser sessions are persisted client-side. This is standard for Supabase SPAs, but increases XSS impact. A strict CSP and avoidance of inline scripts are mandatory.

3. Legacy files `frontend/app.js` and `frontend/original_index.html` are still tracked and contain raw `innerHTML` patterns and hardcoded localhost API usage. If these are no longer served, remove them before production to reduce maintenance and accidental deployment risk.

### Infrastructure and Secrets

1. Local `.env` files exist in the workspace but are ignored by Git. Keep them out of commits and scan the repo history before launch.

2. `.env.example` files are tracked, which is appropriate, but production compose should not rely on weak defaults.

3. Add secret scanning to CI, such as Gitleaks or TruffleHog, and run a one-time history scan before production.

4. Use a managed secrets store or deployment secret mechanism rather than bind-mounting `/backend/.env` where practical.

5. Pin Docker base images by digest for reproducibility and supply-chain control, or at least schedule dependency/base image updates with vulnerability scans.

### Database and Migrations

1. The backend creates tables with `Base.metadata.create_all()`. This is convenient for development but insufficient for production schema governance.

2. Add Alembic migrations and deployment checks. Production should not mutate schema implicitly at app startup.

3. Add indexes and constraints for ownership-critical queries and retention jobs. Existing foreign keys and user/session indexes are a good start.

4. Add backup, restore, encryption, and disaster recovery procedures. Test restores before launch.

### LLM and Prompt-Injection Risks

1. Retrieved corpus text and prior chat history are inserted into the model context. Treat all retrieved/user-provided content as untrusted. Strengthen system prompts to ignore instructions found in corpus chunks, user memory, summaries, or citations.

2. Do not store model "thought" or hidden reasoning. The frontend explicitly parses and displays `<|channel>thought` blocks in `frontend/src/components/ChatArea.jsx:13-30`. Production systems should avoid exposing chain-of-thought style content and should filter such markers server-side.

3. Add content safety boundaries for medical, legal, financial, self-harm, and crisis topics. The product domain is religious/spiritual study, but users may ask for high-stakes guidance.

4. Add evaluation tests for prompt injection, privacy leakage, and citation faithfulness.

## Recommended Production Readiness Plan

### P0 - Must Fix Before Any Public Production

1. Remove wildcard CORS and make allowed origins required in production.
2. Require auth for `/api/search` or explicitly public-limit it.
3. Replace default DB credentials and rotate any deployed secrets.
4. Add API rate limits, concurrent stream limits, and OpenAI spend quotas.
5. Stop returning raw exception details to clients.
6. Disable automatic long-term memory by default until consent, retention, and controls are implemented.
7. Add TLS and browser security headers.
8. Add secret scanning and dependency vulnerability scanning to CI.

### P1 - Required For Responsible User Data Handling

1. Add privacy policy, terms, vendor disclosure, and data retention schedule.
2. Add account deletion and data export.
3. Add hard-delete retention jobs for deleted sessions/memories.
4. Add field-level encryption or a documented encryption-at-rest posture for chat and memory data.
5. Add admin access controls and audit logs before any support/admin tooling.
6. Add Alembic migrations and remove production reliance on `create_all()`.

### P2 - Defense In Depth

1. Run containers as non-root with reduced capabilities.
2. Add CSP report-only, tune it, then enforce.
3. Add OpenTelemetry or equivalent tracing with PII-safe attributes.
4. Add prompt-injection and privacy regression tests.
5. Remove tracked legacy frontend files if unused.
6. Add backup/restore drills and incident response runbooks.

## Suggested Acceptance Criteria

Before production launch:

- Unknown browser origins cannot call the API through CORS.
- Every user-data endpoint requires a valid Supabase access token.
- A single user/IP cannot exceed configured chat/search/token budgets.
- Client-facing errors contain no stack traces, provider payloads, DSNs, or secret-adjacent values.
- Users can see, delete, and disable memories; memory extraction is opt-in.
- Session deletion has a documented hard-delete path.
- TLS is enforced and security headers are present.
- CI runs lint/tests, secret scanning, dependency audit, and container scanning.
- Database credentials are unique, strong, rotated, and not hardcoded in compose.
- A privacy policy accurately describes Supabase, OpenAI, stored chat history, summaries, memories, retention, and deletion.
