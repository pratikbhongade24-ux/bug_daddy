#!/bin/bash
set -eo pipefail

EC2_IP="13.205.34.252"
SSH_KEY="~/.ssh/bug-daddy-key.pem"
USER="ubuntu"
REMOTE="${USER}@${EC2_IP}"

echo "🚀 Deploying Bug Daddy Platform to ${EC2_IP}..."

# 1. Deploy Frontend
echo "📦 Building and Uploading Frontend..."
(cd platform/frontend && npm run build)
ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no ${REMOTE} "mkdir -p ~/bug-daddy-out"
scp -i ${SSH_KEY} -o StrictHostKeyChecking=no -r platform/frontend/out/* ${REMOTE}:~/bug-daddy-out/
ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no ${REMOTE} << 'EOF'
  sudo rm -rf /var/www/html/*
  sudo mv ~/bug-daddy-out/* /var/www/html/
  rm -rf ~/bug-daddy-out
  sudo systemctl reload nginx
EOF
echo "✅ Frontend deployed."

# 2. Deploy Backend
echo "📦 Uploading Backend..."
# Make sure the remote backend directory exists
ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no ${REMOTE} "mkdir -p ~/platform/backend"
scp -i ${SSH_KEY} -o StrictHostKeyChecking=no platform/backend/main.py platform/backend/requirements.txt ${REMOTE}:~/platform/backend/

echo "🔄 Restarting Backend Service..."
ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no ${REMOTE} << 'EOF'
  cd ~/platform/backend
  
  # Setup virtualenv if it doesn't exist
  if [ ! -d "venv" ]; then
    python3 -m venv venv
  fi
  
  # Install dependencies
  ./venv/bin/pip install -r requirements.txt > /dev/null
  
  # Restart uvicorn
  pkill -f uvicorn || true
  nohup ./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
EOF
echo "✅ Backend deployed and restarted."

echo "🎉 Deployment complete!"
echo "Frontend: http://${EC2_IP}/"
echo "Backend:  http://${EC2_IP}:8000/"
