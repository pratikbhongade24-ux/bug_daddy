#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-preflight}"

AWS_PROFILE="${AWS_PROFILE:-bug-daddy}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
PROJECT="${PROJECT:-bugdaddy}"

APP_DB_INSTANCE_ID="${APP_DB_INSTANCE_ID:-database-1}"
APP_EC2_INSTANCE_ID="${APP_EC2_INSTANCE_ID:-i-0f67a42919b9f7a27}"
SONAR_RUNNER_INSTANCE_NAME="${SONAR_RUNNER_INSTANCE_NAME:-bugdaddy-sonar-runner}"
SONAR_RUNNER_INSTANCE_TYPE="${SONAR_RUNNER_INSTANCE_TYPE:-t3.small}"
SONAR_RUNNER_ROLE_NAME="${SONAR_RUNNER_ROLE_NAME:-bugdaddy-sonar-runner-role}"
SONAR_RUNNER_INSTANCE_PROFILE="${SONAR_RUNNER_INSTANCE_PROFILE:-bugdaddy-sonar-runner-profile}"
EC2_INSTANCE_ID="${EC2_INSTANCE_ID:-}"

S3_BUCKET="${S3_BUCKET:-bugdaddy-sonar-reports}"
SONAR_DB_INSTANCE_ID="${SONAR_DB_INSTANCE_ID:-bugdaddy-sonarqube-postgres}"
SONAR_DB_NAME="${SONAR_DB_NAME:-sonarqube}"
SONAR_DB_USER="${SONAR_DB_USER:-sonar}"
SONAR_DB_INSTANCE_CLASS="${SONAR_DB_INSTANCE_CLASS:-db.t4g.micro}"
SONAR_DB_STORAGE_GB="${SONAR_DB_STORAGE_GB:-20}"
SONAR_DB_MAX_STORAGE_GB="${SONAR_DB_MAX_STORAGE_GB:-100}"

SONAR_LAMBDA_NAME="${SONAR_LAMBDA_NAME:-bugdaddy-sonar-scan-trigger}"
SONAR_LAMBDA_ROLE_NAME="${SONAR_LAMBDA_ROLE_NAME:-bugdaddy-sonar-lambda-role}"
SONAR_EVENT_RULE_NAME="${SONAR_EVENT_RULE_NAME:-bugdaddy-sonar-daily-scan}"
SONAR_SCHEDULE="${SONAR_SCHEDULE:-cron(30 8 * * ? *)}"

SONAR_HOME="${SONAR_HOME:-/opt/sonarqube}"
SONAR_PROJECT_KEY="${SONAR_PROJECT_KEY:-bugdaddy}"
SONAR_PROJECT_NAME="${SONAR_PROJECT_NAME:-BugDaddy}"
SONAR_REPO_PATH="${SONAR_REPO_PATH:-/opt/sonarqube/bug_daddy}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SONAR_DIR="${ROOT_DIR}/sonar"
GENERATED_DIR="${SONAR_DIR}/.generated"
mkdir -p "${GENERATED_DIR}"

aws_cmd() {
  aws --profile "${AWS_PROFILE}" --region "${AWS_REGION}" "$@"
}

aws_global() {
  aws --profile "${AWS_PROFILE}" "$@"
}

usage() {
  cat <<EOF
Usage: AWS_PROFILE=${AWS_PROFILE} $0 [preflight|apply]

preflight  Validate account, EC2, and existing RDS network discovery.
apply      Create/update S3, RDS PostgreSQL, IAM, Lambda, and EventBridge.
EOF
}

if [[ "${ACTION}" != "preflight" && "${ACTION}" != "apply" ]]; then
  usage
  exit 2
fi

json_value() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

path, expr = sys.argv[1:3]
with open(path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

value = payload
for part in expr.split("."):
    if part.isdigit():
        value = value[int(part)]
    else:
        value = value[part]
if isinstance(value, list):
    print(" ".join(str(item) for item in value))
else:
    print(value)
PY
}

