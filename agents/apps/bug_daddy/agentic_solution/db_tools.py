from __future__ import annotations

import hashlib
import os
from typing import Any

import pymysql
import pymysql.cursors
from strands import tool


def _db_connect() -> pymysql.Connection:
    return pymysql.connect(
        host=os.getenv("DB_HOST", "database-1.ctkcsksi0yjl.ap-south-1.rds.amazonaws.com"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "bug_daddy"),
        password=os.getenv("DB_PASSWORD", "bug_daddy"),
        database=os.getenv("DB_NAME", "bug_daddy"),
        autocommit=True,
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _fingerprint(service_name: str, issue_type: str, description: str) -> str:
    raw = f"{service_name}|{issue_type}|{description[:200]}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


@tool
def insert_exception_log(
    service_name: str,
    issue_type: str,
    description: str,
    source: str = "slack",
    stack_trace: str | None = None,
    assigned_to: str | None = None,
    resolution_jira: str | None = None,
) -> dict[str, Any]:
    """
    Insert a new entry into bug_daddy.service_exception_log.

    Returns the inserted row id, fingerprint, and Jira/issue id if available.
    Use source='slack' for issues reported via Slack.
    issue_type should be one of: bug, incident, tech_debt, cve, other.
    """
    fp = _fingerprint(service_name, issue_type, description)
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bug_daddy.service_exception_log
                  (fingerprint, service_name, issue_type, source, description,
                   stack_trace, status, assigned_to, resolution_jira)
                VALUES (%s, %s, %s, %s, %s, %s, 'open', %s, %s)
                """,
                (fp, service_name, issue_type, source, description,
                 stack_trace, assigned_to, resolution_jira),
            )
            row_id = cur.lastrowid
    finally:
        conn.close()

    return {
        "id": row_id,
        "fingerprint": fp,
        "resolution_jira": resolution_jira,
        "service_name": service_name,
        "issue_type": issue_type,
        "status": "open",
    }


@tool
def lookup_exception_log(fingerprint: str) -> dict[str, Any] | None:
    """
    Look up an existing entry in service_exception_log by fingerprint.
    Returns the row dict or None if not found.
    """
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM bug_daddy.service_exception_log WHERE fingerprint = %s ORDER BY id DESC LIMIT 1",
                (fingerprint,),
            )
            return cur.fetchone()
    finally:
        conn.close()
