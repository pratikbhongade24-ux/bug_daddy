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
JIRA_WEBHOOK_SECRET="${JIRA_WEBHOOK_SECRET:-d8tbOEYzWYHpB3rHS878}"

echo "Deploying branch '${BRANCH}' to ${EC2_IP}..."

ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" \
  "BRANCH=${BRANCH} BACKEND_PORT=${BACKEND_PORT} FRONTEND_PORT=${FRONTEND_PORT} REMOTE_ROOT=${REMOTE_ROOT} BACKEND_SERVICE=${BACKEND_SERVICE} AGENT_EXECUTION_CALLBACK_URL=${AGENT_EXECUTION_CALLBACK_URL} AGENT_EXECUTION_LOG_SECRET='${AGENT_EXECUTION_LOG_SECRET}' SECURITY_SCANNER_ACCESS_KEY_ID='${SECURITY_SCANNER_ACCESS_KEY_ID}' SECURITY_SCANNER_SECRET_ACCESS_KEY='${SECURITY_SCANNER_SECRET_ACCESS_KEY}' JIRA_WEBHOOK_SECRET='${JIRA_WEBHOOK_SECRET}' bash -s" << 'EOF'

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

# Reload if the pm2 entry exists, otherwise start fresh. pm2's treekill handles
# next-server children, so no manual port-killing is needed.
PORT=${FRONTEND_PORT} pm2 reload bugdaddy --update-env 2>/dev/null \
  || PORT=${FRONTEND_PORT} pm2 start npm --name bugdaddy -- start
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
Environment=JIRA_WEBHOOK_SECRET=${JIRA_WEBHOOK_SECRET}
ExecStart=
ExecStart=${VENV_DIR}/bin/python -m uvicorn main:app --host 127.0.0.1 --port ${BACKEND_PORT}
UNIT

sudo systemctl daemon-reload
sudo systemctl restart "${BACKEND_SERVICE}"

echo "Done! https://bugdaddy.in"
EOF
