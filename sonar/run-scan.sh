#!/usr/bin/env bash
set -euo pipefail

SONAR_HOME="${SONAR_HOME:-/opt/sonarqube}"
ENV_FILE="${SONAR_HOME}/.env"
LOG_FILE="${SONAR_LOG_FILE:-/var/log/sonar-scan.log}"
DATE="$(date +%Y-%m-%d)"
REPORT_DIR="/tmp/sonar-report-${DATE}"
REPORT_FILE="/tmp/sonar-report-${DATE}.json"

mkdir -p "$(dirname "${LOG_FILE}")" "${REPORT_DIR}"
touch "${LOG_FILE}"

log() {
  echo "[$(date --iso-8601=seconds)] $*" | tee -a "${LOG_FILE}"
}

if [[ ! -f "${ENV_FILE}" ]]; then
  log "Missing ${ENV_FILE}. Copy sonar/.env.example to ${ENV_FILE} and fill secrets."
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

: "${S3_BUCKET:?S3_BUCKET is required}"
: "${SONAR_TOKEN:?SONAR_TOKEN is required}"
: "${SONAR_PROJECT_KEY:=bugdaddy}"
: "${SONAR_REPO_PATH:=/opt/sonarqube/bug_daddy}"

cd "${SONAR_HOME}"

stop_runner_instance() {
  if [[ "${STOP_INSTANCE_AFTER_SCAN:-1}" != "1" ]]; then
    return
  fi
  METADATA_TOKEN="$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || true)"
  INSTANCE_ID=""
  if [[ -n "${METADATA_TOKEN}" ]]; then
    INSTANCE_ID="$(curl -fsS -H "X-aws-ec2-metadata-token: ${METADATA_TOKEN}" \
      "http://169.254.169.254/latest/meta-data/instance-id" || true)"
  fi
  if [[ -n "${INSTANCE_ID}" ]]; then
    log "Stopping EC2 runner ${INSTANCE_ID}"
    aws ec2 stop-instances --instance-ids "${INSTANCE_ID}" --region "${AWS_REGION:-ap-south-1}" >> "${LOG_FILE}" 2>&1 || true
  fi
}

cleanup() {
  docker compose down >> "${LOG_FILE}" 2>&1 || true
  stop_runner_instance
}
trap cleanup EXIT

if [[ -d "${SONAR_REPO_PATH}/.git" ]]; then
  log "Updating repository at ${SONAR_REPO_PATH}"
  git -C "${SONAR_REPO_PATH}" pull --ff-only >> "${LOG_FILE}" 2>&1 || log "Repository update failed; scanning existing checkout."
fi

log "Starting SonarQube"
docker compose up -d sonarqube >> "${LOG_FILE}" 2>&1

log "Waiting for SonarQube to become UP"
until curl -fsS "http://127.0.0.1:9000/api/system/status" | grep -q '"status":"UP"'; do
  sleep 15
done

log "Running Sonar scanner"
docker compose run --rm scanner >> "${LOG_FILE}" 2>&1

log "Exporting unresolved SonarQube issues"
page=1
page_size=500
total=1
while (( (page - 1) * page_size < total )); do
  page_file="${REPORT_DIR}/page-${page}.json"
  curl -fsS -u "${SONAR_TOKEN}:" \
    "http://127.0.0.1:9000/api/issues/search?projectKeys=${SONAR_PROJECT_KEY}&resolved=false&ps=${page_size}&p=${page}" \
    -o "${page_file}"

  total="$(python3 - "${page_file}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)
print(payload.get("paging", {}).get("total", 0))
PY
)"
  page=$((page + 1))
done

python3 - "${REPORT_DIR}" "${REPORT_FILE}" "${SONAR_PROJECT_KEY}" "${DATE}" <<'PY'
import glob
import json
import os
import sys

report_dir, report_file, project_key, report_date = sys.argv[1:5]
issues = []
components = {}
rules = {}
facets = []
total = 0

for path in sorted(glob.glob(os.path.join(report_dir, "page-*.json"))):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    total = payload.get("paging", {}).get("total", total)
    issues.extend(payload.get("issues", []))
    for component in payload.get("components", []):
        components[component.get("key")] = component
    for rule in payload.get("rules", []):
        rules[rule.get("key")] = rule
    if payload.get("facets"):
        facets = payload["facets"]

merged = {
    "projectKey": project_key,
    "date": report_date,
    "total": total,
    "exported": len(issues),
    "issues": issues,
    "components": list(components.values()),
    "rules": list(rules.values()),
    "facets": facets,
}

with open(report_file, "w", encoding="utf-8") as handle:
    json.dump(merged, handle, indent=2)
PY

log "Uploading report to s3://${S3_BUCKET}/${DATE}/report.json"
aws s3 cp "${REPORT_FILE}" "s3://${S3_BUCKET}/${DATE}/report.json" >> "${LOG_FILE}" 2>&1

log "Report uploaded. Stopping SonarQube."