generate_password() {
  python3 <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits
print("".join(secrets.choice(alphabet) for _ in range(28)))
PY
}

ensure_password() {
  if [[ -n "${SONAR_DB_PASSWORD:-}" ]]; then
    return
  fi

  local password_file="${GENERATED_DIR}/sonar-db-password.txt"
  if [[ -f "${password_file}" ]]; then
    SONAR_DB_PASSWORD="$(<"${password_file}")"
  else
    if aws_cmd rds describe-db-instances --db-instance-identifier "${SONAR_DB_INSTANCE_ID}" >/dev/null 2>&1; then
      echo "RDS instance ${SONAR_DB_INSTANCE_ID} already exists, but no password was provided and ${password_file} is missing."
      echo "Set SONAR_DB_PASSWORD in the environment before running apply."
      exit 1
    fi
    SONAR_DB_PASSWORD="$(generate_password)"
    umask 077
    printf '%s\n' "${SONAR_DB_PASSWORD}" > "${password_file}"
  fi
  export SONAR_DB_PASSWORD
}

echo "Using AWS profile ${AWS_PROFILE} in ${AWS_REGION}"
ACCOUNT_ID="$(aws_cmd sts get-caller-identity --query Account --output text)"
echo "AWS account: ${ACCOUNT_ID}"

APP_DB_JSON="${GENERATED_DIR}/app-db.json"
EC2_JSON="${GENERATED_DIR}/ec2-instance.json"

aws_cmd rds describe-db-instances \
  --db-instance-identifier "${APP_DB_INSTANCE_ID}" \
  > "${APP_DB_JSON}"

aws_cmd ec2 describe-instances \
  --instance-ids "${APP_EC2_INSTANCE_ID}" \
  > "${EC2_JSON}"

APP_DB_ENGINE="$(json_value "${APP_DB_JSON}" "DBInstances.0.Engine")"
VPC_ID="$(json_value "${APP_DB_JSON}" "DBInstances.0.DBSubnetGroup.VpcId")"
APP_DB_SUBNET_GROUP="$(json_value "${APP_DB_JSON}" "DBInstances.0.DBSubnetGroup.DBSubnetGroupName")"
SUBNET_IDS="$(python3 - "${APP_DB_JSON}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)
print(" ".join(s["SubnetIdentifier"] for s in payload["DBInstances"][0]["DBSubnetGroup"]["Subnets"]))
PY
)"
EC2_SECURITY_GROUP_IDS="$(python3 - "${EC2_JSON}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)
instance = payload["Reservations"][0]["Instances"][0]
print(" ".join(group["GroupId"] for group in instance["SecurityGroups"]))
PY
)"
EC2_PRIMARY_SG="${EC2_SECURITY_GROUP_IDS%% *}"
APP_IMAGE_ID="$(json_value "${EC2_JSON}" "Reservations.0.Instances.0.ImageId")"
APP_SUBNET_ID="$(json_value "${EC2_JSON}" "Reservations.0.Instances.0.SubnetId")"
APP_KEY_NAME="$(json_value "${EC2_JSON}" "Reservations.0.Instances.0.KeyName")"

echo "Existing app DB: ${APP_DB_INSTANCE_ID} (${APP_DB_ENGINE})"
echo "VPC: ${VPC_ID}"
echo "App DB subnet group: ${APP_DB_SUBNET_GROUP}"
echo "Subnets: ${SUBNET_IDS}"
echo "App EC2 instance: ${APP_EC2_INSTANCE_ID}"
echo "App EC2 security groups: ${EC2_SECURITY_GROUP_IDS}"
echo "Sonar runner: ${SONAR_RUNNER_INSTANCE_NAME} (${SONAR_RUNNER_INSTANCE_TYPE})"

if [[ "${ACTION}" == "preflight" ]]; then
  echo "Preflight complete. Run '$0 apply' to create/update Sonar resources."
  exit 0
fi

ensure_password

