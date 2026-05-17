#!/usr/bin/env bash
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-bug-daddy}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
EC2_HOST="${EC2_HOST:-}"
EC2_USER="${EC2_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/bug-daddy-key.pem}"
REPO_URL="${REPO_URL:-https://github.com/pratikbhongade24-ux/bug_daddy}"
REPO_BRANCH="${REPO_BRANCH:-master}"
REMOTE_HOME="${REMOTE_HOME:-/opt/sonarqube}"
SONAR_RUNNER_INSTANCE_NAME="${SONAR_RUNNER_INSTANCE_NAME:-bugdaddy-sonar-runner}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SONAR_DIR="${ROOT_DIR}/sonar"

if [[ -z "${EC2_HOST}" ]]; then
  RUNNER_INSTANCE_ID="$(aws --profile "${AWS_PROFILE}" --region "${AWS_REGION}" ec2 describe-instances \
    --filters "Name=tag:Name,Values=${SONAR_RUNNER_INSTANCE_NAME}" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text)"
  if [[ -z "${RUNNER_INSTANCE_ID}" || "${RUNNER_INSTANCE_ID}" == "None" ]]; then
    echo "Could not find Sonar runner instance named ${SONAR_RUNNER_INSTANCE_NAME}. Run sonar/setup-aws.sh apply first." >&2
    exit 1
  fi
  RUNNER_STATE="$(aws --profile "${AWS_PROFILE}" --region "${AWS_REGION}" ec2 describe-instances \
    --instance-ids "${RUNNER_INSTANCE_ID}" \
    --query 'Reservations[0].Instances[0].State.Name' \
    --output text)"
  if [[ "${RUNNER_STATE}" == "stopped" ]]; then
    aws --profile "${AWS_PROFILE}" --region "${AWS_REGION}" ec2 start-instances --instance-ids "${RUNNER_INSTANCE_ID}" >/dev/null
    aws --profile "${AWS_PROFILE}" --region "${AWS_REGION}" ec2 wait instance-running --instance-ids "${RUNNER_INSTANCE_ID}"
  fi
  EC2_HOST="$(aws --profile "${AWS_PROFILE}" --region "${AWS_REGION}" ec2 describe-instances \
    --instance-ids "${RUNNER_INSTANCE_ID}" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)"
fi

REMOTE="${EC2_USER}@${EC2_HOST}"

echo "Bootstrapping SonarQube EC2 host ${REMOTE}"

ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" \
  "REMOTE_HOME='${REMOTE_HOME}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git unzip

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get install -y docker.io
fi

if ! docker compose version >/dev/null 2>&1; then
  sudo apt-get install -y docker-compose-v2 || sudo apt-get install -y docker-compose-plugin
fi

if ! command -v aws >/dev/null 2>&1; then
  arch="$(uname -m)"
  case "${arch}" in
    x86_64) aws_arch="x86_64" ;;
    aarch64|arm64) aws_arch="aarch64" ;;
    *) echo "Unsupported architecture for AWS CLI installer: ${arch}" >&2; exit 1 ;;
  esac
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip" -o /tmp/awscliv2.zip
  rm -rf /tmp/aws
  unzip -q /tmp/awscliv2.zip -d /tmp
  sudo /tmp/aws/install --update
fi

# Upgrade cryptography package to fix CVE-2026-34073
# This addresses incomplete DNS name constraint enforcement on peer names
sudo apt-get install -y python3-pip
pip3 install --upgrade cryptography

sudo usermod -aG docker ubuntu || true
echo "vm.max_map_count=262144" | sudo tee /etc/sysctl.d/99-sonarqube.conf >/dev/null
sudo sysctl -w vm.max_map_count=262144 >/dev/null

if [[ ! -f /swapfile-sonar ]]; then
  sudo fallocate -l 4G /swapfile-sonar
  sudo chmod 600 /swapfile-sonar
  sudo mkswap /swapfile-sonar >/dev/null
fi
if ! swapon --show=NAME | grep -qx /swapfile-sonar; then
  sudo swapon /swapfile-sonar
fi
if ! grep -q '^/swapfile-sonar ' /etc/fstab; then
  echo '/swapfile-sonar none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

sudo mkdir -p "${REMOTE_HOME}"
sudo chown -R ubuntu:ubuntu "${REMOTE_HOME}"
REMOTE_SCRIPT

rsync -az --delete \
  -e "ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no" \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='venv' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='sonar/.generated' \
  "${ROOT_DIR}/" \
  "${REMOTE}:${REMOTE_HOME}/bug_daddy/"

rsync -az \
  -e "ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no" \
  "${SONAR_DIR}/docker-compose.yml" \
  "${SONAR_DIR}/run-scan.sh" \
  "${SONAR_DIR}/.env.example" \
  "${REMOTE}:${REMOTE_HOME}/"

if [[ -f "${SONAR_DIR}/.generated/.env.runtime" ]]; then
  rsync -az \
    -e "ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no" \
    "${SONAR_DIR}/.generated/.env.runtime" \
    "${REMOTE}:${REMOTE_HOME}/.env"
fi

ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${REMOTE}" \
  "REMOTE_HOME='${REMOTE_HOME}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

chmod +x "${REMOTE_HOME}/run-scan.sh"
if [[ "${REMOTE_HOME}/run-scan.sh" != "/opt/sonarqube/run-scan.sh" ]]; then
  sudo ln -sf "${REMOTE_HOME}/run-scan.sh" /opt/sonarqube/run-scan.sh
fi

if [[ ! -f "${REMOTE_HOME}/.env" ]]; then
  cp "${REMOTE_HOME}/.env.example" "${REMOTE_HOME}/.env"
  echo "Created ${REMOTE_HOME}/.env from example. Fill secrets before running scans."
else
  chmod 600 "${REMOTE_HOME}/.env"
fi

echo "EC2 bootstrap complete at ${REMOTE_HOME}"
REMOTE_SCRIPT