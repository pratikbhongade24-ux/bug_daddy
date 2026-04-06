#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${PLATFORM_DIR}/.." && pwd)"

DEPLOY_HOST="${DEPLOY_HOST:-ubuntu@3.109.87.158}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/bug-daddy-key.pem}"
REMOTE_PLATFORM_DIR="${REMOTE_PLATFORM_DIR:-/home/ubuntu/bug_daddy/platform}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-bug-daddy-platform-frontend}"
BACKEND_SERVICE="${BACKEND_SERVICE:-bug-daddy-platform-backend}"

SSH_OPTS=(
  -i "${SSH_KEY}"
  -o StrictHostKeyChecking=accept-new
)

require_tool() {
  local tool="$1"
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Missing required tool: ${tool}" >&2
    exit 1
  fi
}

run_remote() {
  local command="$1"
  ssh "${SSH_OPTS[@]}" "${DEPLOY_HOST}" "${command}"
}

sync_dir() {
  local source_dir="$1"
  local remote_dir="$2"
  shift 2

  rsync -az --delete \
    -e "ssh -i ${SSH_KEY} -o StrictHostKeyChecking=accept-new" \
    "$@" \
    "${source_dir}/" "${DEPLOY_HOST}:${remote_dir}/"
}

print_target() {
  echo "Deploy target: ${DEPLOY_HOST}"
  echo "Remote root:  ${REMOTE_PLATFORM_DIR}"
}
