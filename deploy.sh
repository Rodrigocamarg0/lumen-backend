#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# deploy.sh — Automated production deployment for Lumen (rsync-based)
#
# Usage:
#   ./deploy.sh                 # full deploy (rsync + build + verify)
#   ./deploy.sh --setup         # first-time VPS setup (dirs, sync, proxy net)
#   ./deploy.sh --sync          # rsync code + env only (no rebuild)
#   ./deploy.sh --sync-env      # only sync env files (no code, no rebuild)
#   ./deploy.sh --build         # rebuild on VPS (no sync)
#   ./deploy.sh --build backend # rebuild only one service
#   ./deploy.sh --logs          # tail production logs
#   ./deploy.sh --logs backend  # tail one service
#   ./deploy.sh --status        # container status + health
#   ./deploy.sh --ssh           # open interactive SSH session
#   ./deploy.sh --disk          # show VPS disk usage
#
# Prerequisites:
#   - sshpass installed locally (brew install hudochenkov/sshpass/sshpass)
#   - Local backend/.env has production secrets
#   - Local docker/.env has build-time VITE_* values
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# VPS connection (same VPS as chat-trainer).
VPS_HOST="${LUMEN_VPS_HOST:-145.223.93.104}"
VPS_USER="${LUMEN_VPS_USER:-root}"
VPS_PASS="${LUMEN_VPS_PASS:-guigo2119}"

# Remote paths (must match docs/vps-deploy.md).
REMOTE_PROJECT_DIR="/home/rodrigo/projects/lumen"
REMOTE_DOCKER_DIR="${REMOTE_PROJECT_DIR}/docker"

# Compose file
COMPOSE_FILE="docker-compose.prod.yml"

# File owner on VPS (app runs under this user; rsync as root then chown).
REMOTE_OWNER="rodrigo"

# ── Rsync excludes ───────────────────────────────────────────────────
RSYNC_EXCLUDES=(
    # Env files (synced separately with production overrides)
    ".env"
    ".env.*"
    "!.env.example"
    # Python artifacts
    "__pycache__/"
    "*.py[cod]"
    "*.pyo"
    "*.pyd"
    ".Python"
    "*.egg-info/"
    "dist/"
    "build/"
    ".eggs/"
    # Virtual environments
    "backend/venv/"
    "venv/"
    ".venv/"
    "env/"
    # Generated data (large, rebuilt via ingest on VPS if needed)
    "backend/data/"
    "books/"
    # Frontend build output and deps (rebuilt in Docker)
    "frontend/node_modules/"
    "frontend/dist/"
    # Model files (too large)
    "*.bin"
    "*.safetensors"
    "*.gguf"
    # IDE / OS junk
    ".DS_Store"
    "*.swp"
    "*.swo"
    ".idea/"
    ".vscode/"
    "*.log"
    # Git internals
    ".git/"
    # AI agent data
    ".gemini/"
)

# ── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ──────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}ℹ${NC}  $*"; }
success() { echo -e "${GREEN}✔${NC}  $*"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $*"; }
error()   { echo -e "${RED}✖${NC}  $*" >&2; }
header()  { echo -e "\n${BOLD}${CYAN}── $* ──${NC}\n"; }

# SSH/SCP/rsync wrappers using sshpass for password auth.
_ssh_base="sshpass -p ${VPS_PASS} ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"

ssh_cmd() {
    ${_ssh_base} "${VPS_USER}@${VPS_HOST}" "$@"
}

scp_cmd() {
    sshpass -p "${VPS_PASS}" scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$@"
}

rsync_cmd() {
    local -a rsync_opts=(
        -azP
        --delete
        --delete-excluded
        -e "sshpass -p '${VPS_PASS}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
    )
    for pattern in "${RSYNC_EXCLUDES[@]}"; do
        rsync_opts+=(--exclude="$pattern")
    done
    rsync "${rsync_opts[@]}" "$@"
}

# ── Pre-flight checks ───────────────────────────────────────────────
preflight() {
    header "Pre-flight checks"

    # Repo root
    if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
        error "deploy.sh must live in the Lumen repo root (pyproject.toml not found)"
        exit 1
    fi

    # sshpass
    if ! command -v sshpass &>/dev/null; then
        error "sshpass is not installed. Install with: brew install hudochenkov/sshpass/sshpass"
        exit 1
    fi

    # rsync
    if ! command -v rsync &>/dev/null; then
        error "rsync is not installed"
        exit 1
    fi

    # SSH connectivity
    info "Testing SSH to ${VPS_USER}@${VPS_HOST} ..."
    if ! ssh_cmd "echo ok" &>/dev/null; then
        error "Cannot SSH into ${VPS_USER}@${VPS_HOST}"
        echo ""
        echo "  Troubleshooting:"
        echo "    1. Is the VPS reachable? ping ${VPS_HOST}"
        echo "    2. Is the password correct? Set LUMEN_VPS_PASS=<password>"
        echo "    3. Is port 22 open?"
        echo "    4. Run: sshpass -p '${VPS_PASS}' ssh -v ${VPS_USER}@${VPS_HOST}"
        echo ""
        exit 1
    fi
    success "SSH connection OK"

    # Local env files
    if [[ ! -f "$SCRIPT_DIR/backend/.env" ]]; then
        error "backend/.env not found — secrets are required for deployment"
        exit 1
    fi
    if [[ ! -f "$SCRIPT_DIR/docker/.env" ]]; then
        error "docker/.env not found — build-time config is required"
        exit 1
    fi
    success "Local env files found"
}

# ── Rsync project code ──────────────────────────────────────────────
sync_code() {
    header "Syncing code via rsync"

    info "Syncing ${SCRIPT_DIR}/ → ${VPS_HOST}:${REMOTE_PROJECT_DIR}/"
    rsync_cmd "${SCRIPT_DIR}/" "${VPS_USER}@${VPS_HOST}:${REMOTE_PROJECT_DIR}/"

    # Fix ownership (rsync as root creates root-owned files)
    info "Fixing file ownership → ${REMOTE_OWNER}:${REMOTE_OWNER} ..."
    ssh_cmd "chown -R ${REMOTE_OWNER}:${REMOTE_OWNER} ${REMOTE_PROJECT_DIR}"

    success "Code synced to VPS"
}

# ── Sync env files (with production overrides) ───────────────────────
sync_env() {
    header "Syncing env files to VPS"

    # -- backend/.env: rewrite DATABASE_URL for Docker internal networking --
    local tmp_backend_env
    tmp_backend_env=$(mktemp)
    sed 's|postgresql+psycopg://ai:ai@localhost:5532/ai|postgresql+psycopg://ai:ai@postgres:5432/ai|g' \
        "$SCRIPT_DIR/backend/.env" > "$tmp_backend_env"
    if grep -q '@localhost:' "$tmp_backend_env"; then
        sed -i.bak 's|@localhost:[0-9]*/|@postgres:5432/|g' "$tmp_backend_env"
        rm -f "${tmp_backend_env}.bak"
    fi

    info "Uploading backend/.env (secrets, Docker DATABASE_URL) ..."
    scp_cmd "$tmp_backend_env" "${VPS_USER}@${VPS_HOST}:${REMOTE_PROJECT_DIR}/backend/.env"
    rm -f "$tmp_backend_env"
    success "backend/.env synced"

    # -- docker/.env: override paths/ports for production --
    local tmp_docker_env
    tmp_docker_env=$(mktemp)
    cp "$SCRIPT_DIR/docker/.env" "$tmp_docker_env"

    # Production overrides
    sed -i.bak "s|^LUMEN_APP_PATH=.*|LUMEN_APP_PATH=${REMOTE_PROJECT_DIR}|" "$tmp_docker_env"
    sed -i.bak 's|^LUMEN_FRONTEND_PORT=.*|LUMEN_FRONTEND_PORT=80|' "$tmp_docker_env"
    sed -i.bak 's|^VITE_SUPABASE_REDIRECT_URL=.*|VITE_SUPABASE_REDIRECT_URL=https://lumen.kardechat.com.br|' "$tmp_docker_env"
    rm -f "${tmp_docker_env}.bak"

    info "Uploading docker/.env (build config, VPS paths) ..."
    scp_cmd "$tmp_docker_env" "${VPS_USER}@${VPS_HOST}:${REMOTE_DOCKER_DIR}/.env"
    rm -f "$tmp_docker_env"
    success "docker/.env synced"

    # Fix ownership on env files too
    ssh_cmd "chown ${REMOTE_OWNER}:${REMOTE_OWNER} ${REMOTE_PROJECT_DIR}/backend/.env ${REMOTE_DOCKER_DIR}/.env"
}

# ── First-time VPS setup ────────────────────────────────────────────
setup_vps() {
    header "First-time VPS setup"
    preflight

    info "Creating project directories ..."
    ssh_cmd "mkdir -p ${REMOTE_PROJECT_DIR}/backend/data && chown -R ${REMOTE_OWNER}:${REMOTE_OWNER} /home/rodrigo/projects"

    # Sync everything
    sync_code
    sync_env

    # Create proxy network for Traefik (may already exist from chat-trainer)
    info "Ensuring Docker 'proxy' network exists ..."
    ssh_cmd "docker network inspect proxy >/dev/null 2>&1 || docker network create proxy"
    success "Docker 'proxy' network ready"

    success "VPS setup complete!"
    echo ""
    info "Next: run ${BOLD}./deploy.sh${NC} to build and start the stack"
}

# ── Remote build & deploy ────────────────────────────────────────────
remote_build() {
    local service="${1:-}"

    header "Building on VPS${service:+ (service: $service)}"

    info "Ensuring Docker 'proxy' network exists ..."
    ssh_cmd "docker network inspect proxy >/dev/null 2>&1 || docker network create proxy"

    info "Ensuring backend/data directory exists ..."
    ssh_cmd "mkdir -p ${REMOTE_PROJECT_DIR}/backend/data"

    if [[ -n "$service" ]]; then
        info "Rebuilding service: ${service} ..."
        ssh_cmd "cd ${REMOTE_DOCKER_DIR} && docker compose -f ${COMPOSE_FILE} up -d --build ${service}" 2>&1
    else
        info "Building and starting full production stack ..."
        ssh_cmd "cd ${REMOTE_DOCKER_DIR} && docker compose -f ${COMPOSE_FILE} up -d --build --remove-orphans" 2>&1
    fi
    success "Production stack started"

    # Clean up dangling images
    info "Pruning dangling images ..."
    ssh_cmd "docker image prune -f" 2>/dev/null || true
}

# ── Verify deployment ────────────────────────────────────────────────
verify() {
    header "Verifying deployment"

    info "Container status:"
    ssh_cmd "cd ${REMOTE_DOCKER_DIR} && docker compose -f ${COMPOSE_FILE} ps"

    echo ""
    info "Waiting 5s for services to start ..."
    sleep 5

    info "Health check (backend via docker exec) ..."
    local health
    health=$(ssh_cmd "docker exec lumen-frontend curl -sf http://backend:8000/api/health 2>/dev/null" || echo "FAILED")
    if [[ "$health" == "FAILED" ]]; then
        warn "Backend health check failed — it may still be starting up"
        info "Check logs: ./deploy.sh --logs backend"
    else
        success "Backend healthy: ${health}"
    fi

    echo ""
    info "Checking Traefik route for lumen ..."
    local traefik_check
    traefik_check=$(ssh_cmd "curl -sf http://localhost:8080/api/http/routers 2>/dev/null | python3 -c \"import sys,json; [print(r['name'],'→',r.get('rule','')) for r in json.load(sys.stdin) if 'lumen' in r.get('name','')]\" 2>/dev/null" || echo "")
    if [[ -n "$traefik_check" ]]; then
        success "Traefik route: ${traefik_check}"
    else
        warn "Could not verify Traefik route (Traefik API may not be exposed)"
    fi

    echo ""
    echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${GREEN}  Deployment complete!${NC}"
    echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${CYAN}Frontend:${NC}  https://lumen.kardechat.com.br"
    echo -e "  ${CYAN}Backend:${NC}   internal only (via nginx /api/ proxy)"
    echo -e "  ${CYAN}Postgres:${NC}  internal only (Docker network)"
    echo -e "  ${CYAN}VPS:${NC}       ${VPS_HOST}"
    echo ""
}

# ── Show status ──────────────────────────────────────────────────────
show_status() {
    header "Production stack status"
    preflight
    ssh_cmd "cd ${REMOTE_DOCKER_DIR} && docker compose -f ${COMPOSE_FILE} ps"
    echo ""
    info "Health check:"
    ssh_cmd "docker exec lumen-frontend curl -sf http://backend:8000/api/health 2>/dev/null" && echo "" || warn "Backend not responding"
    echo ""
    info "All containers on this VPS:"
    ssh_cmd "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | head -20"
}

# ── Tail logs ────────────────────────────────────────────────────────
show_logs() {
    local service="${1:-}"
    header "Production logs (Ctrl+C to exit)"
    info "Connecting to VPS ..."
    if [[ -n "$service" ]]; then
        ssh_cmd "cd ${REMOTE_DOCKER_DIR} && docker compose -f ${COMPOSE_FILE} logs -f --tail=100 ${service}"
    else
        ssh_cmd "cd ${REMOTE_DOCKER_DIR} && docker compose -f ${COMPOSE_FILE} logs -f --tail=100"
    fi
}

# ── Interactive SSH ──────────────────────────────────────────────────
open_ssh() {
    header "Opening SSH session"
    info "Connecting to ${VPS_USER}@${VPS_HOST} ..."
    sshpass -p "${VPS_PASS}" ssh -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}"
}

