# VPS Deploy — Lumen

This project can be deployed on the VPS under:

`/home/rodrigo/projects/lumen`

The Docker Compose files now expect that path through `docker/.env`, so the repo path is explicit and can be changed later without editing the compose files.

## 1. Copy the project to the VPS

```bash
mkdir -p /home/rodrigo/projects
cd /home/rodrigo/projects
git clone <your-repo-url> lumen
cd /home/rodrigo/projects/lumen
```

## 2. Create the Docker deploy env

```bash
cd /home/rodrigo/projects/lumen/docker
cp .env.example .env
```

Default `docker/.env`:

```env
COMPOSE_PROJECT_NAME=lumen
LUMEN_APP_PATH=/home/rodrigo/projects/lumen
LUMEN_FRONTEND_PORT=80
LUMEN_BACKEND_BIND=127.0.0.1
LUMEN_BACKEND_PORT=8000
LUMEN_POSTGRES_BIND=127.0.0.1
LUMEN_POSTGRES_PORT=5532
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=your_publishable_key
VITE_SUPABASE_REDIRECT_URL=http://localhost:3000
VITE_API_BASE=
VITE_ENABLED_PERSONAS=kardec
```

## 3. Create the backend runtime env

Create `/home/rodrigo/projects/lumen/backend/.env`.

Minimum CPU/OpenAI example:

```env
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4.1-nano
OPENAI_API_KEY=your_openai_key
EMBEDDING_MODEL=text-embedding-3-small
ENABLED_PERSONAS=kardec
DATABASE_URL=postgresql+psycopg://ai:ai@postgres:5432/ai
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_JWT_SECRET=your_supabase_jwt_secret_if_using_hs256
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_VERIFY_ISSUER=true
```

Notes:
- Inside Docker, `DATABASE_URL` must point to `postgres`, not `localhost`.
- The frontend `VITE_SUPABASE_*` values are build-time Docker args from `docker/.env`.
- The backend `SUPABASE_*` values are runtime auth verification settings from `backend/.env`.
- Keep the backend `.env` on the VPS only. Do not commit secrets.

## 4. Start the Production Stack

Production uses external OpenAI models only:

```bash
cd /home/rodrigo/projects/lumen/docker
docker compose -f docker-compose.prod.yml up -d --build
```

For local development use the local compose file:

```bash
cd /Users/Rodrigo/CMP/lumen/docker
docker compose -f docker-compose.yml up -d --build
```

## 5. Verify

```bash
docker compose -f docker-compose.prod.yml ps
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1/
```

Expected exposure:
- Frontend: `http://<VPS-IP>:80`
- Backend: `127.0.0.1:8000`
- Postgres: `127.0.0.1:5532`

The frontend container builds the React app on the VPS and nginx proxies `/api/*` to the backend, so the browser uses a single origin in production.