echo "[1/8] Ensuring private S3 bucket ${S3_BUCKET}"
if ! aws_cmd s3api head-bucket --bucket "${S3_BUCKET}" >/dev/null 2>&1; then
  aws_cmd s3api create-bucket \
    --bucket "${S3_BUCKET}" \
    --create-bucket-configuration "LocationConstraint=${AWS_REGION}" \
    >/dev/null
fi
aws_cmd s3api put-public-access-block \
  --bucket "${S3_BUCKET}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws_cmd s3api put-bucket-encryption \
  --bucket "${S3_BUCKET}" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

echo "[2/8] Ensuring dedicated Sonar runner EC2"
RUNNER_TRUST_POLICY="${GENERATED_DIR}/runner-trust-policy.json"
cat > "${RUNNER_TRUST_POLICY}" <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws_global iam create-role \
  --role-name "${SONAR_RUNNER_ROLE_NAME}" \
  --assume-role-policy-document "file://${RUNNER_TRUST_POLICY}" \
  --tags Key=Project,Value="${PROJECT}" Key=Service,Value=sonarqube \
  >/dev/null 2>&1 || true

aws_global iam attach-role-policy \
  --role-name "${SONAR_RUNNER_ROLE_NAME}" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore \
  >/dev/null

cat > "${GENERATED_DIR}/runner-inline-policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::${S3_BUCKET}/*"
    },
    {
      "Effect": "Allow",
      "Action": "ec2:StopInstances",
      "Resource": "arn:aws:ec2:${AWS_REGION}:${ACCOUNT_ID}:instance/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/Name": "${SONAR_RUNNER_INSTANCE_NAME}"
        }
      }
    }
  ]
}
EOF

aws_global iam put-role-policy \
  --role-name "${SONAR_RUNNER_ROLE_NAME}" \
  --policy-name "${PROJECT}-sonar-runner-inline" \
  --policy-document "file://${GENERATED_DIR}/runner-inline-policy.json"

aws_global iam create-instance-profile \
  --instance-profile-name "${SONAR_RUNNER_INSTANCE_PROFILE}" \
  >/dev/null 2>&1 || true
aws_global iam add-role-to-instance-profile \
  --instance-profile-name "${SONAR_RUNNER_INSTANCE_PROFILE}" \
  --role-name "${SONAR_RUNNER_ROLE_NAME}" \
  >/dev/null 2>&1 || true

EC2_INSTANCE_ID="$(aws_cmd ec2 describe-instances \
  --filters "Name=tag:Name,Values=${SONAR_RUNNER_INSTANCE_NAME}" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text 2>/dev/null || true)"

if [[ -z "${EC2_INSTANCE_ID}" || "${EC2_INSTANCE_ID}" == "None" ]]; then
  sleep 10
  EC2_INSTANCE_ID="$(aws_cmd ec2 run-instances \
    --image-id "${APP_IMAGE_ID}" \
    --instance-type "${SONAR_RUNNER_INSTANCE_TYPE}" \
    --key-name "${APP_KEY_NAME}" \
    --subnet-id "${APP_SUBNET_ID}" \
    --security-group-ids ${EC2_SECURITY_GROUP_IDS} \
    --iam-instance-profile "Name=${SONAR_RUNNER_INSTANCE_PROFILE}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${SONAR_RUNNER_INSTANCE_NAME}},{Key=Project,Value=${PROJECT}},{Key=Service,Value=sonarqube}]" \
    --query 'Instances[0].InstanceId' \
    --output text)"
  aws_cmd ec2 wait instance-running --instance-ids "${EC2_INSTANCE_ID}"
fi

RUNNER_PUBLIC_IP="$(aws_cmd ec2 describe-instances \
  --instance-ids "${EC2_INSTANCE_ID}" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)"
RUNNER_PRIVATE_IP="$(aws_cmd ec2 describe-instances \
  --instance-ids "${EC2_INSTANCE_ID}" \
  --query 'Reservations[0].Instances[0].PrivateIpAddress' \
  --output text)"
