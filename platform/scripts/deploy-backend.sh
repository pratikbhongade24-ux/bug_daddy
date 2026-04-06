#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_tool ssh
require_tool rsync

print_target
echo "Syncing backend..."

sync_dir "${PLATFORM_DIR}/backend" "${REMOTE_PLATFORM_DIR}/backend" \
  --exclude ".venv" \
  --exclude ".env" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude ".pytest_cache" \
  --exclude ".mypy_cache" \
  --exclude "platform.db"

echo "Installing backend dependencies and restarting service..."

run_remote "
set -euo pipefail
cd '${REMOTE_PLATFORM_DIR}/backend'
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
sudo systemctl restart '${BACKEND_SERVICE}'
sudo systemctl --no-pager --full status '${BACKEND_SERVICE}' | sed -n '1,20p'
"

echo "Backend deploy complete."
