import hashlib
import json
import os
from datetime import datetime, timezone

import boto3
import pymysql


s3_client = boto3.client("s3")


def connect_db():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        port=int(os.environ.get("DB_PORT", "3306")),
        autocommit=True,
        connect_timeout=10,
    )


def build_fingerprint(issue_key):
    return hashlib.sha256(f"sonarqube|{issue_key}".encode()).hexdigest()


def extract_service_name(component):
    # component format: "bugdaddy:platform/backend/main.py" → "platform/backend"
    path = component.split(":", 1)[1] if ":" in component else component
    parts = path.strip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0] if parts else component


def map_issue_type(issue):
    t = issue.get("type", "CODE_SMELL")
    severity = issue.get("severity", "MINOR")
    if t == "BUG":
        return "bug"
    if t == "VULNERABILITY":
        return "vulnerability"
    if severity in ("BLOCKER", "CRITICAL"):
        return "critical_code_smell"
    if severity == "MAJOR":
        return "major_code_smell"
    return "code_smell"


def parse_sonar_dt(dt_str):
    if not dt_str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        return datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def build_stack_trace(issue):
    component = issue.get("component", "")
    line = issue.get("line", "")
    message = issue.get("message", "")
    rule = issue.get("rule", "")
    severity = issue.get("severity", "")
    issue_type = issue.get("type", "")

    lines = [
        f"Rule:     {rule}",
        f"Severity: {severity} | Type: {issue_type}",
        f"File:     {component}" + (f":{line}" if line else ""),
        f"Message:  {message}",
    ]

    flows = issue.get("flows", [])
    if flows:
        lines.append("\nData flows:")
        for flow in flows[:5]:
            for loc in flow.get("locations", []):
                loc_line = loc.get("textRange", {}).get("startLine", "")
                loc_msg = loc.get("msg", "")
                lines.append(f"  {loc.get('component', '')}:{loc_line} — {loc_msg}")

    return "\n".join(lines)[:65000]


def upsert_issue(cursor, row):
    cursor.execute(
        "SELECT id FROM service_exception_log WHERE fingerprint = %s LIMIT 1",
        (row["fingerprint"],),
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            """UPDATE service_exception_log
               SET last_seen = %s, description = %s, stack_trace = %s,
                   entire_execution_logs = %s, issue_type = %s
               WHERE id = %s""",
            (row["last_seen"], row["description"], row["stack_trace"],
             row["entire_execution_logs"], row["issue_type"], existing[0]),
        )
        return "updated"

    cursor.execute(
        """INSERT INTO service_exception_log (
               fingerprint, service_name, issue_type, source, description,
               stack_trace, entire_execution_logs, request_id, frequency,
               first_seen, last_seen, status, assigned_to, resolution_pr,
               resolution_jira, created_at, resolved_at
           ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            row["fingerprint"], row["service_name"], row["issue_type"],
            "sonarqube", row["description"], row["stack_trace"],
            row["entire_execution_logs"], row["request_id"],
            1, row["first_seen"], row["last_seen"],
            "open", None, None, None, row["created_at"], None,
        ),
    )
    return "inserted"


def process_report(report):
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    report_date = report.get("date", now[:10])
    last_seen_dt = f"{report_date} 00:00:00"

    rows = []
    for issue in report.get("issues", []):
        rows.append({
            "fingerprint": build_fingerprint(issue["key"]),
            "service_name": extract_service_name(issue.get("component", "unknown")),
            "issue_type": map_issue_type(issue),
            "description": (issue.get("message") or "")[:1000],
            "stack_trace": build_stack_trace(issue),
            "entire_execution_logs": json.dumps(issue, indent=2)[:65000],
            "request_id": issue.get("key", ""),
            "first_seen": parse_sonar_dt(issue.get("creationDate")),
            "last_seen": last_seen_dt,
            "created_at": now,
        })
    return rows


def lambda_handler(event, context):
    total_inserted = total_updated = 0

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        print(f"Processing s3://{bucket}/{key}")

        obj = s3_client.get_object(Bucket=bucket, Key=key)
        report = json.loads(obj["Body"].read())

        rows = process_report(report)
        print(f"Report date={report.get('date')} issues={len(rows)}")

        if not rows:
            continue

        conn = connect_db()
        try:
            with conn.cursor() as cursor:
                for row in rows:
                    result = upsert_issue(cursor, row)
                    if result == "inserted":
                        total_inserted += 1
                    else:
                        total_updated += 1
        finally:
            conn.close()

        print(f"Upserted: inserted={total_inserted} updated={total_updated}")

    return {
        "statusCode": 200,
        "body": json.dumps({"inserted": total_inserted, "updated": total_updated}),
    }