# ── Disk usage ───────────────────────────────────────────────────────
show_disk() {
    header "VPS disk usage"
    preflight
    ssh_cmd "echo '── Filesystem ──' && df -h / && echo '' && echo '── Docker ──' && docker system df && echo '' && echo '── Top volumes ──' && du -sh /var/lib/docker/volumes/* 2>/dev/null | sort -h | tail -10"
}

# ── Main ─────────────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}${CYAN}"
    echo "  ╦  ╦ ╦╔╦╗╔═╗╔╗╔   ╔╦╗╔═╗╔═╗╦  ╔═╗╦ ╦"
    echo "  ║  ║ ║║║║║╣ ║║║    ║║║╣ ╠═╝║  ║ ║╚╦╝"
    echo "  ╩═╝╚═╝╩ ╩╚═╝╝╚╝   ═╩╝╚═╝╩  ╩═╝╚═╝ ╩ "
    echo -e "${NC}"

    case "${1:-}" in
        --setup)
            setup_vps
            ;;
        --sync)
            preflight
            sync_code
            sync_env
            success "Code and env synced (no rebuild)"
            ;;
        --sync-env)
            preflight
            sync_env
            success "Env files synced (no code, no rebuild)"
            ;;
        --build)
            preflight
            remote_build "${2:-}"
            verify
            ;;
        --logs)
            show_logs "${2:-}"
            ;;
        --status)
            show_status
            ;;
        --ssh)
            open_ssh
            ;;
        --disk)
            show_disk
            ;;
        --help|-h)
            head -20 "$0" | tail -18
            ;;
        "")
            # Full deploy: rsync → sync env → build → verify
            preflight
            sync_code
            sync_env
            remote_build
            verify
            ;;
        *)
            error "Unknown option: $1"
            echo "Run: ./deploy.sh --help"
            exit 1
            ;;
    esac
}

main "$@"
