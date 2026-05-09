#!/usr/bin/env bash
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-bug-daddy}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
S3_BUCKET="${S3_BUCKET:-bugdaddy-sonar-reports}"
REPORT_DATE="${1:-$(date +%Y-%m-%d)}"
EXPIRES_IN="${EXPIRES_IN:-3600}"

aws s3 presign "s3://${S3_BUCKET}/${REPORT_DATE}/report.json" \
  --expires-in "${EXPIRES_IN}" \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}"
