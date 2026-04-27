# VPS Deployment — chat-trainer

## Infrastructure Overview

| Component | Details |
|---|---|
| VPS IP | `145.223.93.104` |
| OS | Ubuntu 24.04 LTS |
| Reverse proxy | Traefik v3 (Docker) |
| SSL/TLS | Cloudflare (terminates HTTPS, forwards HTTP to VPS) |
| Domain | `chat-trainer.elia.com.de` |
| Project path | `/home/rodrigo/projects/chat-trainer/` |

---

## Architecture

```
Internet → Cloudflare (SSL) → VPS :80 → Traefik → chat-trainer-frontend :3000
                                                  → chat-trainer-api :8000 (internal)
                                                  → chat-trainer-whatsapp :3002 (internal)
                                                  → chat-trainer-mongo :27017 (internal)
```

Traefik discovers services automatically via Docker labels on the `proxy` external network.
Only `chat-trainer-frontend` is on the `proxy` network and exposed publicly.

---

## Services

| Container | Image | Internal port | Notes |
|---|---|---|---|
| `chat-trainer-frontend` | Next.js (custom) | 3000 | Public via Traefik |
| `chat-trainer-api` | FastAPI + uv (custom) | 8000 | Internal only |
| `chat-trainer-whatsapp` | Baileys bridge (custom) | 3002 | Internal only |
| `chat-trainer-mongo` | `mongo:7` | 27017 | Internal only, volume persisted |

---

## Secrets File — `.env.prod`

Located at `/home/rodrigo/projects/chat-trainer/.env.prod` (never committed to git).

```env
# MongoDB
MONGODB_URL=mongodb://mongo:27017
DATABASE_NAME=personal_trainer_ai
MONGODB_DB=personal_trainer_ai
WHATSAPP_MESSAGES_TTL_DAYS=30
TELEGRAM_MESSAGES_TTL_DAYS=30
AUDIT_LOGS_TTL_DAYS=180
AGENT_SESSIONS_TTL_DAYS=0
AGENT_MEMORY_TTL_DAYS=0

# OpenAI
OPENAI_API_KEY=sk-proj-...

# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGci...   ← must be JWT format (not sb_publishable_)
SUPABASE_DB_PASSWORD=...

# Admin access (semicolon-separated emails)
ADMIN_EMAILS=you@example.com

# WhatsApp service (internal docker network)
WHATSAPP_SERVICE_URL=http://whatsapp:3002
```

> **Supabase key**: copy the `anon public` key from Supabase → Settings → API.
> It must start with `eyJhbGci...`. The `sb_publishable_` key is NOT valid here.

Retention defaults:
- `WHATSAPP_MESSAGES_TTL_DAYS=30`: auto-expires WhatsApp message logs after 30 days
- `TELEGRAM_MESSAGES_TTL_DAYS=30`: auto-expires Telegram message logs after 30 days
- `AUDIT_LOGS_TTL_DAYS=180`: auto-expires audit logs after 180 days
- `AGENT_SESSIONS_TTL_DAYS=0`: disabled by default
- `AGENT_MEMORY_TTL_DAYS=0`: disabled by default

Use `0` to disable automatic expiration for any of the TTL settings.

---

## Deploying an Update

The VPS has no GitHub SSH access. Updates are deployed by **rsyncing from local** then rebuilding on the VPS.

### From your Mac (local machine):

**1. Sync code (run from project root):**
```bash
rsync -av \
  -e "sshpass -p 'guigo2119' ssh -o StrictHostKeyChecking=no" \
  --exclude '.venv' --exclude 'node_modules' --exclude '.next' \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.git' \
  --exclude 'dist' --exclude 'mongo_data' \
  --exclude '.env' --exclude '.env.prod' \
  /Users/Rodrigo/CMP/personal/ \
  root@145.223.93.104:/home/rodrigo/projects/chat-trainer/
```

**2. SSH in and rebuild:**
```bash
ssh root@145.223.93.104
cd /home/rodrigo/projects/chat-trainer
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

### Rebuild only frontend (e.g. after UI changes):
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build frontend
```

### Rebuild only API (e.g. after Python changes):
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build api
```

### Rebuild only Mongo service config changes:
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d mongo
```

---

## Critical: `--env-file .env.prod` is Required

`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are baked into the
Next.js bundle at **build time** via Docker build ARGs. They are NOT injected at runtime.

The `env_file:` directive in `docker-compose.prod.yml` only applies to **runtime** env vars,
not to the `args:` interpolation. Without `--env-file .env.prod` on the CLI, compose
treats those vars as empty strings and bakes blanks into the bundle — Supabase auth silently breaks.

**Always use:**
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```
**Never use:**
```bash
docker compose -f docker-compose.prod.yml up -d --build   # ← WRONG, breaks auth
```

---

## Verify Deployment

