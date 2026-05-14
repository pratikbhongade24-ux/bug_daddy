#!/bin/bash
###############################################################################
# Bug Daddy — Local Development Setup
#
# Starts both the backend (FastAPI) and frontend (Next.js) in parallel.
# Logs from each process are prefixed and streamed to the terminal.
# Ctrl+C shuts both down cleanly.
#
# Backend:  platform/backend/  — uvicorn on :8000
# Frontend: platform/frontend/ — Next.js dev on :3000
###############################################################################

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$REPO_ROOT/platform/backend"
FRONTEND_DIR="$REPO_ROOT/platform/frontend"

# ── colours ──────────────────────────────────────────────────────────────────
CYAN="\033[0;36m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

log()  { printf "${CYAN}[local_run]${RESET} %s\n" "$*"; }
ok()   { printf "${GREEN}[local_run]${RESET} %s\n" "$*"; }
warn() { printf "${YELLOW}[local_run]${RESET} %s\n" "$*"; }
err()  { printf "${RED}[local_run]${RESET} %s\n" "$*" >&2; }

cleanup() {
  warn "Shutting down…"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  ok "Done."
}
trap cleanup INT TERM

# ── env defaults (override via environment or a .env file at repo root) ───────
if [[ -f "$REPO_ROOT/.env" ]]; then
  log "Loading .env from repo root"
  set -o allexport
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +o allexport
fi

export DB_HOST="${DB_HOST:-database-1.ctkcsksi0yjl.ap-south-1.rds.amazonaws.com}"
export DB_PORT="${DB_PORT:-3306}"
export DB_NAME="${DB_NAME:-bug_daddy}"
export DB_USER="${DB_USER:-bug_daddy}"
export DB_PASSWORD="${DB_PASSWORD:-bug_daddy}"
export TOKEN_SECRET="${TOKEN_SECRET:-bug-daddy-dev-secret}"
export AWS_REGION="${AWS_REGION:-ap-south-1}"

# ── backend setup ─────────────────────────────────────────────────────────────
log "Setting up backend…"

VENV="$BACKEND_DIR/venv"
if [[ ! -d "$VENV" ]]; then
  log "Creating Python venv at $VENV"
  python3 -m venv "$VENV"
fi

log "Installing/updating Python dependencies"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$BACKEND_DIR/requirements.txt"

ok "Backend ready — starting uvicorn on :8000"
(
  cd "$BACKEND_DIR"
  "$VENV/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 --reload 2>&1 \
    | sed "s/^/$(printf "${GREEN}[backend]${RESET} ")/"
) &
BACKEND_PID=$!

# ── frontend setup ────────────────────────────────────────────────────────────
log "Setting up frontend…"

if ! command -v node &>/dev/null; then
  err "node not found — install Node.js 18+ and re-run"
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  log "Installing npm dependencies"
  npm --prefix "$FRONTEND_DIR" install
else
  log "node_modules present — skipping npm install (run 'npm install' manually if needed)"
fi

ok "Frontend ready — starting Next.js dev server on :3000"
(
  cd "$FRONTEND_DIR"
  npm run dev 2>&1 \
    | sed "s/^/$(printf "${CYAN}[frontend]${RESET} ")/"
) &
FRONTEND_PID=$!

# ── wait ──────────────────────────────────────────────────────────────────────
echo ""
ok "Both services running. Press Ctrl+C to stop."
printf "  ${GREEN}Backend${RESET}  → http://localhost:8000\n"
printf "  ${CYAN}Frontend${RESET} → http://localhost:3000\n"
echo ""

wait "$BACKEND_PID" "$FRONTEND_PID"
