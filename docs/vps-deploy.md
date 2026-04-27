# VPS Deploy — Lumen

## Infrastructure

| Component | Details |
|---|---|
| VPS IP | `145.223.93.104` |
| OS | Ubuntu 24.04 LTS |
| User | `root` (rsync), files owned by `rodrigo` |
| Reverse proxy | Traefik v3 (Docker, shared with chat-trainer) |
| SSL/TLS | Cloudflare (terminates HTTPS, forwards HTTP to VPS) |
| Domain | `lumen.kardechat.com.br` |
| Project path | `/home/rodrigo/projects/lumen/` |

The VPS is shared with the `chat-trainer` project. Traefik routes requests by `Host()` rule.
See `docs/vps-deploy-personal.md` for full VPS context.

---

## Quick Deploy (automated — rsync)

```bash
# First-time setup (creates dirs on VPS, rsyncs code + env):
./deploy.sh --setup

# Full deploy (rsync → env sync → docker build → verify):
./deploy.sh

# Partial operations:
./deploy.sh --sync              # rsync code + env only (no rebuild)
./deploy.sh --sync-env          # sync env files only
./deploy.sh --build             # rebuild all on VPS (no sync)
./deploy.sh --build backend     # rebuild one service
./deploy.sh --build frontend    # rebuild one service

# Monitoring:
./deploy.sh --status            # container health
./deploy.sh --logs              # tail all logs
./deploy.sh --logs backend      # tail one service
./deploy.sh --disk              # VPS disk usage
./deploy.sh --ssh               # open interactive SSH
```

The script uses **rsync** + **sshpass** to push your local working tree directly to the VPS.
No git push required — uncommitted changes are deployed as-is. Env files are synced
separately with automatic production overrides (`DATABASE_URL` rewrite, VPS paths, ports).

---

## Manual Steps (reference)

### 1. Sync code to VPS

```bash
rsync -azP \
  -e "sshpass -p 'guigo2119' ssh -o StrictHostKeyChecking=no" \
  --exclude '.git' --exclude '.env' --exclude '.env.*' \
  --exclude '__pycache__' --exclude 'node_modules' --exclude 'dist' \
  --exclude '.venv' --exclude 'backend/data' --exclude '*.bin' \
  /Users/Rodrigo/CMP/lumen/ \
  root@145.223.93.104:/home/rodrigo/projects/lumen/
```

### 2. Create the Docker deploy env

`docker/.env` on VPS:

```env
COMPOSE_PROJECT_NAME=lumen
LUMEN_APP_PATH=/home/rodrigo/projects/lumen
LUMEN_FRONTEND_PORT=80
LUMEN_BACKEND_BIND=127.0.0.1
LUMEN_BACKEND_PORT=8000
LUMEN_POSTGRES_BIND=127.0.0.1
LUMEN_POSTGRES_PORT=5532
VITE_SUPABASE_URL=https://dpsgppujmlnwxfbobcii.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_Q_O18LnWCSIuOpTZ6MHTRA_zBJnbzCm
VITE_SUPABASE_REDIRECT_URL=https://lumen.kardechat.com.br
VITE_API_BASE=
VITE_ENABLED_PERSONAS=kardec
```

### 3. Create the backend runtime env

`backend/.env` on VPS (note `DATABASE_URL` uses `postgres`, not `localhost`):

```env
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4.1-nano
OPENAI_API_KEY=your_openai_key
EMBEDDING_MODEL=text-embedding-3-small
ENABLED_PERSONAS=kardec
DATABASE_URL=postgresql+psycopg://ai:ai@postgres:5432/ai
SUPABASE_URL=https://dpsgppujmlnwxfbobcii.supabase.co
SUPABASE_JWT_SECRET=your_supabase_jwt_secret
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_VERIFY_ISSUER=true
```

### 4. Start the Production Stack

```bash
ssh root@145.223.93.104
cd /home/rodrigo/projects/lumen/docker
docker compose -f docker-compose.prod.yml up -d --build
```

Rebuild a single service:
```bash
docker compose -f docker-compose.prod.yml up -d --build backend
docker compose -f docker-compose.prod.yml up -d --build frontend
```

### 5. Verify

```bash
docker compose -f docker-compose.prod.yml ps
curl http://127.0.0.1:8000/api/health
```

---

## Architecture

```
Internet → Cloudflare (SSL) → VPS :80 → Traefik → lumen-frontend :80 (nginx)
                                                  → lumen-backend :8000 (via nginx /api/ proxy)
                                                  → lumen-postgres :5432 (internal only)
```

The frontend nginx container handles both static assets and `/api/*` reverse proxy to the backend.
Traefik routes `Host(\`lumen.kardechat.com.br\`)` to the frontend container on the `proxy` network.

---

## Notes

- Inside Docker, `DATABASE_URL` must point to `postgres`, not `localhost`.
- The frontend `VITE_SUPABASE_*` values are build-time Docker args from `docker/.env`.
- The backend `SUPABASE_*` values are runtime auth verification settings from `backend/.env`.
- Keep secrets on the VPS only. Do not commit `.env` files.
- Files are rsynced as `root` then `chown`ed to `rodrigo:rodrigo`.
- The `proxy` Docker network is shared with `chat-trainer` on the same VPS.

For local development use the local compose file:

```bash
cd /Users/Rodrigo/CMP/lumen/docker
docker compose -f docker-compose.yml up -d --build
```