echo "  Sonar runner instance: ${EC2_INSTANCE_ID}"
echo "  Sonar runner public IP: ${RUNNER_PUBLIC_IP}"
echo "  Sonar runner private IP: ${RUNNER_PRIVATE_IP}"

echo "[3/8] Ensuring PostgreSQL security group"
SONAR_DB_SG_NAME="${PROJECT}-sonar-postgres-sg"
SONAR_DB_SG="$(aws_cmd ec2 describe-security-groups \
  --filters "Name=group-name,Values=${SONAR_DB_SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null || true)"

if [[ -z "${SONAR_DB_SG}" || "${SONAR_DB_SG}" == "None" ]]; then
  SONAR_DB_SG="$(aws_cmd ec2 create-security-group \
    --group-name "${SONAR_DB_SG_NAME}" \
    --description "BugDaddy SonarQube PostgreSQL access from EC2" \
    --vpc-id "${VPC_ID}" \
    --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=${SONAR_DB_SG_NAME}},{Key=Project,Value=${PROJECT}},{Key=Service,Value=sonarqube}]" \
    --query GroupId \
    --output text)"
fi

aws_cmd ec2 authorize-security-group-ingress \
  --group-id "${SONAR_DB_SG}" \
  --protocol tcp \
  --port 5432 \
  --source-group "${EC2_PRIMARY_SG}" \
  >/dev/null 2>&1 || true

echo "[4/8] Ensuring RDS subnet group"
SONAR_DB_SUBNET_GROUP="${PROJECT}-sonar-postgres-subnets"
if ! aws_cmd rds describe-db-subnet-groups --db-subnet-group-name "${SONAR_DB_SUBNET_GROUP}" >/dev/null 2>&1; then
  aws_cmd rds create-db-subnet-group \
    --db-subnet-group-name "${SONAR_DB_SUBNET_GROUP}" \
    --db-subnet-group-description "BugDaddy SonarQube PostgreSQL subnet group" \
    --subnet-ids ${SUBNET_IDS} \
    --tags Key=Project,Value="${PROJECT}" Key=Service,Value=sonarqube \
    >/dev/null
fi

echo "[5/8] Ensuring tiny PostgreSQL RDS ${SONAR_DB_INSTANCE_ID}"
if ! aws_cmd rds describe-db-instances --db-instance-identifier "${SONAR_DB_INSTANCE_ID}" >/dev/null 2>&1; then
  aws_cmd rds create-db-instance \
    --db-instance-identifier "${SONAR_DB_INSTANCE_ID}" \
    --db-instance-class "${SONAR_DB_INSTANCE_CLASS}" \
    --engine postgres \
    --allocated-storage "${SONAR_DB_STORAGE_GB}" \
    --max-allocated-storage "${SONAR_DB_MAX_STORAGE_GB}" \
    --storage-type gp3 \
    --master-username "${SONAR_DB_USER}" \
    --master-user-password "${SONAR_DB_PASSWORD}" \
    --db-name "${SONAR_DB_NAME}" \
    --vpc-security-group-ids "${SONAR_DB_SG}" \
    --db-subnet-group-name "${SONAR_DB_SUBNET_GROUP}" \
    --backup-retention-period 1 \
    --no-publicly-accessible \
    --storage-encrypted \
    --no-multi-az \
    --no-deletion-protection \
    --copy-tags-to-snapshot \
    --tags Key=Project,Value="${PROJECT}" Key=Service,Value=sonarqube \
    >/dev/null

  echo "Waiting for ${SONAR_DB_INSTANCE_ID} to become available"
  aws_cmd rds wait db-instance-available --db-instance-identifier "${SONAR_DB_INSTANCE_ID}"
fi

SONAR_DB_HOST="$(aws_cmd rds describe-db-instances \
  --db-instance-identifier "${SONAR_DB_INSTANCE_ID}" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)"
