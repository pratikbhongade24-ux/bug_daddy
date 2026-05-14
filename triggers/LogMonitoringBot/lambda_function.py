import base64
import boto3
import gzip
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

import pymysql


# -------------------------------------------------------------------------
# Log line prefixes – defined once to avoid duplicated literals (SonarQube S1192)
# -------------------------------------------------------------------------
START_REQUEST_ID_PREFIX = "START RequestId:"
END_REQUEST_ID_PREFIX   = "END RequestId:"
REPORT_REQUEST_ID_PREFIX = "REPORT RequestId:"

logs_client = boto3.client("logs")

def decode_logs_event(event):
    logs_data = event.get("awslogs", {}).get("data")
    if not logs_data:
        return {"messageType": "CONTROL_MESSAGE", "logEvents": []}
    compressed_payload = base64.b64decode(logs_data)
    decompressed_payload = gzip.decompress(compressed_payload)
    return json.loads(decompressed_payload)

def utc_datetime_from_ms(timestamp_ms):
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

def extract_service_name(log_group):
    return log_group.rsplit("/", 1)[-1] if log_group else "unknown"

def extract_issue_type(message):
    lowered = message.lower()
    if "timeout" in lowered:
        return "timeout"
    if "database" in lowered or "sql" in lowered or "mysql" in lowered:
        return "database_exception"
    if "traceback" in lowered:
        return "python_traceback"
    if "exception" in lowered:
        return "exception"
    if "error" in lowered:
        return "error"
    return "log_exception"

def normalize_message(message):
    return " ".join(message.strip().split())

def normalize_fingerprint_message(message):
    normalized = normalize_message(message)
    normalized = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "<uuid>",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\bRequestId:\s*[A-Za-z0-9-]+\b", "RequestId:<id>", normalized)
    normalized = re.sub(r"\b[A-Z]+-\d+\b", "<ticket>", normalized)
    normalized = re.sub(r"\b[A-Z]\d+\b", "<entity>", normalized)
    normalized = re.sub(r"\b\d+\b", "<num>", normalized)
    return normalized

