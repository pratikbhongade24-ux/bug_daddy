import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import boto3
import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, EmailStr, Field


DB_HOST = os.getenv("DB_HOST", "database-1.ctkcsksi0yjl.ap-south-1.rds.amazonaws.com")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "bug_daddy")
DB_USER = os.getenv("DB_USER", "bug_daddy")
DB_PASSWORD = os.getenv("DB_PASSWORD", "bug_daddy")
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "bug-daddy-dev-secret")
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
PASSWORD_RESET_HOURS = int(os.getenv("PASSWORD_RESET_HOURS", "1"))
EMAIL_VERIFY_HOURS = int(os.getenv("EMAIL_VERIFY_HOURS", "24"))
PBKDF2_ITERATIONS = int(os.getenv("PBKDF2_ITERATIONS", "120000"))
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AGENTCORE_RUNTIME_ARN = os.getenv(
    "AGENTCORE_RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:ap-south-1:105028893980:runtime/bug_daddy-IV6831D6Rs",
)
AGENT_EXECUTION_LOG_SECRET = os.getenv("AGENT_EXECUTION_LOG_SECRET")
AGENT_EXECUTION_CALLBACK_URL = os.getenv("AGENT_EXECUTION_CALLBACK_URL")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://bugdaddy.atlassian.net").rstrip("/")
SONAR_LAMBDA_NAME = os.getenv("SONAR_LAMBDA_NAME", "bugdaddy-sonar-scan-trigger")
SONAR_REPORT_BUCKET = os.getenv("SONAR_REPORT_BUCKET", "bugdaddy-sonar-reports")
SONAR_REPORT_PREFIX = os.getenv("SONAR_REPORT_PREFIX", "")
SONAR_PRESIGN_EXPIRES_SECONDS = int(os.getenv("SONAR_PRESIGN_EXPIRES_SECONDS", "3600"))


app = FastAPI(title="Bug Daddy API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=255)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    role_name: Literal["admin", "user"] = "user"
    status: Literal["active", "inactive", "locked"] = "active"


class UserUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=100)
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=255)
    role_name: Literal["admin", "user"] | None = None
    status: Literal["active", "inactive", "locked"] | None = None


class PasswordUpdateRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=255)


class RolePermissionsUpdateRequest(BaseModel):
    permission_keys: list[str]


class IssueUpdateRequest(BaseModel):
    status: Literal["open", "in_progress", "resolved", "no_action"] | None = None
    assigned_to: str | None = Field(default=None, max_length=255)
    resolution_pr: str | None = Field(default=None, max_length=255)
    resolution_jira: str | None = Field(default=None, max_length=255)


class IssueAssignRequest(BaseModel):
    assigned_to: str = Field(min_length=1, max_length=255)


class JiraResolutionMapRequest(BaseModel):
    resolution_jira: str | None = Field(default=None, max_length=255)
    jira_key: str | None = Field(default=None, max_length=100)
    jira_url: str | None = Field(default=None, max_length=255)


class PullRequestResolutionMapRequest(BaseModel):
    resolution_pr: str | None = Field(default=None, max_length=255)
    pull_request_url: str | None = Field(default=None, max_length=255)
    pr_url: str | None = Field(default=None, max_length=255)


class AgentInvokeRequest(BaseModel):
    session_id: str | None = None
    target: Literal["classifier", "incident_daddy", "bug_daddy", "reviewer_daddy", "sme_agent"] | None = None
    prompt: str | None = None
    question: str | None = None
    source: str = "platform"
    service_name: str | None = None
    issue_id: int | None = None
    logs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    incident_summary: str | None = None
    repository: str | None = None


class AgentExecutionCreateRequest(BaseModel):
    issue_id: int | None = None
    target: Literal["classifier", "incident_daddy", "bug_daddy", "reviewer_daddy", "sme_agent"] = "incident_daddy"
    workflow_key: str | None = None
    workflow_version: str = "v1"
    input_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SonarInvokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class AgentExecutionEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=50)
    node_id: str | None = Field(default=None, max_length=100)
    node_name: str | None = Field(default=None, max_length=255)
    agent_name: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=30)
    level: str | None = Field(default="info", max_length=20)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    reasoning_summary: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    result: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    tool_name: str | None = Field(default=None, max_length=100)
    tool_input: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    tool_output: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = None
    duration_ms: int | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    full_name: str | None
    role: str
    status: str
    is_email_verified: bool
    last_login_at: str | None
    created_at: str
    updated_at: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dt_to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()
    return str(value)


def json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def get_db():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10,
    )


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations, salt, digest = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    test_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(test_digest, digest)


