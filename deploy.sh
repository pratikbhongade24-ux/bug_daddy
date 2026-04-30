#!/usr/bin/env bash
set -euo pipefail

EC2_IP="13.205.34.252"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/bug-daddy-key.pem}"
USER="ubuntu"
REMOTE="${USER}@${EC2_IP}"
BRANCH="master"
BACKEND_PORT="${BACKEND_PORT:-8000}"
REMOTE_BACKEND_DIR="${REMOTE_BACKEND_DIR:-/home/ubuntu/platform/backend}"
BACKEND_SERVICE="${BACKEND_SERVICE:-bug-daddy-platform-backend.service}"

echo "🚀 Deploying Bug Daddy Platform from branch ${BRANCH} to ${EC2_IP}..."

# 1. Deploy Frontend
echo "📦 Building and Uploading Frontend..."
(cd platform/frontend && npm run build)
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" "mkdir -p ~/bug-daddy-out"
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no -r platform/frontend/out/* "${REMOTE}:~/bug-daddy-out/"
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" << 'EOF'
  sudo rm -rf /var/www/html/*
  sudo mv ~/bug-daddy-out/* /var/www/html/
  rm -rf ~/bug-daddy-out
  sudo systemctl reload nginx
EOF
echo "✅ Frontend deployed."

# 2. Deploy Backend
echo "📦 Uploading Backend..."
# Make sure the remote backend directory exists
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" "mkdir -p ${REMOTE_BACKEND_DIR}"
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no platform/backend/main.py platform/backend/requirements.txt "${REMOTE}:${REMOTE_BACKEND_DIR}/"

echo "🔄 Restarting Backend Service..."
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" "BACKEND_PORT=${BACKEND_PORT} REMOTE_BACKEND_DIR=${REMOTE_BACKEND_DIR} BACKEND_SERVICE=${BACKEND_SERVICE} bash -s" << 'EOF'
  cd "${REMOTE_BACKEND_DIR}"
  
  # Setup virtualenv if it doesn't exist
  if [ ! -d "venv" ]; then
    python3 -m venv venv
  fi
  
  # Install dependencies
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
ExecStart=
ExecStart=${REMOTE_BACKEND_DIR}/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port ${BACKEND_PORT}
UNIT
    sudo systemctl daemon-reload
    sudo systemctl restart "${BACKEND_SERVICE}"
  else
    pkill -f uvicorn || true
    nohup ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "${BACKEND_PORT}" > uvicorn.log 2>&1 &
  fi
EOF
echo "✅ Backend deployed and restarted."

echo "🎉 Deployment complete!"
echo "Frontend: http://${EC2_IP}/"
echo "Backend:  http://${EC2_IP}:${BACKEND_PORT}/"