def build_fingerprint(service_name, issue_type, message):
    normalized = (
        f"{service_name}|{issue_type}|{normalize_fingerprint_message(message)}"
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def summarize_message(message):
    first_line = message.strip().splitlines()[0] if message.strip() else "No message"
    return first_line[:1000]

def fetch_log_stream_events(log_group, log_stream, start_time, end_time):
    events = []
    next_token = None

    while True:
        kwargs = {
            "logGroupName": log_group,
            "logStreamName": log_stream,
            "startTime": max(start_time - 60000, 0),
            "endTime": end_time + 60000,
            "startFromHead": True,
        }
        if next_token:
            kwargs["nextToken"] = next_token

        response = logs_client.get_log_events(**kwargs)
        batch = response.get("events", [])
        events.extend(batch)

        new_token = response.get("nextForwardToken")
        if not batch or new_token == next_token:
            break
        next_token = new_token

    return events

def find_invocation_window(stream_events, matched_signatures):
    matched_indexes = [
        index
        for index, event in enumerate(stream_events)
        if (event.get("timestamp"), event.get("message", "").strip()) in matched_signatures
    ]
    if not matched_indexes:
        return stream_events

    target_index = matched_indexes[0]
    start_index = target_index
    while start_index > 0:
        message = stream_events[start_index].get("message", "")
        if message.startswith(START_REQUEST_ID_PREFIX):
            break
        start_index -= 1

    end_index = target_index
    while end_index < len(stream_events) - 1:
        message = stream_events[end_index].get("message", "")
        if message.startswith(REPORT_REQUEST_ID_PREFIX) or message.startswith(END_REQUEST_ID_PREFIX):
            break
        end_index += 1

    if end_index < len(stream_events) - 1:
        next_message = stream_events[end_index + 1].get("message", "")
        if next_message.startswith(REPORT_REQUEST_ID_PREFIX):
            end_index += 1

    return stream_events[start_index : end_index + 1]

def build_execution_log(log_group, log_stream, grouped_events):
    try:
        min_timestamp = min(event["timestamp"] for event in grouped_events)
        max_timestamp = max(event["timestamp"] for event in grouped_events)
        stream_events = fetch_log_stream_events(
            log_group, log_stream, min_timestamp, max_timestamp
        )
        matched_signatures = {
            (event.get("timestamp"), event.get("message", "").strip())
            for event in grouped_events
        }
        invocation_events = find_invocation_window(stream_events, matched_signatures)
        lines = [event.get("message", "").rstrip("\n") for event in invocation_events]
        return "\n".join(line for line in lines if line).strip()[:65000]
    except Exception as exc:
        fallback = "\n".join(event.get("message", "").strip() for event in grouped_events)
        return f"[fallback] failed to fetch full invocation logs: {exc}\n{fallback}"[:65000]

def canonical_issue_message(execution_log, grouped_events):
    if execution_log:
        for line in execution_log.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(START_REQUEST_ID_PREFIX):
                continue
            if stripped.startswith(END_REQUEST_ID_PREFIX):
                continue
            if stripped.startswith(REPORT_REQUEST_ID_PREFIX):
                continue
            if stripped.startswith("{") and '"stage"' in stripped:
                continue
            return stripped
    for event in grouped_events:
        message = event.get("message", "").strip()
        if message:
            return message
    return "Unknown issue"

def extract_request_id(execution_log):
    for line in execution_log.splitlines():
        if line.startswith(START_REQUEST_ID_PREFIX):
            parts = line.split()
            if len(parts) >= 3:
                return parts[2]
        if line.startswith(REPORT_REQUEST_ID_PREFIX):
            parts = line.split()
            if len(parts) >= 3:
                return parts[2]
    return "no-request-id"

def classify_issue(execution_log, grouped_events):
    combined = execution_log.lower()
    if "traceback" in combined:
        return "python_traceback"
    if "runtimeerror" in combined:
        return "runtime_error"
    if "valueerror" in combined:
        return "value_error"
    if "zerodivisionerror" in combined:
        return "zero_division"
    if "keyerror" in combined:
        return "key_error"
    return extract_issue_type(canonical_issue_message(execution_log, grouped_events))

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

def upsert_issue(cursor, issue):
    select_sql = """
        SELECT id, frequency, first_seen, last_seen
        FROM service_exception_log
        WHERE fingerprint = %s
        LIMIT 1
    """
    update_sql = """
        UPDATE service_exception_log
        SET frequency = %s,
            last_seen = %s,
            description = %s,
            stack_trace = %s,
            entire_execution_logs = %s,
            request_id = %s,
            issue_type = %s,
            service_name = %s,
            source = %s
        WHERE id = %s
    """
    insert_sql = """
        INSERT INTO service_exception_log (
            fingerprint,
            service_name,
            issue_type,
            source,
            description,
            stack_trace,
            entire_execution_logs,
            request_id,
            frequency,
            first_seen,
            last_seen,
            status,
            assigned_to,
            resolution_pr,
            resolution_jira,
            created_at,
            resolved_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    cursor.execute(select_sql, (issue["fingerprint"],))
    existing = cursor.fetchone()
    if existing:
        row_id, current_frequency, _, _ = existing
        cursor.execute(
            update_sql,
            (
                current_frequency + issue["frequency"],
                issue["last_seen"],
                issue["description"],
                issue["stack_trace"],
                issue["entire_execution_logs"],
                issue["request_id"],
                issue["issue_type"],
                issue["service_name"],
                issue["source"],
                row_id,
            ),
        )
        return "updated"

    cursor.execute(
        insert_sql,
        (
            issue["fingerprint"],
            issue["service_name"],
            issue["issue_type"],
            issue["source"],
            issue["description"],
            issue["stack_trace"],
            issue["entire_execution_logs"],
            issue["request_id"],
            issue["frequency"],
            issue["first_seen"],
            issue["last_seen"],
            issue["status"],
            None,
            None,
            None,
            issue["created_at"],
            None,
        ),
    )
    return "inserted"

# --- Helper functions to simplify build_issues --

def _event_bounds(log_events):
    """Return (first_event, last_event) based on timestamps."""
    first = min(log_events, key=lambda i: i["timestamp"])
    last = max(log_events, key=lambda i: i["timestamp"])
    return first, last

def _merged_messages(log_events):
    """Concatenate all log messages, separated by double newlines."""
    return "\n\n".join(event["message"].strip() for event in log_events if event.get("message"))

def _build_issue_dict(
    fingerprint,
    service_name,
    issue_type,
    canonical_message,
    merged_messages,
    execution_log,
    request_id,
    first_seen,
    last_seen,
    created_at,
):
    return {
        "fingerprint": fingerprint,
        "service_name": service_name,
        "issue_type": issue_type,
        "source": "cloudwatch",
        "description": summarize_message(canonical_message),
        "stack_trace": merged_messages[:65000],
        "entire_execution_logs": execution_log or merged_messages[:65000],
        "request_id": request_id,
        "frequency": 1,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "status": "open",
        "created_at": created_at,
    }

def build_issues(payload):
    log_group = payload.get("logGroup")
    log_stream = payload.get("logStream")
    service_name = extract_service_name(log_group)
    log_events = payload.get("logEvents", [])
    if not log_events:
        return []

    first_event, last_event = _event_bounds(log_events)
    merged_messages = _merged_messages(log_events)
    execution_log = build_execution_log(log_group, log_stream, log_events)
    canonical_message = canonical_issue_message(execution_log, log_events)
    issue_type = classify_issue(execution_log, log_events)
    request_id = extract_request_id(execution_log)
    fingerprint = build_fingerprint(service_name, issue_type, canonical_message)

    issue = _build_issue_dict(
        fingerprint,
        service_name,
        issue_type,
        canonical_message,
        merged_messages,
        execution_log,
        request_id,
        utc_datetime_from_ms(first_event["timestamp"]),
        utc_datetime_from_ms(last_event["timestamp"]),
        utc_datetime_from_ms(last_event["timestamp"]),
    )
    return [issue]

def lambda_handler(event, context):
    payload = decode_logs_event(event)
    print(json.dumps(payload))

    if payload.get("messageType") == "CONTROL_MESSAGE":
        return {"statusCode": 200, "body": json.dumps({"message": "control message"})}

    issues = build_issues(payload)
    if not issues:
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "no matching log events to persist"}),
        }

    inserted = 0
    updated = 0
    connection = connect_db()
    try:
        with connection.cursor() as cursor:
            for issue in issues:
                result = upsert_issue(cursor, issue)
                if result == "inserted":
                    inserted += 1
                else:
                    updated += 1
    finally:
        connection.close()

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "messageType": payload.get("messageType"),
                "logGroup": payload.get("logGroup"),
                "logEventCount": len(payload.get("logEvents", [])),
                "issueCount": len(issues),
                "inserted": inserted,
                "updated": updated,
            }
        ),
    }