SONAR_DB_PORT="$(aws_cmd rds describe-db-instances \
  --db-instance-identifier "${SONAR_DB_INSTANCE_ID}" \
  --query 'DBInstances[0].Endpoint.Port' \
  --output text)"

echo "[6/8] Ensuring app EC2 role can invoke Sonar Lambda"
INSTANCE_PROFILE_ARN="$(aws_cmd ec2 describe-instances \
  --instance-ids "${APP_EC2_INSTANCE_ID}" \
  --query 'Reservations[0].Instances[0].IamInstanceProfile.Arn' \
  --output text)"

if [[ -z "${INSTANCE_PROFILE_ARN}" || "${INSTANCE_PROFILE_ARN}" == "None" ]]; then
  echo "EC2 instance has no IAM instance profile. Attach one, then add SSM and S3 policies."
  exit 1
else
  INSTANCE_PROFILE_NAME="${INSTANCE_PROFILE_ARN##*/}"
  EC2_ROLE_NAME="$(aws_global iam get-instance-profile \
    --instance-profile-name "${INSTANCE_PROFILE_NAME}" \
    --query 'InstanceProfile.Roles[0].RoleName' \
    --output text)"

  aws_global iam attach-role-policy \
    --role-name "${EC2_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore \
    >/dev/null

  cat > "${GENERATED_DIR}/ec2-s3-policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::${S3_BUCKET}/*"
    }
  ]
}
EOF
  aws_global iam put-role-policy \
    --role-name "${EC2_ROLE_NAME}" \
    --policy-name "${PROJECT}-sonar-s3-access" \
    --policy-document "file://${GENERATED_DIR}/ec2-s3-policy.json"

  cat > "${GENERATED_DIR}/ec2-lambda-invoke-policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${SONAR_LAMBDA_NAME}"
    }
  ]
}
EOF
  aws_global iam put-role-policy \
    --role-name "${EC2_ROLE_NAME}" \
    --policy-name "${PROJECT}-sonar-lambda-invoke" \
    --policy-document "file://${GENERATED_DIR}/ec2-lambda-invoke-policy.json"
fi

echo "[7/8] Ensuring Lambda trigger"
TRUST_POLICY="${GENERATED_DIR}/lambda-trust-policy.json"
cat > "${TRUST_POLICY}" <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws_global iam create-role \
  --role-name "${SONAR_LAMBDA_ROLE_NAME}" \
  --assume-role-policy-document "file://${TRUST_POLICY}" \
  --tags Key=Project,Value="${PROJECT}" Key=Service,Value=sonarqube \
  >/dev/null 2>&1 || true

aws_global iam attach-role-policy \
  --role-name "${SONAR_LAMBDA_ROLE_NAME}" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
  >/dev/null

cat > "${GENERATED_DIR}/lambda-ssm-policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": [
        "arn:aws:ec2:${AWS_REGION}:${ACCOUNT_ID}:instance/${EC2_INSTANCE_ID}",
        "arn:aws:ssm:${AWS_REGION}::document/AWS-RunShellScript",
        "arn:aws:ssm:${AWS_REGION}:${ACCOUNT_ID}:document/AWS-RunShellScript"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:StartInstances"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "ssm:DescribeInstanceInformation",
      "Resource": "*"
    }
  ]
}
EOF

aws_global iam put-role-policy \
  --role-name "${SONAR_LAMBDA_ROLE_NAME}" \
  --policy-name "${PROJECT}-sonar-send-ssm" \
  --policy-document "file://${GENERATED_DIR}/lambda-ssm-policy.json"

LAMBDA_ROLE_ARN="$(aws_global iam get-role \
  --role-name "${SONAR_LAMBDA_ROLE_NAME}" \
  --query 'Role.Arn' \
  --output text)"

rm -f "${GENERATED_DIR}/lambda.zip"
(cd "${SONAR_DIR}" && zip -q "${GENERATED_DIR}/lambda.zip" lambda_function.py)
sleep 10