def encode_token(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body_b64 = base64.urlsafe_b64encode(body).rstrip(b"=")
    sig = hmac.new(TOKEN_SECRET.encode("utf-8"), body_b64, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
    return f"{body_b64.decode()}.{sig_b64.decode()}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        body_b64, sig_b64 = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    expected = base64.urlsafe_b64encode(
        hmac.new(TOKEN_SECRET.encode("utf-8"), body_b64.encode("utf-8"), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    if not hmac.compare_digest(expected, sig_b64):
        raise HTTPException(status_code=401, detail="Invalid token signature")
    padded = body_b64 + "=" * (-len(body_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))
    if payload["exp"] < int(utc_now().timestamp()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def create_access_token(user: dict[str, Any]) -> str:
    now = utc_now()
    payload = {
        "sub": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "permissions": user["permissions"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
    }
    return encode_token(payload)


def create_refresh_session(conn, user_id: str) -> str:
    refresh_token = secrets.token_urlsafe(48)
    token_hash = hash_secret(refresh_token)
    expires_at = utc_now() + timedelta(days=REFRESH_TOKEN_DAYS)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_sessions (id, user_id, refresh_token_hash, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), user_id, token_hash, expires_at.strftime("%Y-%m-%d %H:%M:%S")),
        )
    return refresh_token


def fetch_user_by_identifier(conn, identifier: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              u.id, u.username, u.email, u.password_hash, u.full_name, u.status, u.is_email_verified,
              u.last_login_at, u.created_at, u.updated_at, r.name AS role
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.username = %s OR u.email = %s
            LIMIT 1
            """,
            (identifier, identifier),
        )
        return cur.fetchone()


def fetch_user_by_id(conn, user_id: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              u.id, u.username, u.email, u.full_name, u.status, u.is_email_verified,
              u.last_login_at, u.created_at, u.updated_at, r.name AS role
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            """
            SELECT p.permission_key
            FROM permissions p
            JOIN role_permissions rp ON rp.permission_id = p.id
            JOIN roles r ON r.id = rp.role_id
            JOIN users u ON u.role_id = r.id
            WHERE u.id = %s
            ORDER BY p.permission_key
            """,
            (user_id,),
        )
        row["permissions"] = [item["permission_key"] for item in cur.fetchall()]
        return row


def to_user_response(user: dict[str, Any]) -> UserResponse:
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        full_name=user.get("full_name"),
        role=user["role"],
        status=user["status"],
        is_email_verified=bool(user["is_email_verified"]),
        last_login_at=dt_to_str(user.get("last_login_at")),
        created_at=dt_to_str(user["created_at"]) or "",
        updated_at=dt_to_str(user["updated_at"]) or "",
    )


def require_auth(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    conn = get_db()
    try:
        user = fetch_user_by_id(conn, payload["sub"])
        if not user or user["status"] != "active":
            raise HTTPException(status_code=401, detail="User not active")
        return user
    finally:
        conn.close()


def require_permission(permission_key: str):
    def checker(user: dict[str, Any] = Depends(require_auth)):
        if permission_key not in user["permissions"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def write_audit_log(conn, user_id: str | None, action: str, entity_type: str | None = None, entity_id: str | None = None, metadata: dict[str, Any] | None = None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_logs (user_id, action, entity_type, entity_id, metadata)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, action, entity_type, entity_id, json.dumps(metadata) if metadata else None),
        )


def get_role_id(conn, role_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM roles WHERE name = %s LIMIT 1", (role_name,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail=f"Role not found: {role_name}")
        return int(row["id"])


def issue_criticality(frequency: int) -> str:
    if frequency > 600:
        return "Critical"
    if frequency > 200:
        return "High"
    if frequency > 50:
        return "Medium"
    return "Low"


def issue_tab(status: str) -> str:
    return {
        "open": "backlog",
        "in_progress": "wip",
        "in_review": "review",
        "resolved": "resolved",
        "no_action": "backlog",
    }.get(status, "backlog")


def route_issue_agent(issue: dict[str, Any]) -> str:
    frequency = int(issue.get("frequency") or 0)
    text = " ".join(
        str(issue.get(key) or "")
        for key in ("issue_type", "source", "description", "stack_trace", "criticality")
    ).lower()
    incident_markers = (
        "incident",
        "outage",
        "sev1",
        "sev2",
        "p0",
        "p1",
        "critical",
        "all customers",
        "partial outage",
        "degraded",
        "service down",
    )
    if frequency > 600 or any(marker in text for marker in incident_markers):
        return "incident_daddy"
    return "bug_daddy"


def default_workflow_graph(workflow_key: str) -> dict[str, Any]:
    common_triggers = [
        {"id": "cw", "label": "CloudWatch", "type": "trigger", "x": 100, "y": 20},
        {"id": "sq", "label": "SonarQube", "type": "trigger", "x": 250, "y": 20},
        {"id": "cve", "label": "CVE Monitor", "type": "trigger", "x": 400, "y": 20},
        {"id": "jira", "label": "Jira Backlogs", "type": "trigger", "x": 550, "y": 20},
        {"id": "slk", "label": "Slack Incident", "type": "trigger", "x": 700, "y": 20},
        {"id": "db", "label": "Issues Tracker", "type": "store", "x": 380, "y": 120},
        {"id": "esc", "label": "Escalation Agent", "type": "agent", "x": 380, "y": 220},
        {"id": "jag", "label": "Jira Agent", "type": "tool", "x": 580, "y": 220},
        {"id": "sme", "label": "SME", "type": "agent", "x": 310, "y": 390},
    ]
    incident_nodes = [
        {"id": "inc", "label": "Incident Daddy", "type": "agent", "x": 110, "y": 385},
    ]
    bug_nodes = [
        {"id": "bug", "label": "Bug Daddy", "type": "agent", "x": 700, "y": 310},
        {"id": "strat", "label": "Planner", "type": "agent", "x": 560, "y": 455},
        {"id": "crit_strat", "label": "Planner Critique", "type": "agent", "x": 560, "y": 595},
        {"id": "ctx", "label": "Context Analyser", "type": "agent", "x": 760, "y": 455},
        {"id": "crit_ctx", "label": "Context Critique", "type": "agent", "x": 760, "y": 595},
        {"id": "code", "label": "Coder", "type": "agent", "x": 960, "y": 455},
        {"id": "crit_code", "label": "Coder Critique", "type": "agent", "x": 910, "y": 595},
        {"id": "jprf", "label": "GitHub", "type": "tool", "x": 1060, "y": 595},
    ]
    reviewer_nodes = [
        {"id": "rev", "label": "Reviewer Daddy", "type": "agent", "x": 1240, "y": 310},
    ]

    if workflow_key == "reviewer_daddy":
        nodes = [{"id": "sme", "label": "SME", "type": "agent", "x": 400, "y": 260}] + reviewer_nodes
        edges = [
            {"from": "sme", "to": "rev"},
        ]
    elif workflow_key == "sme_agent":
        nodes = [
            {"id": "sme", "label": "SME", "type": "agent", "x": 400, "y": 260},
            {"id": "kb", "label": "Knowledge Base", "type": "store", "x": 400, "y": 360},
            {"id": "refs", "label": "References", "type": "output", "x": 400, "y": 460},
        ]
        edges = [
            {"from": "sme", "to": "kb"},
            {"from": "kb", "to": "refs"},
        ]
    elif workflow_key == "bug_daddy":
        nodes = common_triggers + bug_nodes + reviewer_nodes
        edges = [
            {"from": "cw", "to": "db"},
            {"from": "sq", "to": "db"},
            {"from": "cve", "to": "db"},
            {"from": "jira", "to": "db"},
            {"from": "slk", "to": "db"},
            {"from": "db", "to": "esc"},
            {"from": "esc", "to": "jag"},
            {"from": "esc", "to": "bug"},
            {"from": "bug", "to": "sme"},
            {"from": "bug", "to": "strat"},
            {"from": "strat", "to": "crit_strat"},
            {"from": "crit_strat", "to": "strat"},
            {"from": "bug", "to": "ctx"},
            {"from": "ctx", "to": "crit_ctx"},
            {"from": "crit_ctx", "to": "ctx"},
            {"from": "bug", "to": "code"},
            {"from": "code", "to": "crit_code"},
            {"from": "crit_code", "to": "code"},
            {"from": "code", "to": "jprf"},
            {"from": "bug", "to": "rev"},
        ]
    else:
        nodes = common_triggers + incident_nodes + bug_nodes + reviewer_nodes
        edges = [
            {"from": "cw", "to": "db"},
            {"from": "sq", "to": "db"},
            {"from": "cve", "to": "db"},
            {"from": "jira", "to": "db"},
            {"from": "slk", "to": "db"},
            {"from": "db", "to": "esc"},
            {"from": "esc", "to": "jag"},
            {"from": "esc", "to": "inc"},
            {"from": "esc", "to": "bug"},
            {"from": "bug", "to": "sme"},
            {"from": "bug", "to": "strat"},
            {"from": "strat", "to": "crit_strat"},
            {"from": "crit_strat", "to": "strat"},
            {"from": "bug", "to": "ctx"},
            {"from": "ctx", "to": "crit_ctx"},
            {"from": "crit_ctx", "to": "ctx"},
            {"from": "bug", "to": "code"},
            {"from": "code", "to": "crit_code"},
            {"from": "crit_code", "to": "code"},
            {"from": "code", "to": "jprf"},
            {"from": "bug", "to": "rev"},
        ]
    return {"nodes": nodes, "edges": edges}


def workflow_key_for_target(target: str | None) -> str:
    normalized = (target or "incident_daddy").strip().lower().replace("-", "_")
    if normalized == "classifier":
        return "bug_daddy"
    if normalized in {"bug", "bug_daddy"}:
        return "bug_daddy"
    if normalized in {"reviewer", "reviewer_daddy"}:
        return "reviewer_daddy"
    if normalized in {"sme", "sme_agent"}:
        return "sme_agent"
    return "incident_daddy"


def map_issue(row: dict[str, Any]) -> dict[str, Any]:
    frequency = int(row.get("frequency") or 0)
    latest_session_id = row.get("latest_execution_session_id")
    criticality = issue_criticality(frequency)
    agent_target = route_issue_agent(
        {
            **row,
            "frequency": frequency,
            "criticality": criticality,
        }
    )
    return {
        "id": int(row["id"]),
        "jiraId": f"GH-{row['id']}",
        "fingerprint": row["fingerprint"],
        "service": row["service_name"],
        "shortSvc": row["service_name"].replace("grabhack-", ""),
        "type": row["issue_type"],
        "source": row["source"],
        "description": row.get("description"),
        "err": row.get("description") or f"{row['issue_type']} in {row['service_name']}",
        "stack_trace": row.get("stack_trace"),
        "frequency": frequency,
        "freq": frequency,
        "criticality": criticality,
        "agent_target": agent_target,
        "workflow_key": workflow_key_for_target(agent_target),
        "status": row["status"],
        "tab": issue_tab(row["status"]),
        "owner": row.get("assigned_to") or "Unassigned",
        "resolution_pr": row.get("resolution_pr"),
        "resolution_jira": row.get("resolution_jira"),
        "request_id": row.get("request_id"),
        "entire_execution_logs": row.get("entire_execution_logs"),
        "first_seen": dt_to_str(row.get("first_seen")),
        "last_seen": dt_to_str(row.get("last_seen")),
        "created_at": dt_to_str(row.get("created_at")),
        "resolved_at": dt_to_str(row.get("resolved_at")),
        "latest_execution_session_id": latest_session_id,
        "execution_session_id": latest_session_id,
    }


def fetch_issue_by_id(conn, issue_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sel.id, fingerprint, service_name, issue_type, source, description, stack_trace,
                   frequency, first_seen, last_seen, status, assigned_to, resolution_pr,
                   resolution_jira, created_at, resolved_at, entire_execution_logs, request_id,
                   (
                     SELECT aes.session_id
                     FROM agent_execution_sessions aes
                     WHERE aes.issue_id = sel.id
                     ORDER BY aes.created_at DESC
                     LIMIT 1
                   ) AS latest_execution_session_id
            FROM service_exception_log sel
            WHERE sel.id = %s
            LIMIT 1
            """,
            (issue_id,),
        )
        row = cur.fetchone()
    return map_issue(row) if row else None


def invoke_agentcore(payload: dict[str, Any]) -> dict[str, Any]:
    client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
        runtimeSessionId=str(uuid.uuid4()),
        payload=json.dumps(payload).encode("utf-8"),
    )
    body = response.get("payload")
    if body is None:
        return {"message": "No payload returned from AgentCore"}
    if hasattr(body, "read"):
        raw = body.read()
    else:
        raw = body
    if isinstance(raw, (bytes, bytearray)):
        raw_text = raw.decode("utf-8")
    else:
        raw_text = str(raw)
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"raw": raw_text}


def ensure_execution_schema(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_workflow_definitions (
              id BIGINT AUTO_INCREMENT PRIMARY KEY,
              workflow_key VARCHAR(100) NOT NULL,
              workflow_version VARCHAR(50) NOT NULL,
              name VARCHAR(255) NOT NULL,
              description TEXT NULL,
              graph_json JSON NOT NULL,
              is_active BOOLEAN NOT NULL DEFAULT TRUE,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE KEY uq_workflow_version (workflow_key, workflow_version)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_execution_sessions (
              id BIGINT AUTO_INCREMENT PRIMARY KEY,
              session_id CHAR(36) NOT NULL UNIQUE,
              issue_id BIGINT NULL,
              workflow_key VARCHAR(100) NOT NULL,
              workflow_version VARCHAR(50) NOT NULL,
              status VARCHAR(30) NOT NULL,
              next_sequence_no BIGINT NOT NULL DEFAULT 0,
              started_by VARCHAR(255) NULL,
              started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              ended_at DATETIME NULL,
              agent_target VARCHAR(100) NULL,
              input_payload JSON NULL,
              summary TEXT NULL,
              error_message TEXT NULL,
              metadata JSON NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              INDEX idx_execution_sessions_issue (issue_id),
              INDEX idx_execution_sessions_status (status),
              INDEX idx_execution_sessions_created (created_at)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_execution_logs (
              id BIGINT AUTO_INCREMENT PRIMARY KEY,
              session_id CHAR(36) NOT NULL,
              sequence_no BIGINT NOT NULL,
              event_type VARCHAR(50) NOT NULL,
              node_id VARCHAR(100) NULL,
              node_name VARCHAR(255) NULL,
              agent_name VARCHAR(100) NULL,
              status VARCHAR(30) NULL,
              level VARCHAR(20) NULL,
              title VARCHAR(255) NULL,
              description TEXT NULL,
              reasoning_summary TEXT NULL,
              input_summary TEXT NULL,
              output_summary TEXT NULL,
              result JSON NULL,
              tool_name VARCHAR(100) NULL,
              tool_input JSON NULL,
              tool_output JSON NULL,
              error_code VARCHAR(100) NULL,
              error_message TEXT NULL,
              duration_ms INT NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE KEY uq_session_sequence (session_id, sequence_no),
              INDEX idx_execution_logs_session_id (session_id, id),
              INDEX idx_execution_logs_session_node (session_id, node_id),
              INDEX idx_execution_logs_session_created (session_id, created_at),
              CONSTRAINT fk_execution_logs_session
                FOREIGN KEY (session_id) REFERENCES agent_execution_sessions(session_id)
                ON DELETE CASCADE
            )
            """
        )
        cur.execute("SHOW COLUMNS FROM agent_execution_sessions LIKE 'next_sequence_no'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE agent_execution_sessions ADD COLUMN next_sequence_no BIGINT NOT NULL DEFAULT 0 AFTER status"
            )
    seed_workflow_definitions(conn)


def seed_workflow_definitions(conn):
    workflows = {
        "incident_daddy": "Incident Daddy Flow",
        "bug_daddy": "Bug Daddy Flow",
        "reviewer_daddy": "Reviewer Daddy Flow",
        "sme_agent": "SME Agent Flow",
    }
    with conn.cursor() as cur:
        for key, name in workflows.items():
            graph = default_workflow_graph(key)
            cur.execute(
                """
                INSERT INTO agent_workflow_definitions
                  (workflow_key, workflow_version, name, description, graph_json, is_active)
                VALUES (%s, 'v1', %s, %s, %s, TRUE)
                ON DUPLICATE KEY UPDATE
                  name = VALUES(name),
                  description = VALUES(description),
                  graph_json = VALUES(graph_json),
                  is_active = VALUES(is_active)
                """,
                (
                    key,
                    name,
                    f"Default {name} graph used by the platform execution view.",
                    json.dumps(graph),
                ),
            )


def create_execution_session(
    conn,
    *,
    issue_id: int | None,
    workflow_key: str,
    workflow_version: str,
    agent_target: str | None,
    started_by: str | None,
    input_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    status_value: str = "queued",
) -> str:
    session_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_execution_sessions
              (session_id, issue_id, workflow_key, workflow_version, status, started_by,
               agent_target, input_payload, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                issue_id,
                workflow_key,
                workflow_version,
                status_value,
                started_by,
                agent_target,
                json_or_none(input_payload),
                json_or_none(metadata),
            ),
        )
    return session_id


def append_execution_event(conn, session_id: str, payload: AgentExecutionEventCreate | dict[str, Any]) -> dict[str, Any]:
    event = payload if isinstance(payload, AgentExecutionEventCreate) else AgentExecutionEventCreate.model_validate(payload)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE agent_execution_sessions
            SET next_sequence_no = LAST_INSERT_ID(next_sequence_no + 1), updated_at = %s
            WHERE session_id = %s
            """,
            (utc_now().strftime("%Y-%m-%d %H:%M:%S"), session_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Execution session not found")
        cur.execute("SELECT LAST_INSERT_ID() AS sequence_no")
        sequence_no = int(cur.fetchone()["sequence_no"])
        cur.execute(
            """
            INSERT INTO agent_execution_logs (
              session_id, sequence_no, event_type, node_id, node_name, agent_name, status, level,
              title, description, reasoning_summary, input_summary, output_summary, result,
              tool_name, tool_input, tool_output, error_code, error_message, duration_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                session_id,
                sequence_no,
                event.event_type,
                event.node_id,
                event.node_name,
                event.agent_name,
                event.status,
                event.level,
                event.title,
                event.description,
                event.reasoning_summary,
                event.input_summary,
                event.output_summary,
                json_or_none(event.result),
                event.tool_name,
                json_or_none(event.tool_input),
                json_or_none(event.tool_output),
                event.error_code,
                event.error_message,
                event.duration_ms,
            ),
        )
        event_id = cur.lastrowid
    return {
        "id": event_id,
        "session_id": session_id,
        "sequence_no": sequence_no,
        **event.model_dump(),
    }


def update_execution_session(
    conn,
    session_id: str,
    *,
    status_value: str,
    summary: str | None = None,
    error_message: str | None = None,
    ended: bool = False,
):
    fields = ["status = %s", "updated_at = %s"]
    values: list[Any] = [status_value, utc_now().strftime("%Y-%m-%d %H:%M:%S")]
    if summary is not None:
        fields.append("summary = %s")
        values.append(summary)
    if error_message is not None:
        fields.append("error_message = %s")
        values.append(error_message)
    if ended:
        fields.append("ended_at = %s")
        values.append(utc_now().strftime("%Y-%m-%d %H:%M:%S"))
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE agent_execution_sessions SET {', '.join(fields)} WHERE session_id = %s",
            (*values, session_id),
        )


def map_execution_session(row: dict[str, Any]) -> dict[str, Any]:
    mapped = dict(row)
    for key in ("started_at", "ended_at", "created_at", "updated_at"):
        mapped[key] = dt_to_str(mapped.get(key))
    for key in ("input_payload", "metadata"):
        if isinstance(mapped.get(key), str):
            try:
                mapped[key] = json.loads(mapped[key])
            except json.JSONDecodeError:
                pass
    return mapped


def map_execution_event(row: dict[str, Any]) -> dict[str, Any]:
    mapped = dict(row)
    mapped["created_at"] = dt_to_str(mapped.get("created_at"))
    for key in ("result", "tool_input", "tool_output"):
        if isinstance(mapped.get(key), str):
            try:
                mapped[key] = json.loads(mapped[key])
            except json.JSONDecodeError:
                pass
    return mapped


def sonar_report_key(report_date: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        raise HTTPException(status_code=400, detail="report_date must use YYYY-MM-DD")
    prefix = SONAR_REPORT_PREFIX.strip("/")
    key = f"{report_date}/report.json"
    return f"{prefix}/{key}" if prefix else key


def list_sonar_reports(limit: int = 10) -> list[dict[str, Any]]:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    prefix = SONAR_REPORT_PREFIX.strip("/")
    response = s3.list_objects_v2(
        Bucket=SONAR_REPORT_BUCKET,
        Prefix=f"{prefix}/" if prefix else "",
        MaxKeys=1000,
    )
    reports: list[dict[str, Any]] = []
    for item in response.get("Contents", []):
        key = item.get("Key") or ""
        if not key.endswith("/report.json"):
            continue
        report_date = key.split("/")[-2] if "/" in key else ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
            continue
        reports.append(
            {
                "date": report_date,
                "key": key,
                "size": int(item.get("Size") or 0),
                "last_modified": dt_to_str(item.get("LastModified")),
            }
        )
    reports.sort(key=lambda item: item["date"], reverse=True)
    return reports[:limit]


def verify_execution_log_secret(x_agent_execution_secret: str | None = Header(default=None)):
    if AGENT_EXECUTION_LOG_SECRET and x_agent_execution_secret != AGENT_EXECUTION_LOG_SECRET:
        raise HTTPException(status_code=401, detail="Invalid execution log secret")


def ensure_schema_and_seed_data():
    conn = get_db()
    try:
        ensure_execution_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM users LIKE 'username'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE users ADD COLUMN username VARCHAR(100) NULL AFTER id")
            cur.execute("SHOW INDEX FROM users WHERE Key_name = 'uq_users_username'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE users ADD UNIQUE KEY uq_users_username (username)")
            cur.execute(
                """
                UPDATE users
                SET username = email
                WHERE (username IS NULL OR username = '') AND email IS NOT NULL
                """
            )
            admin_role_id = get_role_id(conn, "admin")
            cur.execute("SELECT id FROM users WHERE username = %s LIMIT 1", ("bug_daddy",))
            admin_user = cur.fetchone()
            password_hash = hash_password("bug_daddy")
            if admin_user:
                cur.execute(
                    """
                    UPDATE users
                    SET email = %s, password_hash = %s, role_id = %s, status = 'active', is_email_verified = TRUE
                    WHERE id = %s
                    """,
                    ("bug_daddy@bugdaddy.local", password_hash, admin_role_id, admin_user["id"]),
                )
                admin_id = admin_user["id"]
            else:
                admin_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO users (id, username, email, password_hash, full_name, role_id, status, is_email_verified)
                    VALUES (%s, %s, %s, %s, %s, %s, 'active', TRUE)
                    """,
                    (admin_id, "bug_daddy", "bug_daddy@bugdaddy.local", password_hash, "Bug Daddy Admin", admin_role_id),
                )
            write_audit_log(conn, admin_id, "seed.default_admin", "users", admin_id, {"username": "bug_daddy"})
    finally:
        conn.close()


@app.on_event("startup")
def startup_event():
    ensure_schema_and_seed_data()


@app.get("/")
def read_root():
    return {"message": "Welcome to the Bug Daddy API!"}


@app.get("/health")
def health_check():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
        return {"status": "healthy", "database": "connected"}
    finally:
        conn.close()


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    conn = get_db()
    try:
        user = fetch_user_by_identifier(conn, payload.identifier)
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if user["status"] != "active":
            raise HTTPException(status_code=403, detail=f"User is {user['status']}")
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login_at = %s WHERE id = %s",
                (utc_now().strftime("%Y-%m-%d %H:%M:%S"), user["id"]),
            )
        full_user = fetch_user_by_id(conn, user["id"])
        refresh_token = create_refresh_session(conn, user["id"])
        access_token = create_access_token(full_user)
        write_audit_log(conn, user["id"], "auth.login", "users", user["id"], {"identifier": payload.identifier})
        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=to_user_response(full_user),
        )
    finally:
        conn.close()


@app.post("/auth/refresh", response_model=AuthResponse)
def refresh_token(payload: TokenRefreshRequest):
    conn = get_db()
    try:
        token_hash = hash_secret(payload.refresh_token)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, expires_at, revoked_at
                FROM user_sessions
                WHERE refresh_token_hash = %s
                LIMIT 1
                """,
                (token_hash,),
            )
            session = cur.fetchone()
        if not session or session["revoked_at"] is not None or session["expires_at"] < utc_now():
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        user = fetch_user_by_id(conn, session["user_id"])
        if not user or user["status"] != "active":
            raise HTTPException(status_code=401, detail="User not active")
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE user_sessions SET revoked_at = %s WHERE id = %s",
                (utc_now().strftime("%Y-%m-%d %H:%M:%S"), session["id"]),
            )
        new_refresh_token = create_refresh_session(conn, user["id"])
        access_token = create_access_token(user)
        write_audit_log(conn, user["id"], "auth.refresh", "user_sessions", session["id"])
        return AuthResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            user=to_user_response(user),
        )
    finally:
        conn.close()


@app.post("/auth/logout")
def logout(payload: TokenRefreshRequest, user: dict[str, Any] = Depends(require_auth)):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_sessions
                SET revoked_at = %s
                WHERE refresh_token_hash = %s AND user_id = %s AND revoked_at IS NULL
                """,
                (
                    utc_now().strftime("%Y-%m-%d %H:%M:%S"),
                    hash_secret(payload.refresh_token),
                    user["id"],
                ),
            )
        write_audit_log(conn, user["id"], "auth.logout", "users", user["id"])
        return {"message": "Logged out"}
    finally:
        conn.close()


@app.get("/auth/me", response_model=UserResponse)
def me(user: dict[str, Any] = Depends(require_auth)):
    return to_user_response(user)


@app.post("/auth/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    conn = get_db()
    try:
        user = fetch_user_by_identifier(conn, payload.identifier)
        if not user:
            return {"message": "If the account exists, a reset token has been created."}
        raw_token = secrets.token_urlsafe(32)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    user["id"],
                    hash_secret(raw_token),
                    (utc_now() + timedelta(hours=PASSWORD_RESET_HOURS)).strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        write_audit_log(conn, user["id"], "auth.forgot_password", "users", user["id"])
        return {"message": "Reset token created", "reset_token": raw_token}
    finally:
        conn.close()


@app.post("/auth/reset-password")
def reset_password(payload: ResetPasswordRequest):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, expires_at, used_at
                FROM password_reset_tokens
                WHERE token_hash = %s
                LIMIT 1
                """,
                (hash_secret(payload.token),),
            )
            token_row = cur.fetchone()
        if not token_row or token_row["used_at"] is not None or token_row["expires_at"] < utc_now():
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (hash_password(payload.new_password), token_row["user_id"]),
            )
            cur.execute(
                "UPDATE password_reset_tokens SET used_at = %s WHERE id = %s",
                (utc_now().strftime("%Y-%m-%d %H:%M:%S"), token_row["id"]),
            )
        write_audit_log(conn, token_row["user_id"], "auth.reset_password", "users", token_row["user_id"])
        return {"message": "Password reset successful"}
    finally:
        conn.close()


@app.get("/roles")
def list_roles(user: dict[str, Any] = Depends(require_permission("roles.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.name, r.description, COUNT(rp.permission_id) AS permission_count
                FROM roles r
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                GROUP BY r.id, r.name, r.description
                ORDER BY r.name
                """
            )
            return {"items": cur.fetchall()}
    finally:
        conn.close()


@app.get("/permissions")
def list_permissions(user: dict[str, Any] = Depends(require_permission("roles.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, permission_key, description FROM permissions ORDER BY permission_key")
            return {"items": cur.fetchall()}
    finally:
        conn.close()


@app.put("/roles/{role_name}/permissions")
def update_role_permissions(role_name: str, payload: RolePermissionsUpdateRequest, actor: dict[str, Any] = Depends(require_permission("roles.update"))):
    conn = get_db()
    try:
        role_id = get_role_id(conn, role_name)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM role_permissions WHERE role_id = %s", (role_id,))
            for key in sorted(set(payload.permission_keys)):
                cur.execute(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT %s, id FROM permissions WHERE permission_key = %s
                    """,
                    (role_id, key),
                )
        write_audit_log(conn, actor["id"], "roles.update_permissions", "roles", str(role_id), {"permission_keys": payload.permission_keys})
        return {"message": "Role permissions updated"}
    finally:
        conn.close()


@app.get("/admin/users")
def admin_list_users(actor: dict[str, Any] = Depends(require_permission("users.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  u.id, u.username, u.email, u.full_name, r.name AS role, u.status,
                  u.is_email_verified, u.last_login_at, u.created_at, u.updated_at
                FROM users u
                JOIN roles r ON r.id = u.role_id
                ORDER BY u.created_at DESC
                """
            )
            items = [to_user_response(row).model_dump() for row in cur.fetchall()]
        return {"items": items}
    finally:
        conn.close()


@app.post("/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def admin_create_user(payload: UserCreateRequest, actor: dict[str, Any] = Depends(require_permission("users.create"))):
    conn = get_db()
    try:
        role_id = get_role_id(conn, payload.role_name)
        user_id = str(uuid.uuid4())
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, username, email, password_hash, full_name, role_id, status, is_email_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                """,
                (user_id, payload.username, str(payload.email), hash_password(payload.password), payload.full_name, role_id, payload.status),
            )
        created = fetch_user_by_id(conn, user_id)
        write_audit_log(conn, actor["id"], "users.create", "users", user_id, {"username": payload.username, "role_name": payload.role_name})
        return to_user_response(created)
    except pymysql.err.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username or email already exists") from exc
    finally:
        conn.close()


@app.get("/admin/users/{user_id}", response_model=UserResponse)
def admin_get_user(user_id: str, actor: dict[str, Any] = Depends(require_permission("users.read"))):
    conn = get_db()
    try:
        user = fetch_user_by_id(conn, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return to_user_response(user)
    finally:
        conn.close()


@app.patch("/admin/users/{user_id}", response_model=UserResponse)
def admin_update_user(user_id: str, payload: UserUpdateRequest, actor: dict[str, Any] = Depends(require_permission("users.update"))):
    conn = get_db()
    try:
        existing = fetch_user_by_id(conn, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        fields = []
        values: list[Any] = []
        if payload.username is not None:
            fields.append("username = %s")
            values.append(payload.username)
        if payload.email is not None:
            fields.append("email = %s")
            values.append(str(payload.email))
        if payload.full_name is not None:
            fields.append("full_name = %s")
            values.append(payload.full_name)
        if payload.status is not None:
            fields.append("status = %s")
            values.append(payload.status)
        if payload.role_name is not None:
            fields.append("role_id = %s")
            values.append(get_role_id(conn, payload.role_name))
        if fields:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", (*values, user_id))
        updated = fetch_user_by_id(conn, user_id)
        write_audit_log(conn, actor["id"], "users.update", "users", user_id, payload.model_dump(exclude_none=True))
        return to_user_response(updated)
    except pymysql.err.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username or email already exists") from exc
    finally:
        conn.close()


@app.patch("/admin/users/{user_id}/password")
def admin_update_user_password(user_id: str, payload: PasswordUpdateRequest, actor: dict[str, Any] = Depends(require_permission("users.update"))):
    conn = get_db()
    try:
        if not fetch_user_by_id(conn, user_id):
            raise HTTPException(status_code=404, detail="User not found")
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(payload.new_password), user_id))
        write_audit_log(conn, actor["id"], "users.update_password", "users", user_id)
        return {"message": "Password updated"}
    finally:
        conn.close()


@app.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: str, actor: dict[str, Any] = Depends(require_permission("users.delete"))):
    conn = get_db()
    try:
        if not fetch_user_by_id(conn, user_id):
            raise HTTPException(status_code=404, detail="User not found")
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET status = 'inactive' WHERE id = %s", (user_id,))
        write_audit_log(conn, actor["id"], "users.delete", "users", user_id)
        return {"message": "User deactivated"}
    finally:
        conn.close()


@app.get("/admin/audit-logs")
def admin_list_audit_logs(actor: dict[str, Any] = Depends(require_permission("audit.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, action, entity_type, entity_id, metadata, ip_address, created_at
                FROM audit_logs
                ORDER BY created_at DESC
                LIMIT 200
                """
            )
            rows = cur.fetchall()
        for row in rows:
            row["created_at"] = dt_to_str(row["created_at"])
            if isinstance(row.get("metadata"), str):
                try:
                    row["metadata"] = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    pass
        return {"items": rows}
    finally:
        conn.close()


@app.get("/dashboard/summary")
def dashboard_summary(user: dict[str, Any] = Depends(require_permission("issues.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_count,
                  SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress_count,
                  SUM(CASE WHEN status = 'in_review' THEN 1 ELSE 0 END) AS in_review_count,
                  SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved_count,
                  SUM(CASE WHEN status = 'no_action' THEN 1 ELSE 0 END) AS no_action_count,
                  SUM(CASE WHEN frequency > 600 THEN 1 ELSE 0 END) AS critical_count
                FROM service_exception_log
                """
            )
            row = cur.fetchone() or {}
        return {
            "total": int(row.get("total") or 0),
            "backlog": int(row.get("open_count") or 0),
            "wip": int(row.get("in_progress_count") or 0),
            "review": int(row.get("in_review_count") or 0),
            "resolved": int(row.get("resolved_count") or 0),
            "no_action": int(row.get("no_action_count") or 0),
            "critical": int(row.get("critical_count") or 0),
        }
    finally:
        conn.close()


@app.get("/dashboard/charts")
def dashboard_charts(user: dict[str, Any] = Depends(require_permission("issues.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  service_name,
                  COUNT(*) AS total,
                  SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS backlog,
                  SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS wip,
                  SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved
                FROM service_exception_log
                GROUP BY service_name
                ORDER BY service_name
                """
            )
            services = cur.fetchall()
            cur.execute(
                """
                SELECT source, COUNT(*) AS total
                FROM service_exception_log
                GROUP BY source
                ORDER BY total DESC, source ASC
                """
            )
            sources = cur.fetchall()
            cur.execute(
                """
                SELECT issue_type, COUNT(*) AS total
                FROM service_exception_log
                GROUP BY issue_type
                ORDER BY total DESC, issue_type ASC
                LIMIT 10
                """
            )
            issue_types = cur.fetchall()
        return {
            "services": services,
            "sources": sources,
            "issue_types": issue_types,
        }
    finally:
        conn.close()


@app.get("/dashboard/escalations")
def dashboard_escalations(limit: int = 10, user: dict[str, Any] = Depends(require_permission("issues.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sel.id, fingerprint, service_name, issue_type, source, description, stack_trace,
                       frequency, first_seen, last_seen, status, assigned_to, resolution_pr,
                       resolution_jira, created_at, resolved_at, entire_execution_logs, request_id,
                       (
                         SELECT aes.session_id
                         FROM agent_execution_sessions aes
                         WHERE aes.issue_id = sel.id
                         ORDER BY aes.created_at DESC
                         LIMIT 1
                       ) AS latest_execution_session_id
                FROM service_exception_log sel
                WHERE status IN ('open', 'in_progress') AND frequency > 400
                ORDER BY frequency DESC, last_seen DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return {"items": [map_issue(row) for row in rows]}
    finally:
        conn.close()


@app.get("/dashboard/feed")
def dashboard_feed(limit: int = 12, user: dict[str, Any] = Depends(require_permission("issues.read"))):
    conn = get_db()
    try:
        items: list[dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, service_name, issue_type, status, frequency, last_seen, resolved_at, created_at, description
                FROM service_exception_log
                ORDER BY GREATEST(COALESCE(last_seen, created_at), COALESCE(resolved_at, created_at), created_at) DESC
                LIMIT %s
                """,
                (limit,),
            )
            for row in cur.fetchall():
                status = row["status"]
                if status == "resolved":
                    title = f"{row['service_name']} resolved"
                    event_type = "resolved"
                elif status == "in_progress":
                    title = f"{row['service_name']} moved to WIP"
                    event_type = "in_progress"
                elif int(row["frequency"] or 0) > 400:
                    title = f"{row['service_name']} escalated with freq={row['frequency']}"
                    event_type = "escalated"
                else:
                    title = f"New activity in {row['service_name']}"
                    event_type = "open"
                items.append(
                    {
                        "id": row["id"],
                        "jiraId": f"GH-{row['id']}",
                        "event_type": event_type,
                        "title": title,
                        "meta": row["description"] or row["issue_type"],
                        "time": dt_to_str(row.get("resolved_at") or row.get("last_seen")),
                    }
                )
        return {"items": items}
    finally:
        conn.close()


@app.get("/sonar/status")
def sonar_status(limit: int = 10, user: dict[str, Any] = Depends(require_permission("issues.read"))):
    try:
        reports = list_sonar_reports(limit=max(1, min(limit, 50)))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not list Sonar reports: {exc}") from exc

    latest = reports[0] if reports else None
    return {
        "lambda_name": SONAR_LAMBDA_NAME,
        "bucket": SONAR_REPORT_BUCKET,
        "region": AWS_REGION,
        "latest_report": latest,
        "reports": reports,
    }


@app.post("/sonar/invoke")
def invoke_sonar_scan(payload: SonarInvokeRequest, actor: dict[str, Any] = Depends(require_permission("issues.update"))):
    client = boto3.client("lambda", region_name=AWS_REGION)
    request_payload = {
        "source": "bugdaddy-platform",
        "requested_by": actor["username"],
        "requested_at": utc_now().isoformat(),
        "reason": payload.reason,
    }
    try:
        response = client.invoke(
            FunctionName=SONAR_LAMBDA_NAME,
            InvocationType="Event",
            Payload=json.dumps(request_payload).encode("utf-8"),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not invoke Sonar scan: {exc}") from exc

    conn = get_db()
    try:
        write_audit_log(
            conn,
            actor["id"],
            "sonar.invoke",
            "lambda",
            SONAR_LAMBDA_NAME,
            {"status_code": response.get("StatusCode"), "reason": payload.reason},
        )
    finally:
        conn.close()

    return {
        "message": "SonarQube scan trigger accepted",
        "lambda_name": SONAR_LAMBDA_NAME,
        "status_code": response.get("StatusCode"),
    }


@app.get("/sonar/reports/{report_date}/url")
def sonar_report_url(report_date: str, user: dict[str, Any] = Depends(require_permission("issues.read"))):
    key = sonar_report_key(report_date)
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        s3.head_object(Bucket=SONAR_REPORT_BUCKET, Key=key)
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": SONAR_REPORT_BUCKET, "Key": key},
            ExpiresIn=SONAR_PRESIGN_EXPIRES_SECONDS,
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Sonar report not available: {exc}") from exc
    return {
        "date": report_date,
        "key": key,
        "url": url,
        "expires_in": SONAR_PRESIGN_EXPIRES_SECONDS,
    }


@app.get("/issues")
def list_issues(
    q: str | None = None,
    service_name: str | None = None,
    status: str | None = None,
    source: str | None = None,
    criticality: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "desc",
    limit: int = 200,
    user: dict[str, Any] = Depends(require_permission("issues.read")),
):
    allowed_sort = {
        "id": "id",
        "frequency": "frequency",
        "last_seen": "last_seen",
        "created_at": "created_at",
        "service_name": "service_name",
        "status": "status",
    }
    sort_col = allowed_sort.get(sort_by, "id")
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    where_parts = ["1=1"]
    params: list[Any] = []
    if q:
        like = f"%{q}%"
        where_parts.append("(CAST(id AS CHAR) LIKE %s OR fingerprint LIKE %s OR service_name LIKE %s OR description LIKE %s)")
        params.extend([like, like, like, like])
    if service_name:
        where_parts.append("service_name = %s")
        params.append(service_name)
    if status:
        where_parts.append("status = %s")
        params.append(status)
    if source:
        where_parts.append("source = %s")
        params.append(source)

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT sel.id, fingerprint, service_name, issue_type, source, description, stack_trace,
                       frequency, first_seen, last_seen, status, assigned_to, resolution_pr,
                       resolution_jira, created_at, resolved_at, entire_execution_logs, request_id,
                       (
                         SELECT aes.session_id
                         FROM agent_execution_sessions aes
                         WHERE aes.issue_id = sel.id
                         ORDER BY aes.created_at DESC
                         LIMIT 1
                       ) AS latest_execution_session_id
                FROM service_exception_log sel
                WHERE {' AND '.join(where_parts)}
                ORDER BY {sort_col} {direction}
                LIMIT %s
                """,
                (*params, limit),
            )
            items = [map_issue(row) for row in cur.fetchall()]
        if criticality:
            items = [item for item in items if item["criticality"].lower() == criticality.lower()]
        return {"items": items}
    finally:
        conn.close()


@app.get("/issues/{issue_id}")
def get_issue(issue_id: int, user: dict[str, Any] = Depends(require_permission("issues.read"))):
    conn = get_db()
    try:
        issue = fetch_issue_by_id(conn, issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        return issue
    finally:
        conn.close()


@app.patch("/issues/{issue_id}")
def update_issue(issue_id: int, payload: IssueUpdateRequest, actor: dict[str, Any] = Depends(require_permission("issues.update"))):
    conn = get_db()
    try:
        existing = fetch_issue_by_id(conn, issue_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Issue not found")
        fields: list[str] = []
        values: list[Any] = []
        if payload.status is not None:
            fields.append("status = %s")
            values.append(payload.status)
            if payload.status == "resolved":
                fields.append("resolved_at = %s")
                values.append(utc_now().strftime("%Y-%m-%d %H:%M:%S"))
        if payload.assigned_to is not None:
            fields.append("assigned_to = %s")
            values.append(payload.assigned_to)
        if payload.resolution_pr is not None:
            fields.append("resolution_pr = %s")
            values.append(payload.resolution_pr)
        if payload.resolution_jira is not None:
            fields.append("resolution_jira = %s")
            values.append(payload.resolution_jira)
        if not fields:
            return existing
        with conn.cursor() as cur:
            cur.execute(f"UPDATE service_exception_log SET {', '.join(fields)} WHERE id = %s", (*values, issue_id))
        updated = fetch_issue_by_id(conn, issue_id)
        write_audit_log(conn, actor["id"], "issues.update", "service_exception_log", str(issue_id), payload.model_dump(exclude_none=True))
        return updated
    finally:
        conn.close()


@app.post("/issues/{issue_id}/prioritize")
def prioritize_issue(issue_id: int, actor: dict[str, Any] = Depends(require_permission("issues.update"))):
    conn = get_db()
    try:
        if not fetch_issue_by_id(conn, issue_id):
            raise HTTPException(status_code=404, detail="Issue not found")
        with conn.cursor() as cur:
            cur.execute("UPDATE service_exception_log SET status = 'in_progress' WHERE id = %s", (issue_id,))
        write_audit_log(conn, actor["id"], "issues.prioritize", "service_exception_log", str(issue_id))
        return fetch_issue_by_id(conn, issue_id)
    finally:
        conn.close()


@app.post("/issues/{issue_id}/assign")
def assign_issue(issue_id: int, payload: IssueAssignRequest, actor: dict[str, Any] = Depends(require_permission("issues.update"))):
    conn = get_db()
    try:
        if not fetch_issue_by_id(conn, issue_id):
            raise HTTPException(status_code=404, detail="Issue not found")
        with conn.cursor() as cur:
            cur.execute("UPDATE service_exception_log SET assigned_to = %s WHERE id = %s", (payload.assigned_to, issue_id))
        write_audit_log(conn, actor["id"], "issues.assign", "service_exception_log", str(issue_id), {"assigned_to": payload.assigned_to})
        return fetch_issue_by_id(conn, issue_id)
    finally:
        conn.close()


@app.post("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: int, payload: IssueUpdateRequest, actor: dict[str, Any] = Depends(require_permission("issues.update"))):
    conn = get_db()
    try:
        if not fetch_issue_by_id(conn, issue_id):
            raise HTTPException(status_code=404, detail="Issue not found")
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE service_exception_log
                SET status = 'resolved',
                    resolved_at = %s,
                    resolution_pr = COALESCE(%s, resolution_pr),
                    resolution_jira = COALESCE(%s, resolution_jira)
                WHERE id = %s
                """,
                (
                    utc_now().strftime("%Y-%m-%d %H:%M:%S"),
                    payload.resolution_pr,
                    payload.resolution_jira,
                    issue_id,
                ),
            )
        write_audit_log(
            conn,
            actor["id"],
            "issues.resolve",
            "service_exception_log",
            str(issue_id),
            {"resolution_pr": payload.resolution_pr, "resolution_jira": payload.resolution_jira},
        )
        return fetch_issue_by_id(conn, issue_id)
    finally:
        conn.close()


@app.post("/agent/executions")
def create_agent_execution(payload: AgentExecutionCreateRequest, actor: dict[str, Any] = Depends(require_permission("issues.update"))):
    conn = get_db()
    try:
        if payload.issue_id is not None and not fetch_issue_by_id(conn, payload.issue_id):
            raise HTTPException(status_code=404, detail="Issue not found")
        workflow_key = payload.workflow_key or workflow_key_for_target(payload.target)
        session_id = create_execution_session(
            conn,
            issue_id=payload.issue_id,
            workflow_key=workflow_key,
            workflow_version=payload.workflow_version,
            agent_target=payload.target,
            started_by=actor["username"],
            input_payload=payload.input_payload,
            metadata=payload.metadata,
            status_value="queued",
        )
        append_execution_event(
            conn,
            session_id,
            {
                "event_type": "session.created",
                "status": "queued",
                "level": "info",
                "title": "Execution session created",
                "description": f"Workflow {workflow_key} is queued.",
                "agent_name": payload.target,
            },
        )
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_execution_sessions WHERE session_id = %s", (session_id,))
            return map_execution_session(cur.fetchone())
    finally:
        conn.close()


@app.get("/agent/executions")
def list_agent_executions(
    issue_id: int | None = None,
    limit: int = 50,
    user: dict[str, Any] = Depends(require_permission("issues.read")),
):
    conn = get_db()
    try:
        limit = max(1, min(limit, 200))
        where = []
        params: list[Any] = []
        if issue_id is not None:
            where.append("issue_id = %s")
            params.append(issue_id)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM agent_execution_sessions
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            return {"items": [map_execution_session(row) for row in cur.fetchall()]}
    finally:
        conn.close()


@app.get("/agent/executions/{session_id}")
def get_agent_execution(session_id: str, user: dict[str, Any] = Depends(require_permission("issues.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_execution_sessions WHERE session_id = %s", (session_id,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Execution session not found")
        return map_execution_session(row)
    finally:
        conn.close()


@app.get("/agent/executions/{session_id}/events")
def list_agent_execution_events(
    session_id: str,
    after_id: int = 0,
    limit: int = 500,
    user: dict[str, Any] = Depends(require_permission("issues.read")),
):
    conn = get_db()
    try:
        limit = max(1, min(limit, 1000))
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM agent_execution_sessions WHERE session_id = %s", (session_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Execution session not found")
            cur.execute(
                """
                SELECT *
                FROM agent_execution_logs
                WHERE session_id = %s AND id > %s
                ORDER BY id ASC
                LIMIT %s
                """,
                (session_id, after_id, limit),
            )
            return {"items": [map_execution_event(row) for row in cur.fetchall()]}
    finally:
        conn.close()


@app.post("/agent/executions/{session_id}/events")
def append_agent_execution_event(
    session_id: str,
    payload: AgentExecutionEventCreate,
    _secret: None = Depends(verify_execution_log_secret),
):
    conn = get_db()
    try:
        return append_execution_event(conn, session_id, payload)
    finally:
        conn.close()


@app.post("/agent/executions/{session_id}/resolution/jira")
def map_agent_execution_jira_resolution(
    session_id: str,
    payload: JiraResolutionMapRequest,
    _secret: None = Depends(verify_execution_log_secret),
):
    resolution_jira = _normalize_jira_resolution(payload.jira_url or payload.resolution_jira or payload.jira_key)
    if not resolution_jira:
        raise HTTPException(status_code=400, detail="Provide jira_key, jira_url, or resolution_jira")
    return _map_execution_resolution(session_id, resolution_jira=resolution_jira)


@app.post("/agent/executions/{session_id}/resolution/pr")
def map_agent_execution_pull_request_resolution(
    session_id: str,
    payload: PullRequestResolutionMapRequest,
    _secret: None = Depends(verify_execution_log_secret),
):
    resolution_pr = payload.pull_request_url or payload.pr_url or payload.resolution_pr
    if not resolution_pr:
        raise HTTPException(status_code=400, detail="Provide pull_request_url, pr_url, or resolution_pr")
    return _map_execution_resolution(session_id, resolution_pr=resolution_pr)


@app.get("/agent/workflows/{workflow_key}")
def get_agent_workflow(
    workflow_key: str,
    workflow_version: str | None = None,
    user: dict[str, Any] = Depends(require_permission("issues.read")),
):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            if workflow_version:
                cur.execute(
                    """
                    SELECT *
                    FROM agent_workflow_definitions
                    WHERE workflow_key = %s AND workflow_version = %s
                    LIMIT 1
                    """,
                    (workflow_key, workflow_version),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM agent_workflow_definitions
                    WHERE workflow_key = %s AND is_active = TRUE
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (workflow_key,),
                )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workflow definition not found")
        if isinstance(row.get("graph_json"), str):
            row["graph_json"] = json.loads(row["graph_json"])
        row["created_at"] = dt_to_str(row["created_at"])
        return row
    finally:
        conn.close()


@app.get("/agent/executions/{session_id}/graph")
def get_agent_execution_graph(session_id: str, user: dict[str, Any] = Depends(require_permission("issues.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_execution_sessions WHERE session_id = %s", (session_id,))
            session = cur.fetchone()
            if not session:
                raise HTTPException(status_code=404, detail="Execution session not found")
            cur.execute(
                """
                SELECT *
                FROM agent_workflow_definitions
                WHERE workflow_key = %s AND workflow_version = %s
                LIMIT 1
                """,
                (session["workflow_key"], session["workflow_version"]),
            )
            workflow = cur.fetchone()
            cur.execute(
                """
                SELECT *
                FROM agent_execution_logs
                WHERE session_id = %s
                ORDER BY id ASC
                LIMIT 1000
                """,
                (session_id,),
            )
            events = cur.fetchall()
        if workflow and isinstance(workflow.get("graph_json"), str):
            workflow["graph_json"] = json.loads(workflow["graph_json"])
        return {
            "session": map_execution_session(session),
            "workflow": workflow,
            "events": [map_execution_event(row) for row in events],
        }
    finally:
        conn.close()


def _extract_jira_key(result: dict[str, Any]) -> str | None:
    """Extract a Jira ticket key (e.g. BUG-123) from an agent result dict."""
    # Explicit field set by classifier or upstream agent
    if result.get("resolution_jira"):
        return str(result["resolution_jira"])

    # Scan artifacts list for jira_ticket entries that contain a key
    for artifact in result.get("artifacts", []):
        content = artifact.get("content", "")
        if artifact.get("type") == "jira_ticket":
            if isinstance(content, dict) and content.get("key"):
                return str(content["key"])
            text = json.dumps(content) if isinstance(content, dict) else str(content)
            match = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", text)
            if match:
                return match.group(1)

    # Fallback: scan review_response artifacts
    review_response = result.get("review_response") or {}
    for artifact in review_response.get("artifacts", []):
        content = artifact.get("content", "")
        if artifact.get("type") == "jira_ticket":
            text = json.dumps(content) if isinstance(content, dict) else str(content)
            match = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", text)
            if match:
                return match.group(1)

    # Last resort: scan summary text
    summary = str(result.get("summary") or "")
    match = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", summary)
    return match.group(1) if match else None


def _extract_pull_request_url(result: dict[str, Any]) -> str | None:
    """Extract a pull request URL from an agent result dict."""
    if result.get("resolution_pr"):
        return str(result["resolution_pr"])

    candidates: list[Any] = []
    candidates.extend(result.get("artifacts", []))
    review_response = result.get("review_response") or {}
    if isinstance(review_response, dict):
        candidates.extend(review_response.get("artifacts", []))
        if review_response.get("resolution_pr"):
            return str(review_response["resolution_pr"])

    for artifact in candidates:
        if not isinstance(artifact, dict) or artifact.get("type") != "pull_request":
            continue
        content = artifact.get("content", "")
        if isinstance(content, dict):
            for key in ("url", "html_url", "pull_request_url", "pr_url"):
                if content.get(key):
                    return str(content[key])
            text = json.dumps(content)
        else:
            text = str(content)
        match = re.search(r"https?://[^\s)>\"]+/pull/\d+", text)
        if match:
            return match.group(0)

    summary = str(result.get("summary") or "")
    match = re.search(r"https?://[^\s)>\"]+/pull/\d+", summary)
    return match.group(0) if match else None


def _normalize_jira_resolution(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if re.match(r"https?://", cleaned):
        return cleaned
    match = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", cleaned)
    if match:
        return f"{JIRA_BASE_URL}/browse/{match.group(1)}"
    return cleaned


def _map_execution_resolution(
    session_id: str,
    resolution_jira: str | None = None,
    resolution_pr: str | None = None,
) -> dict[str, Any]:
    if not resolution_jira and not resolution_pr:
        raise HTTPException(status_code=400, detail="No resolution value provided")

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT issue_id FROM agent_execution_sessions WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Execution session not found")
        issue_id = row.get("issue_id")
        if not issue_id:
            raise HTTPException(status_code=400, detail="Execution session is not linked to an issue")

        fields: list[str] = []
        values: list[Any] = []
        event_result: dict[str, Any] = {}
        if resolution_jira:
            fields.append("resolution_jira = %s")
            values.append(resolution_jira)
            event_result["resolution_jira"] = resolution_jira
        if resolution_pr:
            fields.append("resolution_pr = %s")
            values.append(resolution_pr)
            event_result["resolution_pr"] = resolution_pr
        fields.append("status = CASE WHEN status = 'open' THEN 'in_progress' ELSE status END")

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE service_exception_log SET {', '.join(fields)} WHERE id = %s",
                (*values, issue_id),
            )
        append_execution_event(
            conn,
            session_id,
            {
                "event_type": "node.completed",
                "node_id": "resmap",
                "node_name": "Resolution Mapping",
                "agent_name": "platform",
                "status": "succeeded",
                "level": "info",
                "title": "Issue resolution link mapped",
                "result": event_result,
            },
        )
        return fetch_issue_by_id(conn, issue_id)
    finally:
        conn.close()


def run_agent_background(session_id: str, runtime_payload: dict[str, Any], target: str):
    try:
        result = invoke_agentcore(runtime_payload)
        summary = str(result.get("summary") or result.get("message") or result.get("raw") or "")[:4000]
        conn = get_db()
        try:
            append_execution_event(
                conn,
                session_id,
                {
                    "event_type": "node.completed",
                    "node_id": "esc",
                    "node_name": "AgentCore Runtime",
                    "agent_name": target,
                    "status": "succeeded",
                    "level": "info",
                    "title": "AgentCore invocation completed",
                    "output_summary": summary,
                    "result": result,
                },
            )
            append_execution_event(
                conn,
                session_id,
                {
                    "event_type": "session.completed",
                    "status": "succeeded",
                    "level": "info",
                    "title": "Execution completed",
                    "output_summary": summary,
                },
            )
            update_execution_session(conn, session_id, status_value="succeeded", summary=summary, ended=True)

            # Map Jira ticket back to service_exception_log
            jira_key = _extract_jira_key(result)
            pr_url = _extract_pull_request_url(result)
            if jira_key:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT issue_id FROM agent_execution_sessions WHERE session_id = %s",
                        (session_id,),
                    )
                    row = cur.fetchone()
                issue_id = row["issue_id"] if row else None
                if issue_id:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE service_exception_log
                            SET resolution_jira = %s,
                                status = CASE WHEN status = 'open' THEN 'in_progress' ELSE status END
                            WHERE id = %s AND (resolution_jira IS NULL OR resolution_jira = '')
                            """,
                            (_normalize_jira_resolution(jira_key), issue_id),
                        )
            if pr_url:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT issue_id FROM agent_execution_sessions WHERE session_id = %s",
                        (session_id,),
                    )
                    row = cur.fetchone()
                issue_id = row["issue_id"] if row else None
                if issue_id:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE service_exception_log
                            SET resolution_pr = %s,
                                status = CASE WHEN status = 'open' THEN 'in_progress' ELSE status END
                            WHERE id = %s AND (resolution_pr IS NULL OR resolution_pr = '')
                            """,
                            (pr_url, issue_id),
                        )
        finally:
            conn.close()
    except Exception as exc:
        conn = get_db()
        try:
            append_execution_event(
                conn,
                session_id,
                {
                    "event_type": "node.failed",
                    "node_id": "esc",
                    "node_name": "AgentCore Runtime",
                    "agent_name": target,
                    "status": "failed",
                    "level": "error",
                    "title": "AgentCore invocation failed",
                    "error_message": str(exc),
                },
            )
            append_execution_event(
                conn,
                session_id,
                {
                    "event_type": "session.failed",
                    "status": "failed",
                    "level": "error",
                    "title": "Execution failed",
                    "error_message": str(exc),
                },
            )
            update_execution_session(conn, session_id, status_value="failed", error_message=str(exc), ended=True)
        finally:
            conn.close()

@app.post("/agent/invoke")
def agent_invoke(
    payload: AgentInvokeRequest,
    bg_tasks: BackgroundTasks,
    actor: dict[str, Any] = Depends(require_permission("issues.update"))
):
    issue_context: dict[str, Any] = {}
    if payload.issue_id is not None:
        conn = get_db()
        try:
            issue = fetch_issue_by_id(conn, payload.issue_id)
            if not issue:
                raise HTTPException(status_code=404, detail="Issue not found")
            issue_context = {
                "issue_id": issue["id"],
                "jira_id": issue["jiraId"],
                "issue_type": issue["type"],
                "criticality": issue["criticality"],
                "status": issue["status"],
                "resolution_jira": issue.get("resolution_jira"),
                "resolution_pr": issue.get("resolution_pr"),
                "description": issue["description"],
                "stack_trace": issue["stack_trace"],
                "frequency": issue["frequency"],
                "service_name": issue["service"],
            }
            if not payload.service_name:
                payload.service_name = issue["service"]
            if not payload.incident_summary:
                payload.incident_summary = issue["description"] or issue["err"]
            if not payload.logs and issue.get("entire_execution_logs"):
                payload.logs = [issue["entire_execution_logs"]]
        finally:
            conn.close()

    target = payload.target or (route_issue_agent(issue_context) if issue_context else "incident_daddy")
    runtime_target = target
    if target == "bug_daddy" and not (
        payload.metadata.get("jira_key")
        or payload.metadata.get("resolution_jira")
        or issue_context.get("resolution_jira")
    ):
        runtime_target = "classifier"
    workflow_key = workflow_key_for_target(target)
    metadata = {
        **payload.metadata,
        "requested_by": actor["username"],
        "requester_role": actor["role"],
        "issue_context": issue_context,
        "agent_target": target,
        "runtime_target": runtime_target,
        "workflow_key": workflow_key,
        "routing_source": "explicit_target" if payload.target else "backend_policy",
    }
    session_id = payload.session_id

    runtime_payload = {
        "target": runtime_target,
        "prompt": payload.prompt or payload.incident_summary or "Investigate issue and provide next actions.",
        "question": payload.question,
        "source": payload.source,
        "service_name": payload.service_name,
        "logs": payload.logs,
        "metadata": metadata,
        "incident_summary": payload.incident_summary,
        "repository": payload.repository,
    }
    runtime_payload = {k: v for k, v in runtime_payload.items() if v is not None}

    conn = get_db()
    try:
        if not session_id:
            session_id = create_execution_session(
                conn,
                issue_id=payload.issue_id,
                workflow_key=workflow_key,
                workflow_version="v1",
                agent_target=target,
                started_by=actor["username"],
                input_payload=runtime_payload,
                metadata=metadata,
                status_value="queued",
            )
            append_execution_event(
                conn,
                session_id,
                {
                    "event_type": "session.created",
                    "status": "queued",
                    "level": "info",
                    "title": "Execution session created",
                    "description": f"Workflow {workflow_key} was created for issue {payload.issue_id}.",
                    "agent_name": runtime_target,
                },
            )

        runtime_payload["session_id"] = session_id
        runtime_payload["metadata"] = {
            **runtime_payload.get("metadata", {}),
            "execution_session_id": session_id,
        }
        if AGENT_EXECUTION_CALLBACK_URL:
            runtime_payload["execution_log_endpoint"] = AGENT_EXECUTION_CALLBACK_URL.rstrip("/")
        if AGENT_EXECUTION_LOG_SECRET:
            runtime_payload["execution_log_secret"] = AGENT_EXECUTION_LOG_SECRET

        update_execution_session(conn, session_id, status_value="running")
        append_execution_event(
            conn,
            session_id,
            {
                "event_type": "session.started",
                "status": "running",
                "level": "info",
                "title": "Agent orchestration started",
                "description": f"Invoking {runtime_target} through AgentCore.",
                "agent_name": runtime_target,
                "result": {"runtime_arn": AGENTCORE_RUNTIME_ARN},
            },
        )
        append_execution_event(
            conn,
            session_id,
            {
                "event_type": "node.started",
                "node_id": "esc",
                "node_name": "AgentCore Runtime",
                "agent_name": runtime_target,
                "status": "running",
                "level": "info",
                "title": "AgentCore invocation started",
                "input_summary": runtime_payload.get("prompt"),
            },
        )
    finally:
        conn.close()

    bg_tasks.add_task(run_agent_background, session_id, runtime_payload, runtime_target)

    return {
        "message": "Agent orchestration started in background",
        "session_id": session_id,
        "workflow_key": workflow_key,
        "target": runtime_target,
        "requested_target": target,
        "request": runtime_payload
    }
