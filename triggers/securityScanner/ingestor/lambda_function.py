"""
Security Scanner Report Ingestor (Lambda)

Triggered by S3 PutObject on the security-scan-reports/ prefix.
Reads the JSON report, maps each CVE finding to a row in
service_exception_log, and upserts (insert new / update existing)
using the same fingerprint-dedup pattern as SonarReportIngestor.

Environment variables required:
    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
    DB_PORT  (optional, default 3306)
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import boto3
import pymysql


s3_client = boto3.client("s3")

_SEVERITY_TO_ISSUE_TYPE = {
    "CRITICAL": "cve_critical",
    "HIGH": "cve_high",
    "MEDIUM": "cve_medium",
    "LOW": "cve_low",
    "UNKNOWN": "cve_low",
}


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _connect_db():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        port=int(os.environ.get("DB_PORT", "3306")),
        autocommit=True,
        connect_timeout=10,
    )


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def _canonical_vuln_id(finding: dict) -> str:
    ids = [finding.get("cve_id", ""), *(finding.get("aliases") or [])]
    for value in ids:
        if isinstance(value, str) and value.startswith("CVE-"):
            return value
    for value in ids:
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _build_fingerprint(finding: dict) -> str:
    asset_id = (
        finding.get("asset_id")
        or finding.get("function_arn")
        or finding.get("resource_id")
        or finding.get("service")
        or "unknown"
    )
    component = finding.get("component") or finding.get("package_name") or "unknown"
    identity = "|".join([
        "security_scanner",
        _canonical_vuln_id(finding).strip().lower(),
        str(asset_id).strip().lower(),
        str(component).strip().lower(),
    ])
    return hashlib.sha256(identity.encode()).hexdigest()


def _build_stack_trace(finding: dict) -> str:
    lines = [
        f"CVE ID:    {finding.get('cve_id', '')}",
        f"Source:    {finding.get('source', '')}",
        f"Severity:  {finding.get('severity', '')}  CVSS: {finding.get('cvss_score', 'N/A')}",
        f"Component: {finding.get('component', '')} {finding.get('affected_version', '')} ({finding.get('component_type', '')})",
        f"Service:   {finding.get('service', '')} ({finding.get('asset_type', '')})",
        f"Published: {finding.get('published', '')}",
        "",
        f"Description: {finding.get('description', '')}",
    ]
    return "\n".join(lines)[:65000]


def _finding_to_row(finding: dict, scan_date: str, now: str) -> dict:
    cve_id = _canonical_vuln_id(finding)
    service = finding.get("service", "unknown")
    severity = finding.get("severity", "UNKNOWN").upper()

    return {
        "fingerprint": _build_fingerprint(finding),
        "service_name": service,
        "issue_type": _SEVERITY_TO_ISSUE_TYPE.get(severity, "cve_low"),
        "source": "security_scanner",
        "description": f"[{cve_id}] {finding.get('description', '')}"[:1000],
        "stack_trace": _build_stack_trace(finding),
        "entire_execution_logs": json.dumps(finding, indent=2)[:65000],
        "request_id": cve_id,
        "first_seen": f"{scan_date} 00:00:00",
        "last_seen": f"{scan_date} 00:00:00",
        "created_at": now,
    }


# ---------------------------------------------------------------------------
# Upsert (same pattern as SonarReportIngestor)
# ---------------------------------------------------------------------------

def _upsert(cursor, row: dict) -> str:
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
            (
                row["last_seen"], row["description"], row["stack_trace"],
                row["entire_execution_logs"], row["issue_type"], existing[0],
            ),
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
            row["source"], row["description"], row["stack_trace"],
            row["entire_execution_logs"], row["request_id"],
            1, row["first_seen"], row["last_seen"],
            "open", None, None, None, row["created_at"], None,
        ),
    )
    return "inserted"


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    total_inserted = total_updated = 0
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        print(f"Processing s3://{bucket}/{key}")

        obj = s3_client.get_object(Bucket=bucket, Key=key)
        report = json.loads(obj["Body"].read())

        findings = report.get("findings", [])
        scan_date = report.get("date", now[:10])
        print(f"Scan date={scan_date}  findings={len(findings)}")

        if not findings:
            continue

        rows = [_finding_to_row(f, scan_date, now) for f in findings]

        conn = _connect_db()
        try:
            with conn.cursor() as cursor:
                for row in rows:
                    result = _upsert(cursor, row)
                    if result == "inserted":
                        total_inserted += 1
                    else:
                        total_updated += 1
        finally:
            conn.close()

        print(f"Upserted: inserted={total_inserted}  updated={total_updated}")

    return {
        "statusCode": 200,
        "body": json.dumps({"inserted": total_inserted, "updated": total_updated}),
    }
