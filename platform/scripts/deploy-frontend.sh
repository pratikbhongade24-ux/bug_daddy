#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_tool ssh
require_tool rsync

print_target
echo "Syncing frontend..."

sync_dir "${PLATFORM_DIR}/frontend" "${REMOTE_PLATFORM_DIR}/frontend" \
  --exclude ".env.local" \
  --exclude "node_modules" \
  --exclude ".next"

echo "Installing frontend dependencies, building, and restarting service..."

run_remote "
set -euo pipefail
cd '${REMOTE_PLATFORM_DIR}/frontend'
npm install
npm run build
sudo systemctl restart '${FRONTEND_SERVICE}'
sudo systemctl --no-pager --full status '${FRONTEND_SERVICE}' | sed -n '1,20p'
"

echo "Frontend deploy complete."
