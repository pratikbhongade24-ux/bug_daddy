# BugDaddy SonarQube Kit

This folder manages the BugDaddy SonarQube setup from the repo root. It keeps the existing MySQL RDS untouched and creates a separate tiny PostgreSQL RDS instance for SonarQube.

## What It Creates

- Private S3 bucket for JSON reports: `bugdaddy-sonar-reports`
- Dedicated PostgreSQL RDS: `bugdaddy-sonarqube-postgres`
- PostgreSQL security group that allows `5432` only from the Sonar runner security group
- Dedicated Sonar runner EC2: `bugdaddy-sonar-runner`
- Runner EC2 role permissions for SSM, S3 report upload/download, and self-stop after scans
- Lambda function that starts the runner when needed and triggers an SSM Run Command
- EventBridge schedule for daily scans at 2:00 PM IST
- Runner-side Docker Compose setup for SonarQube Community and Sonar Scanner

Defaults are in the scripts and can be overridden with environment variables.

## Defaults

```bash
AWS_PROFILE=bug-daddy
AWS_REGION=ap-south-1
APP_EC2_INSTANCE_ID=i-0f67a42919b9f7a27
SONAR_RUNNER_INSTANCE_NAME=bugdaddy-sonar-runner
SONAR_RUNNER_INSTANCE_TYPE=t3.small
APP_DB_INSTANCE_ID=database-1
SONAR_DB_INSTANCE_ID=bugdaddy-sonarqube-postgres
SONAR_DB_NAME=sonarqube
SONAR_DB_USER=sonar
S3_BUCKET=bugdaddy-sonar-reports
REPO_URL=https://github.com/pratikbhongade24-ux/bug_daddy
SONAR_SCHEDULE='cron(30 8 * * ? *)'
```

## Setup Order

From the repo root:

```bash
sonar/setup-aws.sh preflight
sonar/setup-aws.sh apply
sonar/bootstrap-ec2.sh
```

`setup-aws.sh apply` writes generated local runtime files under `sonar/.generated/`. That directory is ignored by git because it may contain the generated PostgreSQL password and a runtime `.env` template.

## First SonarQube Login And Token

After EC2 bootstrap, find the runner public IP:

```bash
aws --profile bug-daddy --region ap-south-1 ec2 describe-instances \
  --filters "Name=tag:Name,Values=bugdaddy-sonar-runner" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text
```

Open an SSH tunnel to that runner:

```bash
ssh -i "$HOME/.ssh/bug-daddy-key.pem" -L 9000:127.0.0.1:9000 ubuntu@<sonar-runner-public-ip>
```

In another terminal, start SonarQube once:

```bash
ssh -i "$HOME/.ssh/bug-daddy-key.pem" ubuntu@<sonar-runner-public-ip> 'cd /opt/sonarqube && docker compose up -d sonarqube'
```

Open `http://127.0.0.1:9000`. The default first login is normally `admin` / `admin`; SonarQube will force a password change. Create a user token, then update this line on EC2:

```bash
/opt/sonarqube/.env
```

Set:

```bash
SONAR_TOKEN=your-token
```

Then stop the service until the scheduled scan:

```bash
ssh -i "$HOME/.ssh/bug-daddy-key.pem" ubuntu@<sonar-runner-public-ip> 'cd /opt/sonarqube && docker compose down'
```

The runner can be stopped after token setup. Scheduled or UI-triggered scans will start it again automatically.

## Manual Scan

```bash
aws --profile bug-daddy --region ap-south-1 lambda invoke \
  --function-name bugdaddy-sonar-scan-trigger \
  --payload '{}' \
  /tmp/sonar-lambda-response.json
```

Logs are written to:

```bash
/var/log/sonar-scan.log
```

Reports are uploaded to:

```bash
s3://bugdaddy-sonar-reports/YYYY-MM-DD/report.json
```

## Scheduled Scan

EventBridge invokes Lambda daily with:

```bash
cron(30 8 * * ? *)
```

That is 2:00 PM IST.

The Lambda starts the dedicated Sonar runner EC2 if it is stopped, waits for SSM to come online, then calls SSM `AWS-RunShellScript` and runs:

```bash
/opt/sonarqube/run-scan.sh
```

At the end of a successful scan, `run-scan.sh` stops the SonarQube containers and stops the runner EC2 instance.

## Access A Report

Generate a presigned URL for today:

```bash
sonar/presign-report.sh
```

Generate one for a specific date:

```bash
sonar/presign-report.sh 2026-05-09
```

Override expiry:

```bash
EXPIRES_IN=7200 sonar/presign-report.sh 2026-05-09
```

## Files

- `setup-aws.sh`: provisions S3, PostgreSQL RDS, IAM, Lambda, and EventBridge.
- `bootstrap-ec2.sh`: installs EC2 dependencies and places the Sonar runtime under `/opt/sonarqube`.
- `docker-compose.yml`: runs SonarQube Community and Sonar Scanner.
- `run-scan.sh`: performs the scan, exports paginated issues, uploads report JSON, and stops containers.
- `lambda_function.py`: Lambda SSM trigger.
- `presign-report.sh`: creates report URLs.
- `setup-sonar-db.sql`: optional manual PostgreSQL SQL template.
- `policies/`: reference IAM policy templates.

## Validation

Run local checks:

```bash
bash -n sonar/*.sh
docker compose -f sonar/docker-compose.yml config
```

The Docker Compose check requires Docker Compose on the local machine. The AWS scripts require valid `bug-daddy` profile credentials.
