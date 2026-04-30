#!/usr/bin/env bash
set -euo pipefail

EC2_IP="13.205.34.252"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/bug-daddy-key.pem}"
USER="ubuntu"
REMOTE="${USER}@${EC2_IP}"
BRANCH="master"
BACKEND_PORT="${BACKEND_PORT:-8000}"

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
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" "mkdir -p ~/platform/backend"
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no platform/backend/main.py platform/backend/requirements.txt "${REMOTE}:~/platform/backend/"

echo "🔄 Restarting Backend Service..."
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" "BACKEND_PORT=${BACKEND_PORT} bash -s" << 'EOF'
  cd ~/platform/backend
  
  # Setup virtualenv if it doesn't exist
  if [ ! -d "venv" ]; then
    python3 -m venv venv
  fi
  
  # Install dependencies
  ./venv/bin/python -m pip install --upgrade pip > /dev/null
  ./venv/bin/python -m pip install -r requirements.txt > /dev/null
  
  # Restart uvicorn through the venv so global packages cannot be selected.
  pkill -f uvicorn || true
  nohup ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "${BACKEND_PORT}" > uvicorn.log 2>&1 &
EOF
echo "✅ Backend deployed and restarted."

echo "🎉 Deployment complete!"
echo "Frontend: http://${EC2_IP}/"
echo "Backend:  http://${EC2_IP}:${BACKEND_PORT}/"
