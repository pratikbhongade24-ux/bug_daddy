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
SECURITY_SCANNER_ACCESS_KEY_ID="${SECURITY_SCANNER_ACCESS_KEY_ID:-AKIARQ5BVXUOP7HLRG3O}"
SECURITY_SCANNER_SECRET_ACCESS_KEY="${SECURITY_SCANNER_SECRET_ACCESS_KEY:-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}"

echo "Deploying branch '${BRANCH}' to ${EC2_IP}..."

ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" \
  "BRANCH=${BRANCH} BACKEND_PORT=${BACKEND_PORT} FRONTEND_PORT=${FRONTEND_PORT} REMOTE_ROOT=${REMOTE_ROOT} BACKEND_SERVICE=${BACKEND_SERVICE} AGENT_EXECUTION_CALLBACK_URL=${AGENT_EXECUTION_CALLBACK_URL} AGENT_EXECUTION_LOG_SECRET='${AGENT_EXECUTION_LOG_SECRET}' SECURITY_SCANNER_ACCESS_KEY_ID='${SECURITY_SCANNER_ACCESS_KEY_ID}' SECURITY_SCANNER_SECRET_ACCESS_KEY='${SECURITY_SCANNER_SECRET_ACCESS_KEY}' bash -s" << 'EOF'

set -euo pipefail

# Pull latest code
cd "${REMOTE_ROOT}"
git pull origin "${BRANCH}"

# Frontend
echo "Building frontend..."
cd "${REMOTE_ROOT}/platform/frontend"
rm -rf node_modules
npm ci --omit=dev
npm run build

# A legacy systemd unit (bug-daddy-platform-frontend.service) used to manage the
# frontend from /home/ubuntu/bug_daddy/. We now run it under pm2 from
# ${REMOTE_ROOT}, but the old unit's Restart=always would race pm2 and grab
# port ${FRONTEND_PORT} after every kill. Disable it idempotently here.
if sudo systemctl list-unit-files bug-daddy-platform-frontend.service 2>/dev/null | grep -q '^bug-daddy-platform-frontend.service'; then
  sudo systemctl disable --now bug-daddy-platform-frontend.service 2>/dev/null || true
fi

# Always delete any existing pm2 entry and kill any orphaned process on the
# port before starting fresh. pm2 restart does not kill child processes spawned
# by npm (e.g. next-server), so orphans keep the port open and cause EADDRINUSE
# on the next restart. ss reads kernel socket info directly, so it catches
# loopback-bound listeners that fuser/lsof may miss.
pm2 delete bugdaddy 2>/dev/null || true
for attempt in 1 2 3 4 5; do
  PIDS=$(sudo ss -ltnpH "( sport = :${FRONTEND_PORT} )" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u)
  [ -z "$PIDS" ] && break
  echo "Port ${FRONTEND_PORT} held by PIDs: $PIDS (attempt $attempt)"
  sudo kill -9 $PIDS 2>/dev/null || true
  sleep 1
done
PORT=${FRONTEND_PORT} pm2 start npm --name bugdaddy -- start
pm2 save

# Backend
echo "Restarting backend..."
BACKEND_DIR="${REMOTE_ROOT}/platform/backend"
VENV_DIR="/home/ubuntu/platform/backend/venv"
cd "${BACKEND_DIR}"
"${VENV_DIR}/bin/pip" install -r requirements.txt -q

sudo tee "/etc/systemd/system/${BACKEND_SERVICE}.d/override.conf" >/dev/null <<UNIT
[Service]
WorkingDirectory=${BACKEND_DIR}
EnvironmentFile=
Environment=AWS_REGION=ap-south-1
Environment=AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:ap-south-1:105028893980:runtime/bug_daddy-IV6831D6Rs
Environment=AGENT_EXECUTION_CALLBACK_URL=${AGENT_EXECUTION_CALLBACK_URL}
Environment=AGENT_EXECUTION_LOG_SECRET=${AGENT_EXECUTION_LOG_SECRET}
Environment=SECURITY_SCANNER_ACCESS_KEY_ID=${SECURITY_SCANNER_ACCESS_KEY_ID}
Environment=SECURITY_SCANNER_SECRET_ACCESS_KEY=${SECURITY_SCANNER_SECRET_ACCESS_KEY}
ExecStart=
ExecStart=${VENV_DIR}/bin/python -m uvicorn main:app --host 127.0.0.1 --port ${BACKEND_PORT}
UNIT

sudo systemctl daemon-reload
sudo systemctl restart "${BACKEND_SERVICE}"

echo "Done! https://bugdaddy.in"
EOF
