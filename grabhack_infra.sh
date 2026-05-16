#!/bin/bash
###############################################################################
# GrabHack 2.0 — Lambda + RDS Setup
# Runs against the currently configured AWS CLI credentials.
#
# Creates:
#   - Lambda security group in the default VPC
#   - IAM role for 6 Lambda functions
#   - 6 Lambda stub microservices attached to the VPC
#
# Updates:
#   - Adds MySQL ingress from the Lambda SG to the RDS security group
#
# Assumes:
#   - RDS MySQL already exists in the default VPC
#   - You will provide DB_NAME explicitly
###############################################################################

set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
PROJECT="grabhack"
DB_INSTANCE_ID="${DB_INSTANCE_ID:-database-1}"
DB_NAME="${DB_NAME:-replace-me}"

echo "============================================="
echo "  GrabHack 2.0 — Lambda + RDS Infrastructure"
echo "  Region: ${REGION}"
echo "============================================="

echo ""
echo "[1/5] Looking up RDS instance details..."
DB_HOST=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)
DB_PORT=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].Endpoint.Port' \
  --output text)
DB_USER=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].MasterUsername' \
  --output text)
VPC_ID=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].DBSubnetGroup.VpcId' \
  --output text)
RDS_SG=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
  --output text)
SUBNET_1=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].DBSubnetGroup.Subnets[0].SubnetIdentifier' \
  --output text)
SUBNET_2=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].DBSubnetGroup.Subnets[1].SubnetIdentifier' \
  --output text)
PUBLICLY_ACCESSIBLE=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].PubliclyAccessible' \
  --output text)

if [[ "$DB_NAME" == "replace-me" ]]; then
  echo "Set DB_NAME before running. Example:"
  echo "  AWS_PROFILE=admin-access-key DB_NAME=bug_daddy ./grabhack_infra.sh"
  exit 1
fi

echo "  RDS Host: $DB_HOST"
echo "  RDS Port: $DB_PORT"
echo "  RDS User: $DB_USER"
echo "  VPC:      $VPC_ID"
echo "  RDS SG:   $RDS_SG"
echo "  Subnets:  $SUBNET_1, $SUBNET_2"
echo "  Publicly Accessible: $PUBLICLY_ACCESSIBLE"

echo ""
echo "[2/5] Creating or reusing Lambda security group..."
LAMBDA_SG_NAME="${PROJECT}-lambda-sg"
LAMBDA_SG=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters "Name=group-name,Values=${LAMBDA_SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

if [[ -z "$LAMBDA_SG" || "$LAMBDA_SG" == "None" ]]; then
  LAMBDA_SG=$(aws ec2 create-security-group \
    --group-name "$LAMBDA_SG_NAME" \
    --description "GrabHack Lambda access to RDS" \
    --vpc-id "$VPC_ID" \
    --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=${LAMBDA_SG_NAME}},{Key=Project,Value=${PROJECT}}]" \
    --region "$REGION" \
    --query 'GroupId' --output text)
fi

aws ec2 authorize-security-group-ingress \
  --group-id "$RDS_SG" \
  --protocol tcp \
  --port 3306 \
  --source-group "$LAMBDA_SG" \
  --region "$REGION" > /dev/null 2>&1 || true

echo "  Lambda SG: $LAMBDA_SG"
echo "  Added: RDS accepts 3306 from Lambda SG"

echo ""
echo "[3/5] Creating or reusing Lambda execution role..."
ROLE_NAME="${PROJECT}-lambda-exec-role"
TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document "$TRUST_POLICY" \
  --tags Key=Project,Value=${PROJECT} \
  > /dev/null 2>&1 || true

aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole > /dev/null 2>&1
aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole > /dev/null 2>&1

ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)
echo "  Lambda Role: $ROLE_ARN"
echo "  Waiting 10s for IAM propagation..."
sleep 10

echo ""
echo "[4/5] Creating Lambda stub package..."
mkdir -p /tmp/lambda_pkg
cat > /tmp/lambda_pkg/lambda_function.py << 'PYEOF'
import json
import os

def lambda_handler(event, context):
    service_name = os.environ.get("SERVICE_NAME", "unknown")
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"{service_name} is operational",
            "service": service_name,
            "db_host": os.environ.get("DB_HOST"),
            "db_port": os.environ.get("DB_PORT"),
            "db_name": os.environ.get("DB_NAME"),
            "event": event
        })
    }
PYEOF

(cd /tmp/lambda_pkg && zip -q /tmp/lambda_stub.zip lambda_function.py)

echo ""
echo "[5/5] Creating Lambda functions..."
SERVICES=(
  "CustomerOnboardingService"
  "BankStatementService"
  "KYCService"
  "AutoDebitService"
  "DisbursementService"
  "SupportService"
)

for SVC in "${SERVICES[@]}"; do
  FUNC_NAME="${PROJECT}-${SVC}"
  echo "  Ensuring: $FUNC_NAME"

  if aws lambda get-function --function-name "$FUNC_NAME" --region "$REGION" > /dev/null 2>&1; then
    aws lambda update-function-code \
      --function-name "$FUNC_NAME" \
      --zip-file fileb:///tmp/lambda_stub.zip \
      --region "$REGION" > /dev/null

    aws lambda update-function-configuration \
      --function-name "$FUNC_NAME" \
      --runtime python3.13 \
      --handler lambda_function.lambda_handler \
      --role "$ROLE_ARN" \
      --timeout 30 \
      --memory-size 256 \
      --vpc-config "SubnetIds=${SUBNET_1},${SUBNET_2},SecurityGroupIds=${LAMBDA_SG}" \
      --environment "Variables={SERVICE_NAME=${SVC},DB_HOST=${DB_HOST},DB_PORT=${DB_PORT},DB_NAME=${DB_NAME},DB_USER=${DB_USER},DB_PASSWORD=${DB_PASSWORD}}" \
      --region "$REGION" > /dev/null
  else
    aws lambda create-function \
      --function-name "$FUNC_NAME" \
      --runtime python3.13 \
      --handler lambda_function.lambda_handler \
      --role "$ROLE_ARN" \
      --zip-file fileb:///tmp/lambda_stub.zip \
      --timeout 30 \
      --memory-size 256 \
      --vpc-config "SubnetIds=${SUBNET_1},${SUBNET_2},SecurityGroupIds=${LAMBDA_SG}" \
      --environment "Variables={SERVICE_NAME=${SVC},DB_HOST=${DB_HOST},DB_PORT=${DB_PORT},DB_NAME=${DB_NAME},DB_USER=${DB_USER},DB_PASSWORD=${DB_PASSWORD}}" \
      --tags "Project=${PROJECT}" \
      --region "$REGION" > /dev/null
  fi

  echo "    ✓ $FUNC_NAME"
done

echo ""
echo "============================================="
echo "  LAMBDA + RDS SETUP READY"
echo "============================================="
echo ""
echo "  RDS Instance:   $DB_INSTANCE_ID"
echo "  RDS Host:       $DB_HOST"
echo "  RDS Port:       $DB_PORT"
echo "  DB Name:        $DB_NAME"
echo "  DB User:        $DB_USER"
echo "  Lambda SG:      $LAMBDA_SG"
echo "  RDS SG:         $RDS_SG"
echo "  Lambda Role:    $ROLE_NAME"
echo ""
echo "  Lambda Functions:"
for SVC in "${SERVICES[@]}"; do
  echo "    - ${PROJECT}-${SVC}"
done
echo ""
