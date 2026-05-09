#!/usr/bin/env bash
set -euo pipefail

EC2_IP="13.205.34.252"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/bug-daddy-key.pem}"
USER="ubuntu"
REMOTE="${USER}@${EC2_IP}"
BRANCH="master"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
REMOTE_BACKEND_DIR="${REMOTE_BACKEND_DIR:-/home/ubuntu/platform/backend}"
REMOTE_FRONTEND_DIR="${REMOTE_FRONTEND_DIR:-/home/ubuntu/platform/frontend}"
BACKEND_SERVICE="${BACKEND_SERVICE:-bug-daddy-platform-backend.service}"
AGENT_EXECUTION_CALLBACK_URL="${AGENT_EXECUTION_CALLBACK_URL:-http://${EC2_IP}/api}"
AGENT_EXECUTION_LOG_SECRET="${AGENT_EXECUTION_LOG_SECRET:-}"

echo "🚀 Deploying Bug Daddy Platform from branch ${BRANCH} to ${EC2_IP}..."

# 1. Deploy Frontend
echo "📦 Building Frontend..."
(cd platform/frontend && npm run build)

echo "📤 Uploading Frontend..."
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" "mkdir -p ${REMOTE_FRONTEND_DIR}"
rsync -az --delete \
  -e "ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no" \
  --exclude='.git' \
  --exclude='node_modules' \
  platform/frontend/ "${REMOTE}:${REMOTE_FRONTEND_DIR}/"

echo "🔄 Installing deps and restarting Frontend via PM2..."
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" \
  "REMOTE_FRONTEND_DIR=${REMOTE_FRONTEND_DIR} FRONTEND_PORT=${FRONTEND_PORT} bash -s" << 'EOF'
  cd "${REMOTE_FRONTEND_DIR}"

  # Install node_modules on server
  npm ci --omit=dev

  # Ensure PM2 is installed
  if ! command -v pm2 &>/dev/null; then
    sudo npm install -g pm2
  fi

  # Kill anything holding the port before (re)starting
  sudo fuser -k ${FRONTEND_PORT}/tcp || true
  sleep 1

  # Start or restart the app
  if pm2 describe bugdaddy &>/dev/null; then
    pm2 restart bugdaddy --update-env
  else
    PORT=${FRONTEND_PORT} pm2 start npm --name bugdaddy -- start
    pm2 save
    pm2 startup | tail -1 | sudo bash || true
  fi
EOF

echo "🔧 Updating Nginx config..."
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" \
  "FRONTEND_PORT=${FRONTEND_PORT} BACKEND_PORT=${BACKEND_PORT} bash -s" << 'EOF'
  sudo tee /etc/nginx/sites-available/bugdaddy > /dev/null << NGINX
map \$http_upgrade \$connection_upgrade {
  default upgrade;
  '' close;
}

server {
  listen 80 default_server;
  listen [::]:80 default_server;
  server_name bugdaddy.in www.bugdaddy.in;

  location /api/ {
    proxy_pass http://127.0.0.1:${BACKEND_PORT}/;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }

  location /health {
    proxy_pass http://127.0.0.1:${BACKEND_PORT}/health;
    proxy_set_header Host \$host;
  }

  location / {
    proxy_pass http://127.0.0.1:${FRONTEND_PORT};
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection \$connection_upgrade;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }
}
NGINX

  sudo ln -sf /etc/nginx/sites-available/bugdaddy /etc/nginx/sites-enabled/bugdaddy
  # Remove old static-file config if it exists (replaced by this one)
  sudo rm -f /etc/nginx/sites-enabled/bug-daddy-platform
  sudo nginx -t && sudo systemctl reload nginx
EOF
echo "✅ Frontend deployed."

# 2. Deploy Backend
echo "📦 Uploading Backend..."
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" "mkdir -p ${REMOTE_BACKEND_DIR}"
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no platform/backend/main.py platform/backend/requirements.txt "${REMOTE}:${REMOTE_BACKEND_DIR}/"

echo "🔄 Restarting Backend Service..."
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" "BACKEND_PORT=${BACKEND_PORT} REMOTE_BACKEND_DIR=${REMOTE_BACKEND_DIR} BACKEND_SERVICE=${BACKEND_SERVICE} AGENT_EXECUTION_CALLBACK_URL=${AGENT_EXECUTION_CALLBACK_URL} AGENT_EXECUTION_LOG_SECRET=${AGENT_EXECUTION_LOG_SECRET} bash -s" << 'EOF'
  cd "${REMOTE_BACKEND_DIR}"

  if [ ! -d "venv" ]; then
    python3 -m venv venv
  fi

  ./venv/bin/python -m pip install --upgrade pip > /dev/null
  ./venv/bin/python -m pip install -r requirements.txt > /dev/null

  if systemctl list-unit-files "${BACKEND_SERVICE}" >/dev/null 2>&1; then
    sudo mkdir -p "/etc/systemd/system/${BACKEND_SERVICE}.d"
    sudo tee "/etc/systemd/system/${BACKEND_SERVICE}.d/override.conf" >/dev/null <<UNIT
[Service]
WorkingDirectory=${REMOTE_BACKEND_DIR}
EnvironmentFile=
Environment=AWS_REGION=ap-south-1
Environment=AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:ap-south-1:105028893980:runtime/bug_daddy-IV6831D6Rs
Environment=AGENT_EXECUTION_CALLBACK_URL=${AGENT_EXECUTION_CALLBACK_URL}
Environment=AGENT_EXECUTION_LOG_SECRET=${AGENT_EXECUTION_LOG_SECRET}
ExecStart=
ExecStart=${REMOTE_BACKEND_DIR}/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port ${BACKEND_PORT}
UNIT
    sudo systemctl daemon-reload
    sudo systemctl restart "${BACKEND_SERVICE}"
  else
    pkill -f uvicorn || true
    AGENT_EXECUTION_CALLBACK_URL="${AGENT_EXECUTION_CALLBACK_URL}" AGENT_EXECUTION_LOG_SECRET="${AGENT_EXECUTION_LOG_SECRET}" nohup ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "${BACKEND_PORT}" > uvicorn.log 2>&1 &
  fi
EOF
echo "✅ Backend deployed and restarted."

echo "🎉 Deployment complete!"
echo "Frontend: http://${EC2_IP}/"
echo "Backend:  http://${EC2_IP}:${BACKEND_PORT}/"
