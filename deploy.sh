#!/usr/bin/env bash
set -euo pipefail

EC2_IP="13.205.34.252"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/bug-daddy-key.pem}"
REMOTE="ubuntu@${EC2_IP}"
BRANCH="${BRANCH:-master}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/ubuntu/repo}"
BACKEND_SERVICE="${BACKEND_SERVICE:-bug-daddy-platform-backend.service}"
AGENT_EXECUTION_LOG_SECRET="${AGENT_EXECUTION_LOG_SECRET:-}"
AGENT_EXECUTION_CALLBACK_URL="${AGENT_EXECUTION_CALLBACK_URL:-https://bugdaddy.in/api}"

echo "Deploying branch '${BRANCH}' to ${EC2_IP}..."

ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" \
  "BRANCH=${BRANCH} BACKEND_PORT=${BACKEND_PORT} FRONTEND_PORT=${FRONTEND_PORT} REMOTE_ROOT=${REMOTE_ROOT} BACKEND_SERVICE=${BACKEND_SERVICE} AGENT_EXECUTION_CALLBACK_URL=${AGENT_EXECUTION_CALLBACK_URL} AGENT_EXECUTION_LOG_SECRET='${AGENT_EXECUTION_LOG_SECRET}' bash -s" << 'EOF'

set -euo pipefail

# Pull latest code
cd "${REMOTE_ROOT}"
git pull origin "${BRANCH}"

# Frontend
echo "Building frontend..."
cd "${REMOTE_ROOT}/platform/frontend"
npm ci --omit=dev
npm run build
pm2 restart bugdaddy || PORT=${FRONTEND_PORT} pm2 start npm --name bugdaddy -- start
pm2 save

# Backend
echo "Restarting backend..."
cd "${REMOTE_ROOT}/platform/backend"
./venv/bin/pip install -r requirements.txt -q

sudo tee "/etc/systemd/system/${BACKEND_SERVICE}.d/override.conf" >/dev/null <<UNIT
[Service]
Environment=AGENT_EXECUTION_CALLBACK_URL=${AGENT_EXECUTION_CALLBACK_URL}
Environment=AGENT_EXECUTION_LOG_SECRET=${AGENT_EXECUTION_LOG_SECRET}
UNIT

sudo systemctl daemon-reload
sudo systemctl restart "${BACKEND_SERVICE}"

echo "Done! https://bugdaddy.in"
EOF