if aws_cmd lambda get-function --function-name "${SONAR_LAMBDA_NAME}" >/dev/null 2>&1; then
  aws_cmd lambda update-function-code \
    --function-name "${SONAR_LAMBDA_NAME}" \
    --zip-file "fileb://${GENERATED_DIR}/lambda.zip" \
    >/dev/null
  aws_cmd lambda update-function-configuration \
    --function-name "${SONAR_LAMBDA_NAME}" \
    --runtime python3.12 \
    --handler lambda_function.lambda_handler \
    --role "${LAMBDA_ROLE_ARN}" \
    --timeout 300 \
    --memory-size 128 \
    --environment "Variables={SONAR_INSTANCE_ID=${EC2_INSTANCE_ID},SONAR_SCAN_COMMAND=${SONAR_HOME}/run-scan.sh,SONAR_SSM_WAIT_SECONDS=240}" \
    >/dev/null
else
  aws_cmd lambda create-function \
    --function-name "${SONAR_LAMBDA_NAME}" \
    --runtime python3.12 \
    --handler lambda_function.lambda_handler \
    --role "${LAMBDA_ROLE_ARN}" \
    --zip-file "fileb://${GENERATED_DIR}/lambda.zip" \
    --timeout 300 \
    --memory-size 128 \
    --environment "Variables={SONAR_INSTANCE_ID=${EC2_INSTANCE_ID},SONAR_SCAN_COMMAND=${SONAR_HOME}/run-scan.sh,SONAR_SSM_WAIT_SECONDS=240}" \
    --tags Project="${PROJECT}",Service=sonarqube \
    >/dev/null
fi

LAMBDA_ARN="$(aws_cmd lambda get-function \
  --function-name "${SONAR_LAMBDA_NAME}" \
  --query 'Configuration.FunctionArn' \
  --output text)"

echo "[8/8] Ensuring EventBridge schedule"
RULE_ARN="$(aws_cmd events put-rule \
  --name "${SONAR_EVENT_RULE_NAME}" \
  --schedule-expression "${SONAR_SCHEDULE}" \
  --state ENABLED \
  --description "Daily BugDaddy SonarQube scan" \
  --query RuleArn \
  --output text)"

aws_cmd lambda add-permission \
  --function-name "${SONAR_LAMBDA_NAME}" \
  --statement-id "${SONAR_EVENT_RULE_NAME}" \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "${RULE_ARN}" \
  >/dev/null 2>&1 || true

aws_cmd events put-targets \
  --rule "${SONAR_EVENT_RULE_NAME}" \
  --targets "Id=${SONAR_LAMBDA_NAME},Arn=${LAMBDA_ARN}" \
  >/dev/null

cat > "${GENERATED_DIR}/.env.runtime" <<EOF
AWS_REGION=${AWS_REGION}
S3_BUCKET=${S3_BUCKET}
SONAR_PROJECT_KEY=${SONAR_PROJECT_KEY}
SONAR_PROJECT_NAME=${SONAR_PROJECT_NAME}
SONAR_REPO_PATH=${SONAR_REPO_PATH}
SONAR_DB_HOST=${SONAR_DB_HOST}
SONAR_DB_PORT=${SONAR_DB_PORT}
SONAR_DB_NAME=${SONAR_DB_NAME}
SONAR_DB_USER=${SONAR_DB_USER}
SONAR_DB_PASSWORD=${SONAR_DB_PASSWORD}
SONAR_TOKEN=replace-with-sonarqube-token
EOF
chmod 600 "${GENERATED_DIR}/.env.runtime"

echo ""
echo "Sonar AWS setup complete."
echo "PostgreSQL endpoint: ${SONAR_DB_HOST}:${SONAR_DB_PORT}"
echo "Sonar runner instance: ${EC2_INSTANCE_ID}"
echo "Sonar runner public IP: ${RUNNER_PUBLIC_IP}"
echo "Runtime env written to sonar/.generated/.env.runtime"
echo "Run sonar/bootstrap-ec2.sh next, then create a SonarQube token and update /opt/sonarqube/.env on EC2."