```bash
# All containers running?
docker ps --format "table {{.Names}}\t{{.Status}}" | grep chat-trainer

# Traefik picked up the route?
curl -s http://localhost:8080/api/http/routers | \
  python3 -c "import sys,json; [print(r['name'],'->', r.get('rule','')) for r in json.load(sys.stdin) if 'chat-trainer' in r['name']]"

# Supabase key valid?
KEY=$(grep NEXT_PUBLIC_SUPABASE_ANON_KEY .env.prod | cut -d= -f2)
curl -s "https://<project>.supabase.co/auth/v1/settings" -H "apikey: $KEY" | python3 -m json.tool

# NEXT_PUBLIC vars baked into frontend?
docker run --rm chat-trainer-frontend sh -c \
  "grep -r 'your-supabase-project-id' /app/.next/static/ | head -1 | cut -c1-80"

# API responding (via internal network)?
docker logs chat-trainer-api --tail 20
```

---

## Disk Monitoring and Mongo Growth

Use the maintenance script from the project root on the VPS:

```bash
cd /home/rodrigo/projects/chat-trainer
uv run python scripts/storage_report.py --env-file .env.prod --mongo-url mongodb://localhost:27017 --limit 20
```

What it shows:
- host filesystem usage
- `docker system df`
- top Docker volumes by size
- MongoDB collections sorted by storage size

Notes:
- On the VPS, prefer `--mongo-url mongodb://localhost:27017` when running from the host shell
- `MONGODB_URL=mongodb://mongo:27017` is correct for containers, but `mongo` usually does not resolve from the host shell

Useful manual checks:

```bash
df -h
docker system df
docker ps --format "table {{.Names}}\t{{.Status}}"
docker volume ls
du -sh /var/lib/docker/volumes/* 2>/dev/null | sort -h | tail -20
```

---

## Mongo Out Of Space Recovery

If MongoDB starts crashing with `WiredTiger`, `WT_PANIC`, or `No space left on device`, treat it as a host disk exhaustion issue first.

Immediate triage:

```bash
df -h
docker system df
docker logs chat-trainer-mongo --tail 100
```

Recovery flow:
1. Free disk space on the host before restarting MongoDB.
2. Re-run the storage report to confirm where the pressure is coming from.
3. Restart Mongo:
   ```bash
   docker compose --env-file .env.prod -f docker-compose.prod.yml restart mongo
   ```
4. If Mongo still fails after space has been freed, inspect the volume before attempting repair.

Potential disk consumers in this stack:
- `mongo_data` volume growth from `whatsapp_messages`, `telegram_messages`, `agent_sessions`, and `agent_long_term_memory`
- Docker image/build cache
- container json logs

Safe cleanup candidates:

```bash
docker image prune -a
docker builder prune
docker container prune
```

Be careful with Docker prune commands on a shared VPS. Review what will be deleted before confirming.

---

## Container Log Rotation

`docker-compose.yml` and `docker-compose.prod.yml` now configure Docker json log rotation for all app services:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
```

This caps per-container log retention to roughly 50 MB and prevents unbounded log growth on the host.

---

## DNS Configuration (Cloudflare)

To add a new subdomain:
1. Cloudflare dashboard → `elia.com.de` → DNS → Records
2. Add record:
   - **Type**: `A`
   - **Name**: `chat-trainer` (or whatever subdomain)
   - **IPv4**: `145.223.93.104`
   - **Proxy**: On (orange cloud)
   - **TTL**: Auto
3. Propagates in < 1 minute with Cloudflare

---

## Setting Up GitHub Access on VPS (optional, for `git pull`)

Currently the VPS has no GitHub SSH key. To enable direct `git pull`:

```bash
# On the VPS as root:
ssh-keygen -t ed25519 -C "chat-trainer-vps" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

Add the printed public key to GitHub:
→ `github.com/Rodrigocamarg0/chat-trainer` → Settings → Deploy keys → Add key

Then configure git to use it:
```bash
git clone git@github.com:Rodrigocamarg0/chat-trainer.git /home/rodrigo/projects/chat-trainer
```

Future updates would then just be:
```bash
cd /home/rodrigo/projects/chat-trainer
git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

---

## Known Gotchas

| Issue | Cause | Fix |
|---|---|---|
| `NEXT_PUBLIC_*` empty in browser | Forgot `--env-file` on compose command | Always use `--env-file .env.prod` |
| `Invalid API key` from Supabase | Using `sb_publishable_` key instead of JWT anon key | Get `eyJhbGci...` key from Supabase dashboard |
| `curl localhost:8000` returns wrong app | money-chat-ai also exposes port 8000 on host | Test via `docker logs` or internal exec instead |
| GitHub clone fails on VPS | No SSH deploy key configured | Use rsync from local (see deploy steps above) |
| `chown` permission denied on project files | Files owned by root after rsync | Run `chown -R rodrigo:rodrigo /home/rodrigo/projects/chat-trainer` as root |
| Mongo exits with `WT_PANIC` / `No space left on device` | Host disk full, usually under Docker storage | Free disk space first, then restart `mongo` |
| `scripts/storage_report.py` cannot reach Mongo on the VPS | Host shell cannot resolve `mongo` service name | Use `--mongo-url mongodb://localhost:27017` |
