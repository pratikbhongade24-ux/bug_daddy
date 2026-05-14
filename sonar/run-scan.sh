#!/usr/bin/env bash
set -euo pipefail

SONAR_HOME="${SONAR_HOME:-/opt/sonarqube}"
ENV_FILE="${SONAR_HOME}/.env"
LOG_FILE="${SONAR_LOG_FILE:-/var/log/sonar-scan.log}"
DATE="$(date +%Y-%m-%d)"
REPORT_DIR="/tmp/sonar-report-${DATE}"
REPORT_FILE="/tmp/sonar-report-${DATE}.json"

CW_LOG_GROUP="${CW_LOG_GROUP:-/bugdaddy/sonar-scan}"
CW_LOG_STREAM="${CW_LOG_STREAM:-${DATE}/run-$(date +%H%M%S)}"
AWS_REGION="${AWS_REGION:-ap-south-1}"

mkdir -p "$(dirname "${LOG_FILE}")" "${REPORT_DIR}"
touch "${LOG_FILE}"

# ── CloudWatch helpers ────────────────────────────────────────────────────────

cw_ensure_stream() {
  aws logs create-log-group --log-group-name "${CW_LOG_GROUP}" \
      --region "${AWS_REGION}" 2>/dev/null || true
  aws logs create-log-stream \
      --log-group-name "${CW_LOG_GROUP}" \
      --log-stream-name "${CW_LOG_STREAM}" \
      --region "${AWS_REGION}" 2>/dev/null || true
}

# Sequence token file for put-log-events (not needed on newer API but kept for safety)
_CW_SEQ_FILE="/tmp/.cw-seq-token"

cw_put() {
  local message="$1"
  local ts
  ts=$(date +%s%3N)   # milliseconds since epoch

  local seq_args=()
  if [[ -f "${_CW_SEQ_FILE}" ]]; then
    local token
    token="$(cat "${_CW_SEQ_FILE}")"
    [[ -n "${token}" ]] && seq_args=(--sequence-token "${token}")
  fi

  local out
  out="$(aws logs put-log-events \
    --log-group-name "${CW_LOG_GROUP}" \
    --log-stream-name "${CW_LOG_STREAM}" \
    --log-events "[{\"timestamp\":${ts},\"message\":$(printf '%s' "${message}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}]" \
    "${seq_args[@]}" \
    --region "${AWS_REGION}" \
    --output json 2>/dev/null || true)"

  # Persist next sequence token
  if [[ -n "${out}" ]]; then
    local next
    next="$(echo "${out}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("nextSequenceToken",""))' 2>/dev/null || true)"
    echo -n "${next}" > "${_CW_SEQ_FILE}"
  fi
}

log() {
  local msg="[$(date --iso-8601=seconds)] $*"
  echo "${msg}" | tee -a "${LOG_FILE}"
  cw_put "${msg}" &   # fire-and-forget; don't block scan on CW latency
}

# Flush a whole file (e.g. docker/scanner output) to CW line-by-line
cw_flush_file() {
  local file="$1"
  [[ -f "${file}" ]] || return 0
  while IFS= read -r line; do
    cw_put "${line}" &
  done < "${file}"
}

# ── Startup ───────────────────────────────────────────────────────────────────

cw_ensure_stream
log "=== SonarQube scan starting (log-group: ${CW_LOG_GROUP}  stream: ${CW_LOG_STREAM}) ==="

if [[ ! -f "${ENV_FILE}" ]]; then
  log "ERROR: Missing ${ENV_FILE}. Copy sonar/.env.example to ${ENV_FILE} and fill secrets."
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

# ── Lifecycle helpers ─────────────────────────────────────────────────────────

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
    aws ec2 stop-instances --instance-ids "${INSTANCE_ID}" --region "${AWS_REGION}" >> "${LOG_FILE}" 2>&1 || true
  fi
}

cleanup() {
  local exit_code=$?
  if [[ ${exit_code} -ne 0 ]]; then
    log "ERROR: Script exited with code ${exit_code} — scan did NOT complete successfully"
    # Flush the full local log to CW so nothing is lost
    cw_flush_file "${LOG_FILE}"
  else
    log "=== Scan completed successfully ==="
  fi
  wait  # let background cw_put calls finish before stopping instance
  docker compose down >> "${LOG_FILE}" 2>&1 || true
  stop_runner_instance
}
trap cleanup EXIT

# ── Scan ──────────────────────────────────────────────────────────────────────

if [[ -d "${SONAR_REPO_PATH}/.git" ]]; then
  log "Updating repository at ${SONAR_REPO_PATH}"
  git -C "${SONAR_REPO_PATH}" pull --ff-only >> "${LOG_FILE}" 2>&1 \
    || log "WARNING: Repository update failed; scanning existing checkout."
fi

log "Starting SonarQube container"
docker compose up -d sonarqube >> "${LOG_FILE}" 2>&1

log "Waiting for SonarQube to become UP (timeout 300s)"
sonar_deadline=$((SECONDS + 300))
until curl -fsS "http://127.0.0.1:9000/api/system/status" 2>/dev/null | grep -q '"status":"UP"'; do
  if (( SECONDS > sonar_deadline )); then
    log "ERROR: SonarQube did not reach UP state within 300s"
    docker compose logs sonarqube >> "${LOG_FILE}" 2>&1 || true
    exit 1
  fi
  sleep 15
done
log "SonarQube is UP"

log "Running Sonar scanner"
_SCANNER_LOG="/tmp/sonar-scanner-${DATE}.log"
docker compose run --rm scanner 2>&1 | tee -a "${LOG_FILE}" "${_SCANNER_LOG}"
# Stream scanner output to CW immediately
cw_flush_file "${_SCANNER_LOG}"

# Extract the CE task ID from the scanner log so we can wait for report processing
_CE_TASK_ID="$(grep -oP '(?<=api/ce/task\?id=)[^\s]+' "${_SCANNER_LOG}" | tail -1 || true)"
if [[ -n "${_CE_TASK_ID}" ]]; then
  log "Waiting for SonarQube to process report (CE task: ${_CE_TASK_ID})"
  ce_deadline=$((SECONDS + 600))
  while true; do
    if (( SECONDS > ce_deadline )); then
      log "ERROR: CE task ${_CE_TASK_ID} did not reach SUCCESS within 600s"
      exit 1
    fi
    _CE_STATUS="$(curl -fsS -u "${SONAR_TOKEN}:" \
      "http://127.0.0.1:9000/api/ce/task?id=${_CE_TASK_ID}" 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])' 2>/dev/null || echo "UNKNOWN")"
    log "  CE task status: ${_CE_STATUS}"
    if [[ "${_CE_STATUS}" == "SUCCESS" ]]; then
      break
    elif [[ "${_CE_STATUS}" == "FAILED" || "${_CE_STATUS}" == "CANCELED" ]]; then
      log "ERROR: CE task ended with status ${_CE_STATUS}"
      exit 1
    fi
    sleep 15
  done
  log "Report processing complete"
else
  log "WARNING: Could not extract CE task ID — waiting 60s before export"
  sleep 60
fi

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
  log "  Fetched page ${page} (total issues: ${total})"
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
