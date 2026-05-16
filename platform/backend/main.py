import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import boto3
from botocore.config import Config as BotocoreConfig
import pymysql
import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from schema_app import ensure_core_schema, schema_status, seed_core_data


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
SECURITY_SCANNER_AWS_REGION = os.getenv("SECURITY_SCANNER_AWS_REGION", AWS_REGION)
SECURITY_SCANNER_ACCESS_KEY_ID = os.getenv("SECURITY_SCANNER_ACCESS_KEY_ID")
SECURITY_SCANNER_SECRET_ACCESS_KEY = os.getenv("SECURITY_SCANNER_SECRET_ACCESS_KEY")
AI_QUEUE_URL = os.getenv(
    "AI_QUEUE_URL",
    "https://sqs.ap-south-1.amazonaws.com/105028893980/bug-daddy-ai-automation-queue",
)
AI_QUEUE_WORKERS = int(os.getenv("AI_QUEUE_WORKERS", "3"))
AI_QUEUE_POLL_SECONDS = int(os.getenv("AI_QUEUE_POLL_SECONDS", "10"))
AI_QUEUE_DEFAULT_LENGTH = int(os.getenv("AI_QUEUE_DEFAULT_LENGTH", "3"))
AI_QUEUE_STARTED = False

# ---------------------------------------------------------------------------
# Distributed trace ID
# ---------------------------------------------------------------------------
TRACE_ID_HEADER = "x-trace-id"
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """Return the trace ID for the current request."""
    return _trace_id_var.get()


def log_request(method: str, path: str, trace_id: str) -> None:
    """Emit a structured JSON line at the start of every request."""
    print(json.dumps({
        "traceId": trace_id,
        "service": "platform-backend",
        "stage": "request_received",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"method": method, "path": path},
    }))


app = FastAPI(title="Bug Daddy API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """Extract or generate X-Trace-ID for every request and stamp it on the response."""
    trace_id = (
        request.headers.get("x-trace-id")
        or request.headers.get("X-Trace-ID")
        or ""
    ).strip() or str(uuid.uuid4())
    _trace_id_var.set(trace_id)
    log_request(request.method, str(request.url.path), trace_id)
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response


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


class SecurityInvokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class AiQueueConfigUpdateRequest(BaseModel):
    is_active: bool | None = None
    queue_length: int | None = Field(default=None, ge=1, le=50)




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
    try:
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
    except pymysql.err.OperationalError as exc:
        if not exc.args or exc.args[0] != 1049:
            raise
        if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NAME):
            raise RuntimeError("DB_NAME may only contain letters, numbers, and underscores") from exc
        bootstrap_conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=10,
        )
        with bootstrap_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
            cur.execute(f"USE `{DB_NAME}`")
        return bootstrap_conn


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
        {"id": "irw", "label": "Report Writer", "type": "agent", "x": 110, "y": 510},
        {"id": "irr", "label": "Report Reviewer", "type": "agent", "x": 110, "y": 630},
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
            {"from": "inc", "to": "sme"},
            {"from": "inc", "to": "irw"},
            {"from": "irw", "to": "irr"},
            {"from": "irr", "to": "irw"},
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


def get_ai_queue_config(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ai_queue_config WHERE id = 1")
        row = cur.fetchone()
    if not row:
        return {
            "is_active": True,
            "queue_length": AI_QUEUE_DEFAULT_LENGTH,
            "queue_url": AI_QUEUE_URL,
            "updated_by": None,
            "created_at": None,
            "updated_at": None,
        }
    return {
        "is_active": bool(row.get("is_active")),
        "queue_length": int(row.get("queue_length") or AI_QUEUE_DEFAULT_LENGTH),
        "queue_url": row.get("queue_url") or AI_QUEUE_URL,
        "updated_by": row.get("updated_by"),
        "created_at": dt_to_str(row.get("created_at")),
        "updated_at": dt_to_str(row.get("updated_at")),
    }


def ai_queue_counts(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM ai_queue_items
            WHERE status IN ('queued', 'processing', 'completed', 'failed')
            GROUP BY status
            """
        )
        rows = cur.fetchall()
    counts = {"queued": 0, "processing": 0, "completed": 0, "failed": 0}
    for row in rows:
        status_name = str(row.get("status"))
        if status_name in counts:
            counts[status_name] = int(row.get("total") or 0)
    counts["active"] = counts["queued"] + counts["processing"]
    return counts


def sqs_client():
    return boto3.client("sqs", region_name=AWS_REGION)


def enqueue_ai_issue(conn, issue: dict[str, Any], queue_url: str, source: str = "auto") -> bool:
    issue_id = int(issue["id"])
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM ai_queue_items
            WHERE issue_id = %s AND status IN ('queued', 'processing')
            LIMIT 1
            """,
            (issue_id,),
        )
        if cur.fetchone():
            return False
        cur.execute(
            """
            INSERT INTO ai_queue_items (issue_id, status)
            VALUES (%s, 'queued')
            """,
            (issue_id,),
        )
        item_id = cur.lastrowid
    try:
        response = sqs_client().send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps({"queue_item_id": item_id, "issue_id": issue_id, "source": source}),
        )
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ai_queue_items SET sqs_message_id = %s WHERE id = %s",
                (response.get("MessageId"), item_id),
            )
        return True
    except Exception as exc:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ai_queue_items SET status = 'failed', last_error = %s, completed_at = %s WHERE id = %s",
                (str(exc), utc_now().strftime("%Y-%m-%d %H:%M:%S"), item_id),
            )
        raise


def replenish_ai_queue(conn) -> int:
    config = get_ai_queue_config(conn)
    if not config["is_active"]:
        return 0
    capacity = max(0, int(config["queue_length"]) - ai_queue_counts(conn)["active"])
    if capacity <= 0:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sel.id, fingerprint, service_name, issue_type, source, description, stack_trace,
                   frequency, first_seen, last_seen, status, assigned_to, resolution_pr,
                   resolution_jira, created_at, resolved_at, entire_execution_logs, request_id,
                   NULL AS latest_execution_session_id
            FROM service_exception_log sel
            WHERE status = 'open'
              AND NOT EXISTS (
                SELECT 1
                FROM ai_queue_items aqi
                WHERE aqi.issue_id = sel.id AND aqi.status IN ('queued', 'processing')
              )
            ORDER BY frequency DESC, last_seen DESC, id DESC
            LIMIT %s
            """,
            (capacity,),
        )
        issues = [map_issue(row) for row in cur.fetchall()]
    enqueued = 0
    for issue in issues:
        if enqueue_ai_issue(conn, issue, str(config["queue_url"]), source="auto"):
            enqueued += 1
    return enqueued


def _runtime_payload_for_issue(
    conn,
    issue_id: int,
    *,
    started_by: str,
    queue_item_id: int | None = None,
) -> tuple[str, dict[str, Any], str]:
    issue = fetch_issue_by_id(conn, issue_id)
    if not issue:
        raise ValueError(f"Issue {issue_id} not found")
    with conn.cursor() as cur:
        cur.execute("UPDATE service_exception_log SET status = 'in_progress' WHERE id = %s", (issue_id,))
    issue_context = {
        "issue_id": issue["id"],
        "jira_id": issue["jiraId"],
        "issue_type": issue["type"],
        "criticality": issue["criticality"],
        "status": "in_progress",
        "resolution_jira": issue.get("resolution_jira"),
        "resolution_pr": issue.get("resolution_pr"),
        "description": issue["description"],
        "stack_trace": issue["stack_trace"],
        "frequency": issue["frequency"],
        "service_name": issue["service"],
    }
    suggested_target = route_issue_agent(issue_context)
    target = "classifier"
    runtime_target = "classifier"
    workflow_key = workflow_key_for_target(suggested_target)
    logs = []
    if issue.get("stack_trace"):
        logs.append("Stack Trace:\n" + issue["stack_trace"])
    if issue.get("entire_execution_logs"):
        logs.append("Execution Logs:\n" + issue["entire_execution_logs"])
    metadata = {
        "requested_by": started_by,
        "requester_role": "system",
        "issue_context": issue_context,
        "agent_target": target,
        "runtime_target": runtime_target,
        "workflow_key": workflow_key,
        "routing_source": "ai_queue",
        "queue_item_id": queue_item_id,
        "suggested_agent_target": suggested_target,
    }
    runtime_payload = {
        "target": runtime_target,
        "prompt": issue["description"] or issue["err"] or "Investigate issue and provide next actions.",
        "source": "ai_queue",
        "service_name": issue["service"],
        "logs": logs,
        "metadata": metadata,
        "incident_summary": issue["description"] or issue["err"],
    }
    session_id = create_execution_session(
        conn,
        issue_id=issue_id,
        workflow_key=workflow_key,
        workflow_version="v1",
        agent_target=target,
        started_by=started_by,
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
            "title": "Execution session created by AI queue",
            "description": f"Workflow {workflow_key} was created for issue {issue_id}.",
            "agent_name": runtime_target,
        },
    )
    runtime_payload["session_id"] = session_id
    runtime_payload["metadata"] = {
        **metadata,
        "session_id": session_id,
        "execution_callback_url": AGENT_EXECUTION_CALLBACK_URL,
        "execution_log_secret": AGENT_EXECUTION_LOG_SECRET,
    }
    # Also set these at the top level so ExecutionLogger.from_payload can read them directly
    if AGENT_EXECUTION_CALLBACK_URL:
        runtime_payload["execution_log_endpoint"] = AGENT_EXECUTION_CALLBACK_URL.rstrip("/")
    if AGENT_EXECUTION_LOG_SECRET:
        runtime_payload["execution_log_secret"] = AGENT_EXECUTION_LOG_SECRET
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
    update_execution_session(conn, session_id, status_value="running")
    return session_id, runtime_payload, target


def process_ai_queue_message(message: dict[str, Any], worker_id: str, queue_url: str):
    body = json.loads(message.get("Body") or "{}")
    queue_item_id = int(body.get("queue_item_id") or 0)
    issue_id = int(body.get("issue_id") or 0)
    receipt_handle = message["ReceiptHandle"]
    if not queue_item_id or not issue_id:
        sqs_client().delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return
    session_id: str | None = None
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ai_queue_items
                SET status = 'processing', worker_id = %s, attempts = attempts + 1, started_at = COALESCE(started_at, %s)
                WHERE id = %s AND issue_id = %s AND status = 'queued'
                """,
                (worker_id, utc_now().strftime("%Y-%m-%d %H:%M:%S"), queue_item_id, issue_id),
            )
            claimed = cur.rowcount
        if not claimed:
            sqs_client().delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
            return
        try:
            session_id, runtime_payload, target = _runtime_payload_for_issue(
                conn,
                issue_id,
                started_by=worker_id,
                queue_item_id=queue_item_id,
            )
            with conn.cursor() as cur:
                cur.execute("UPDATE ai_queue_items SET session_id = %s WHERE id = %s", (session_id, queue_item_id))
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ai_queue_items
                    SET status = 'failed', last_error = %s, completed_at = %s
                    WHERE id = %s
                    """,
                    (str(exc), utc_now().strftime("%Y-%m-%d %H:%M:%S"), queue_item_id),
                )
            sqs_client().delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
            return
    finally:
        conn.close()

    run_agent_background(session_id, runtime_payload, target)

    conn = get_db()
    try:
        issue = fetch_issue_by_id(conn, issue_id)
        issue_status = issue["status"] if issue else "missing"
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, error_message FROM agent_execution_sessions WHERE session_id = %s",
                (session_id,),
            )
            execution = cur.fetchone() or {}
        if execution.get("status") == "failed":
            final_status = "failed"
            last_error = execution.get("error_message") or "Agent execution failed."
        elif issue_status in {"in_review", "resolved", "no_action"}:
            final_status = "completed"
            last_error = None
        else:
            final_status = "completed"
            last_error = f"Execution finished with issue status {issue_status}; message removed to avoid duplicate invocation."
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ai_queue_items
                SET status = %s, last_error = %s, completed_at = %s
                WHERE id = %s
                """,
                (final_status, last_error, utc_now().strftime("%Y-%m-%d %H:%M:%S"), queue_item_id),
            )
        sqs_client().delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
    finally:
        conn.close()


def ai_queue_worker(worker_index: int):
    worker_id = f"ai-queue-worker-{worker_index}"
    while True:
        try:
            conn = get_db()
            try:
                config = get_ai_queue_config(conn)
                active = config["is_active"]
                queue_url = str(config["queue_url"])
                if active:
                    replenish_ai_queue(conn)
            finally:
                conn.close()
            if not active:
                time.sleep(AI_QUEUE_POLL_SECONDS)
                continue
            response = sqs_client().receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
                VisibilityTimeout=1800,
            )
            for message in response.get("Messages", []):
                process_ai_queue_message(message, worker_id, queue_url)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("AI queue worker failed")
            time.sleep(AI_QUEUE_POLL_SECONDS)


def start_ai_queue_workers():
    global AI_QUEUE_STARTED
    if AI_QUEUE_STARTED or not AI_QUEUE_URL or AI_QUEUE_WORKERS <= 0:
        return
    AI_QUEUE_STARTED = True
    for index in range(1, AI_QUEUE_WORKERS + 1):
        thread = threading.Thread(target=ai_queue_worker, args=(index,), name=f"ai-queue-worker-{index}", daemon=True)
        thread.start()


def invoke_agentcore(payload: dict[str, Any]) -> dict[str, Any]:
    client = boto3.client(
        "bedrock-agentcore",
        region_name=AWS_REGION,
        config=BotocoreConfig(read_timeout=600, connect_timeout=10),
    )
    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
        runtimeSessionId=str(uuid.uuid4()),
        payload=json.dumps(payload).encode("utf-8"),
    )
    body = response.get("response") or response.get("payload")
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sonar_scan_sessions (
              id BIGINT AUTO_INCREMENT PRIMARY KEY,
              session_id CHAR(36) NOT NULL UNIQUE,
              status VARCHAR(30) NOT NULL DEFAULT 'processing',
              triggered_by VARCHAR(255) NULL,
              reason VARCHAR(255) NULL,
              lambda_status_code INT NULL,
              ssm_command_id VARCHAR(255) NULL,
              error_message TEXT NULL,
              started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              completed_at DATETIME NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              INDEX idx_sonar_sessions_status (status),
              INDEX idx_sonar_sessions_created (created_at)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS security_scan_sessions (
              id             BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
              session_id     CHAR(36) NOT NULL UNIQUE,
              status         VARCHAR(30) NOT NULL DEFAULT 'processing',
              triggered_by   VARCHAR(255) NULL,
              current_phase  VARCHAR(100) NULL,
              phase_detail   TEXT NULL,
              assets_count   INT NOT NULL DEFAULT 0,
              dependencies_count INT NOT NULL DEFAULT 0,
              findings_count INT NOT NULL DEFAULT 0,
              critical_count INT NOT NULL DEFAULT 0,
              high_count     INT NOT NULL DEFAULT 0,
              tools_json     JSON NULL,
              report_json    LONGTEXT NULL,
              error_message  TEXT NULL,
              started_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              completed_at   DATETIME NULL,
              created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              INDEX idx_security_sessions_status (status),
              INDEX idx_security_sessions_created (created_at)
            )
            """
        )
        for column_name, definition in [
            ("assets_count", "INT NOT NULL DEFAULT 0 AFTER phase_detail"),
            ("dependencies_count", "INT NOT NULL DEFAULT 0 AFTER assets_count"),
            ("tools_json", "JSON NULL AFTER high_count"),
            ("report_json", "LONGTEXT NULL AFTER tools_json"),
            ("updated_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at"),
        ]:
            cur.execute("SHOW COLUMNS FROM security_scan_sessions LIKE %s", (column_name,))
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE security_scan_sessions ADD COLUMN {column_name} {definition}")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_queue_config (
              id TINYINT NOT NULL PRIMARY KEY,
              is_active BOOLEAN NOT NULL DEFAULT TRUE,
              queue_length INT NOT NULL DEFAULT 3,
              queue_url VARCHAR(512) NULL,
              updated_by VARCHAR(255) NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            INSERT INTO ai_queue_config (id, is_active, queue_length, queue_url)
            VALUES (1, TRUE, %s, %s)
            ON DUPLICATE KEY UPDATE
              queue_url = COALESCE(NULLIF(queue_url, ''), VALUES(queue_url))
            """,
            (AI_QUEUE_DEFAULT_LENGTH, AI_QUEUE_URL),
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_queue_items (
              id BIGINT AUTO_INCREMENT PRIMARY KEY,
              issue_id BIGINT NOT NULL,
              sqs_message_id VARCHAR(255) NULL,
              status VARCHAR(30) NOT NULL DEFAULT 'queued',
              worker_id VARCHAR(100) NULL,
              session_id CHAR(36) NULL,
              attempts INT NOT NULL DEFAULT 0,
              last_error TEXT NULL,
              enqueued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              started_at DATETIME NULL,
              completed_at DATETIME NULL,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              INDEX idx_ai_queue_issue_status (issue_id, status),
              INDEX idx_ai_queue_status (status),
              INDEX idx_ai_queue_updated (updated_at)
            )
            """
        )
        cur.execute("SHOW INDEX FROM ai_queue_items WHERE Key_name = 'uq_ai_queue_issue_active'")
        if cur.fetchone():
            cur.execute("ALTER TABLE ai_queue_items DROP INDEX uq_ai_queue_issue_active")
            cur.execute("ALTER TABLE ai_queue_items ADD INDEX idx_ai_queue_issue_status (issue_id, status)")
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
        ensure_core_schema(conn)
        seed_core_data(conn)
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
    start_ai_queue_workers()
    try:
        from rag.db.init_db import init_db
        init_db()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("RAG DB init failed — support chat will be unavailable")


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


@app.get("/admin/schema/status")
def admin_schema_status(actor: dict[str, Any] = Depends(require_permission("users.read"))):
    conn = get_db()
    try:
        return schema_status(conn)
    finally:
        conn.close()


@app.post("/admin/schema/seed")
def admin_schema_seed(actor: dict[str, Any] = Depends(require_permission("users.update"))):
    conn = get_db()
    try:
        ensure_core_schema(conn)
        seed_core_data(conn)
        write_audit_log(conn, actor["id"], "schema.seed", "schema", DB_NAME)
        return schema_status(conn)
    finally:
        conn.close()


@app.get("/admin/microservices/overview")
def admin_microservices_overview(actor: dict[str, Any] = Depends(require_permission("users.read"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT service_name, bounded_context, owner_team, description, capabilities, health_status, updated_at
                FROM ms_service_registry
                ORDER BY service_name
                """
            )
            services = cur.fetchall()
            cur.execute(
                """
                SELECT service_name, operation, status, COUNT(*) AS total, MAX(created_at) AS last_seen
                FROM ms_service_events
                GROUP BY service_name, operation, status
                ORDER BY service_name, operation, status
                """
            )
            operation_counts = cur.fetchall()
            cur.execute(
                """
                SELECT service_name, operation, request_id, customer_id, entity_type, entity_id, status, error_message, created_at
                FROM ms_service_events
                ORDER BY created_at DESC
                LIMIT 50
                """
            )
            recent_events = cur.fetchall()
        for service in services:
            if isinstance(service.get("capabilities"), str):
                try:
                    service["capabilities"] = json.loads(service["capabilities"])
                except json.JSONDecodeError:
                    pass
            service["updated_at"] = dt_to_str(service.get("updated_at"))
        for row in operation_counts:
            row["total"] = int(row.get("total") or 0)
            row["last_seen"] = dt_to_str(row.get("last_seen"))
        for row in recent_events:
            row["created_at"] = dt_to_str(row.get("created_at"))
        return {"services": services, "operation_counts": operation_counts, "recent_events": recent_events}
    finally:
        conn.close()


# Support routes — thin wrappers that inject external_user_id from the JWT actor,
# then delegate to the embedded RAG router logic directly.

class _SupportChatRequest(BaseModel):
    conversation_id: int | None = None
    session_id: str
    question: str = Field(min_length=1, max_length=6000)
    filters: dict[str, Any] = Field(default_factory=dict)


class _SupportFeedbackRequest(BaseModel):
    message_id: int
    rating: int
    comment: str | None = Field(default=None, max_length=2000)


def _actor_user_id(actor: dict[str, Any]) -> str:
    return str(actor.get("id") or actor.get("username") or actor.get("email") or "unknown-user")


@app.get("/support/health")
def support_health(_actor: dict[str, Any] = Depends(require_permission("issues.read"))):
    from rag.api.router import metrics as rag_metrics
    from rag.db.database import get_db as rag_get_db
    db = next(rag_get_db())
    try:
        rag_metrics(db=db)
    finally:
        db.close()
    return {"status": "ok"}


@app.get("/support/conversations")
def support_conversations(
    session_id: str | None = None,
    actor: dict[str, Any] = Depends(require_permission("issues.read")),
):
    from rag.api.router import list_conversations
    from rag.db.database import get_db as rag_get_db
    db = next(rag_get_db())
    try:
        return list_conversations(external_user_id=_actor_user_id(actor), session_id=session_id, db=db)
    finally:
        db.close()


@app.get("/support/messages/{conversation_id}")
def support_messages(
    conversation_id: int,
    actor: dict[str, Any] = Depends(require_permission("issues.read")),
):
    from rag.api.router import messages
    from rag.db.database import get_db as rag_get_db
    db = next(rag_get_db())
    try:
        return messages(conversation_id=conversation_id, external_user_id=_actor_user_id(actor), db=db)
    finally:
        db.close()


@app.post("/support/chat/stream")
def support_chat_stream(
    payload: _SupportChatRequest,
    actor: dict[str, Any] = Depends(require_permission("issues.read")),
):
    from rag.api.router import chat_stream
    from rag.models.schemas import ChatRequest
    from rag.db.database import get_db as rag_get_db
    db = next(rag_get_db())
    rag_payload = ChatRequest(
        conversation_id=payload.conversation_id,
        external_user_id=_actor_user_id(actor),
        session_id=payload.session_id,
        question=payload.question,
        filters=payload.filters or None,
    )
    # chat_stream returns a StreamingResponse; DB session stays alive until streaming completes
    # because the generator holds a closure over the already-committed answer string.
    return chat_stream(payload=rag_payload, db=db)


@app.post("/support/feedback")
def support_feedback(
    payload: _SupportFeedbackRequest,
    actor: dict[str, Any] = Depends(require_permission("issues.read")),
):
    from rag.api.router import feedback
    from rag.models.schemas import FeedbackRequest
    from rag.db.database import get_db as rag_get_db
    db = next(rag_get_db())
    try:
        return feedback(
            payload=FeedbackRequest(
                message_id=payload.message_id,
                rating=payload.rating,
                comment=payload.comment,
                external_user_id=_actor_user_id(actor),
            ),
            db=db,
        )
    finally:
        db.close()


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


def map_ai_queue_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "issue_id": int(row["issue_id"]),
        "sqs_message_id": row.get("sqs_message_id"),
        "status": row["status"],
        "worker_id": row.get("worker_id"),
        "session_id": row.get("session_id"),
        "attempts": int(row.get("attempts") or 0),
        "last_error": row.get("last_error"),
        "service_name": row.get("service_name"),
        "description": row.get("description"),
        "frequency": int(row.get("frequency") or 0),
        "issue_status": row.get("issue_status"),
        "enqueued_at": dt_to_str(row.get("enqueued_at")),
        "started_at": dt_to_str(row.get("started_at")),
        "completed_at": dt_to_str(row.get("completed_at")),
        "updated_at": dt_to_str(row.get("updated_at")),
    }


@app.get("/admin/ai-queue")
def admin_get_ai_queue(actor: dict[str, Any] = Depends(require_permission("users.read"))):
    conn = get_db()
    try:
        config = get_ai_queue_config(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT aqi.*, sel.service_name, sel.description, sel.frequency, sel.status AS issue_status
                FROM ai_queue_items aqi
                LEFT JOIN service_exception_log sel ON sel.id = aqi.issue_id
                ORDER BY aqi.updated_at DESC, aqi.id DESC
                LIMIT 50
                """
            )
            items = [map_ai_queue_item(row) for row in cur.fetchall()]
        return {
            "config": config,
            "counts": ai_queue_counts(conn),
            "items": items,
            "workers": AI_QUEUE_WORKERS,
        }
    finally:
        conn.close()


@app.patch("/admin/ai-queue")
def admin_update_ai_queue(payload: AiQueueConfigUpdateRequest, actor: dict[str, Any] = Depends(require_permission("users.update"))):
    conn = get_db()
    try:
        fields: list[str] = []
        values: list[Any] = []
        if payload.is_active is not None:
            fields.append("is_active = %s")
            values.append(payload.is_active)
        if payload.queue_length is not None:
            fields.append("queue_length = %s")
            values.append(payload.queue_length)
        if not fields:
            return admin_get_ai_queue(actor)
        fields.append("updated_by = %s")
        values.append(actor["username"])
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE ai_queue_config SET {', '.join(fields)} WHERE id = 1",
                values,
            )
        if payload.is_active is True or payload.queue_length is not None:
            replenish_ai_queue(conn)
        write_audit_log(conn, actor["id"], "admin.ai_queue.update", "ai_queue_config", "1", payload.model_dump(exclude_none=True))
        config = get_ai_queue_config(conn)
        return {"config": config, "counts": ai_queue_counts(conn), "workers": AI_QUEUE_WORKERS}
    finally:
        conn.close()


@app.post("/admin/ai-queue/replenish")
def admin_replenish_ai_queue(actor: dict[str, Any] = Depends(require_permission("users.update"))):
    conn = get_db()
    try:
        enqueued = replenish_ai_queue(conn)
        write_audit_log(conn, actor["id"], "admin.ai_queue.replenish", "ai_queue_items", None, {"enqueued": enqueued})
        return {"enqueued": enqueued, "counts": ai_queue_counts(conn)}
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
                        "source": row["issue_type"],
                        "frequency": int(row["frequency"] or 0),
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

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id, status, triggered_by, reason, lambda_status_code,
                       ssm_command_id, error_message, started_at, completed_at, created_at
                FROM sonar_scan_sessions
                ORDER BY created_at DESC
                LIMIT 20
                """
            )
            sessions = cur.fetchall()
        sessions_list = [
            {
                **s,
                "started_at": dt_to_str(s.get("started_at")),
                "completed_at": dt_to_str(s.get("completed_at")),
                "created_at": dt_to_str(s.get("created_at")),
            }
            for s in sessions
        ]
        in_progress = any(s["status"] == "processing" for s in sessions_list)
    finally:
        conn.close()

    return {
        "lambda_name": SONAR_LAMBDA_NAME,
        "bucket": SONAR_REPORT_BUCKET,
        "region": AWS_REGION,
        "latest_report": latest,
        "reports": reports,
        "sessions": sessions_list,
        "in_progress": in_progress,
    }


@app.post("/sonar/invoke")
def invoke_sonar_scan(payload: SonarInvokeRequest, actor: dict[str, Any] = Depends(require_permission("issues.update"))):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id FROM sonar_scan_sessions WHERE status = 'processing' LIMIT 1"
            )
            active = cur.fetchone()
        if active:
            raise HTTPException(
                status_code=409,
                detail=f"A scan is already in progress (session: {active['session_id']}). Wait for it to complete before starting a new one.",
            )

        session_id = str(uuid.uuid4())
        client = boto3.client("lambda", region_name=AWS_REGION)
        request_payload = {
            "source": "bugdaddy-platform",
            "requested_by": actor["username"],
            "requested_at": utc_now().isoformat(),
            "reason": payload.reason,
            "sonar_session_id": session_id,
        }
        try:
            response = client.invoke(
                FunctionName=SONAR_LAMBDA_NAME,
                InvocationType="Event",
                Payload=json.dumps(request_payload).encode("utf-8"),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not invoke Sonar scan: {exc}") from exc

        lambda_status_code = response.get("StatusCode")
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sonar_scan_sessions
                  (session_id, status, triggered_by, reason, lambda_status_code)
                VALUES (%s, 'processing', %s, %s, %s)
                """,
                (session_id, actor["username"], payload.reason, lambda_status_code),
            )

        write_audit_log(
            conn,
            actor["id"],
            "sonar.invoke",
            "sonar_scan_sessions",
            session_id,
            {"status_code": lambda_status_code, "reason": payload.reason},
        )
    finally:
        conn.close()

    return {
        "message": "SonarQube scan trigger accepted",
        "session_id": session_id,
        "lambda_name": SONAR_LAMBDA_NAME,
        "status_code": lambda_status_code,
    }


@app.post("/sonar/sessions/{session_id}/complete")
def complete_sonar_session(
    session_id: str,
    status: str = "completed",
    error_message: str | None = None,
    ssm_command_id: str | None = None,
    _secret: str | None = Depends(verify_execution_log_secret),
):
    allowed = {"completed", "failed"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status FROM sonar_scan_sessions WHERE session_id = %s LIMIT 1",
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sonar session not found")
        fields = ["status = %s", "completed_at = %s", "updated_at = %s"]
        values: list[Any] = [status, utc_now().strftime("%Y-%m-%d %H:%M:%S"), utc_now().strftime("%Y-%m-%d %H:%M:%S")]
        if error_message is not None:
            fields.append("error_message = %s")
            values.append(error_message)
        if ssm_command_id is not None:
            fields.append("ssm_command_id = %s")
            values.append(ssm_command_id)
        values.append(session_id)
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE sonar_scan_sessions SET {', '.join(fields)} WHERE session_id = %s",
                values,
            )
    finally:
        conn.close()
    return {"message": f"Session {session_id} marked as {status}"}


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


@app.get("/sonar/reports/{report_date}/data")
def sonar_report_data(report_date: str, user: dict[str, Any] = Depends(require_permission("issues.read"))):
    key = sonar_report_key(report_date)
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        obj = s3.get_object(Bucket=SONAR_REPORT_BUCKET, Key=key)
        report = json.loads(obj["Body"].read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Sonar report not available: {exc}") from exc
    return report


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


@app.post("/agent/executions/{session_id}/issue-status")
def update_agent_execution_issue_status(
    session_id: str,
    _secret: None = Depends(verify_execution_log_secret),
):
    """Move the linked issue status to in_review when reviewer_daddy takes ownership."""
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
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE service_exception_log SET status = 'in_review' WHERE id = %s AND status = 'in_progress'",
                (issue_id,),
            )
        return fetch_issue_by_id(conn, issue_id)
    finally:
        conn.close()


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


_PR_URL_RE = re.compile(r"https?://[^\s)>\"]+/pull(?:-requests?)?/\d+")


def _extract_pull_request_url(result: dict[str, Any]) -> str | None:
    """Extract a pull request URL from an agent result dict."""
    if result.get("resolution_pr"):
        return str(result["resolution_pr"])
    if result.get("pr_url"):
        return str(result["pr_url"])

    candidates: list[Any] = []
    candidates.extend(result.get("artifacts", []))
    review_response = result.get("review_response") or {}
    if isinstance(review_response, dict):
        candidates.extend(review_response.get("artifacts", []))
        if review_response.get("resolution_pr"):
            return str(review_response["resolution_pr"])
        if review_response.get("pr_url"):
            return str(review_response["pr_url"])

    for artifact in candidates:
        if not isinstance(artifact, dict):
            continue
        content = artifact.get("content", "")
        if isinstance(content, dict):
            for key in ("url", "html_url", "pull_request_url", "pr_url"):
                if content.get(key):
                    return str(content[key])
            text = json.dumps(content)
        else:
            text = str(content)
        match = _PR_URL_RE.search(text)
        if match:
            return match.group(0)

    summary = str(result.get("summary") or "")
    match = _PR_URL_RE.search(summary)
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
        if resolution_pr:
            fields.append("status = CASE WHEN status IN ('open', 'in_progress') THEN 'in_review' ELSE status END")
        else:
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

            jira_key = _extract_jira_key(result)
            pr_url = _extract_pull_request_url(result)
            if jira_key:
                with conn.cursor() as cur:
                    cur.execute("SELECT issue_id FROM agent_execution_sessions WHERE session_id = %s", (session_id,))
                    row = cur.fetchone()
                issue_id = row["issue_id"] if row else None
                if issue_id:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE service_exception_log
                            SET resolution_jira = COALESCE(NULLIF(resolution_jira, ''), %s),
                                status = CASE WHEN status = 'open' THEN 'in_progress' ELSE status END
                            WHERE id = %s
                            """,
                            (_normalize_jira_resolution(jira_key), issue_id),
                        )
            if pr_url:
                with conn.cursor() as cur:
                    cur.execute("SELECT issue_id FROM agent_execution_sessions WHERE session_id = %s", (session_id,))
                    row = cur.fetchone()
                issue_id = row["issue_id"] if row else None
                if issue_id:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE service_exception_log
                            SET resolution_pr = COALESCE(NULLIF(resolution_pr, ''), %s),
                                status = CASE WHEN status IN ('open', 'in_progress') THEN 'in_review' ELSE status END
                            WHERE id = %s
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
                "source": issue.get("source"),
            }
            if not payload.service_name:
                payload.service_name = issue["service"]
            if not payload.incident_summary:
                payload.incident_summary = issue["description"] or issue["err"]
            if not payload.logs:
                logs_list = []
                if issue.get("stack_trace"):
                    logs_list.append("Stack Trace:\n" + issue["stack_trace"])
                if issue.get("entire_execution_logs"):
                    logs_list.append("Execution Logs:\n" + issue["entire_execution_logs"])
                if logs_list:
                    payload.logs = logs_list
        finally:
            conn.close()

    target = payload.target or (route_issue_agent(issue_context) if issue_context else "incident_daddy")
    runtime_target = target
    if target == "bug_daddy" and not (
        payload.metadata.get("jira_key")
        or payload.metadata.get("resolution_jira")
        or issue_context.get("resolution_jira")
        or issue_context.get("jira_id")
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


# ---------------------------------------------------------------------------
# Security Scanner
# ---------------------------------------------------------------------------

def _update_security_session(conn, session_id: str, **fields):
    if not fields:
        return
    clauses = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [session_id]
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE security_scan_sessions SET {clauses} WHERE session_id = %s",
            values,
        )


def _canonical_security_vuln_id(finding: dict) -> str:
    aliases = finding.get("aliases") or []
    ids = [finding.get("cve_id", ""), *aliases]
    for value in ids:
        if isinstance(value, str) and value.startswith("CVE-"):
            return value
    for value in ids:
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _security_finding_fingerprint(finding: dict) -> str:
    import hashlib as _hashlib

    asset_id = (
        finding.get("asset_id")
        or finding.get("function_arn")
        or finding.get("resource_id")
        or finding.get("service")
        or "unknown"
    )
    identity = "|".join([
        "security_scanner",
        _canonical_security_vuln_id(finding).strip().lower(),
        str(asset_id).strip().lower(),
        str(finding.get("component") or finding.get("package_name") or "unknown").strip().lower(),
    ])
    return _hashlib.sha256(identity.encode()).hexdigest()


def _security_tool_name(finding: dict) -> str:
    return str(finding.get("tool_name") or finding.get("source") or "unknown").upper()


def _upsert_cve_finding(conn, finding: dict, scan_date: str, now: str) -> str:
    cve_id = _canonical_security_vuln_id(finding)
    service = finding.get("service", "unknown")
    severity = finding.get("severity", "UNKNOWN").upper()
    severity_map = {"CRITICAL": "cve_critical", "HIGH": "cve_high", "MEDIUM": "cve_medium", "LOW": "cve_low"}
    issue_type = severity_map.get(severity, "cve_low")
    fingerprint = _security_finding_fingerprint(finding)
    tool_name = _security_tool_name(finding)
    finding = {**finding, "cve_id": cve_id, "tool_name": tool_name, "fingerprint": fingerprint}
    description = f"[{tool_name}] [{cve_id}] {finding.get('description', '')}"[:1000]
    stack_trace = "\n".join([
        f"CVE ID:    {cve_id}",
        f"Tool:      {tool_name}",
        f"Source:    {finding.get('source', '')}",
        f"Severity:  {severity}  CVSS: {finding.get('cvss_score', 'N/A')}",
        f"Component: {finding.get('component', '')} {finding.get('affected_version', '')} ({finding.get('component_type', '')})",
        f"Service:   {service} ({finding.get('asset_type', '')})",
        f"Asset:     {finding.get('asset_id', '')}",
        f"Fix:       {finding.get('fixed_version', '')}",
        f"Published: {finding.get('published', '')}",
        "",
        f"Description: {finding.get('description', '')}",
    ])[:65000]
    execution_logs = json.dumps(finding, indent=2, default=str)[:65000]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM service_exception_log WHERE fingerprint = %s LIMIT 1",
            (fingerprint,),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """UPDATE service_exception_log
                   SET last_seen = %s, description = %s, stack_trace = %s,
                       entire_execution_logs = %s, issue_type = %s,
                       resolved_at = CASE WHEN status = 'resolved' THEN NULL ELSE resolved_at END,
                       status = CASE WHEN status = 'resolved' THEN 'open' ELSE status END
                   WHERE id = %s""",
                (f"{scan_date} 00:00:00", description, stack_trace, execution_logs, issue_type, existing["id"]),
            )
        else:
            cur.execute(
                """INSERT INTO service_exception_log (
                       fingerprint, service_name, issue_type, source, description,
                       stack_trace, entire_execution_logs, request_id, frequency,
                       first_seen, last_seen, status, assigned_to, resolution_pr,
                       resolution_jira, created_at, resolved_at
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    fingerprint, service, issue_type, "security_scanner", description,
                    stack_trace, execution_logs, cve_id, 1,
                    f"{scan_date} 00:00:00", f"{scan_date} 00:00:00",
                    "open", None, None, None, now, None,
                ),
            )
    return fingerprint


def _close_stale_security_findings(conn, seen_fingerprints: set[str], now: str) -> int:
    with conn.cursor() as cur:
        if seen_fingerprints:
            placeholders = ", ".join(["%s"] * len(seen_fingerprints))
            cur.execute(
                f"""UPDATE service_exception_log
                    SET status = 'resolved', resolved_at = %s
                    WHERE source = 'security_scanner'
                      AND status IN ('open', 'in_progress', 'in_review')
                      AND fingerprint NOT IN ({placeholders})""",
                [now, *sorted(seen_fingerprints)],
            )
        else:
            cur.execute(
                """UPDATE service_exception_log
                   SET status = 'resolved', resolved_at = %s
                   WHERE source = 'security_scanner'
                     AND status IN ('open', 'in_progress', 'in_review')""",
                (now,),
            )
        return cur.rowcount


def _security_tool_breakdown(report: dict, findings: list[dict]) -> list[dict]:
    tool_rows = [dict(item) for item in report.get("tool_results", [])]
    grouped: dict[str, dict] = {}
    for finding in findings:
        key = str(finding.get("tool_name") or finding.get("source") or "unknown")
        current = grouped.setdefault(key, {
            "tool": key,
            "category": "vulnerability_source",
            "status": "ok",
            "findings": 0,
            "critical": 0,
            "high": 0,
            "message": "",
        })
        current["findings"] += 1
        if finding.get("severity") == "CRITICAL":
            current["critical"] += 1
        if finding.get("severity") == "HIGH":
            current["high"] += 1
    tool_rows.extend(grouped.values())
    return tool_rows


def _dedupe_security_findings(findings: list[dict]) -> list[dict]:
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    deduped: dict[str, dict] = {}
    for finding in findings:
        fingerprint = _security_finding_fingerprint(finding)
        normalized = {**finding, "fingerprint": fingerprint, "cve_id": _canonical_security_vuln_id(finding)}
        existing = deduped.get(fingerprint)
        if not existing:
            deduped[fingerprint] = normalized
            continue
        existing_tools = {str(existing.get("tool_name") or existing.get("source") or "unknown")}
        existing_tools.add(str(normalized.get("tool_name") or normalized.get("source") or "unknown"))
        existing["tool_name"] = " / ".join(sorted(existing_tools))
        aliases = []
        for value in [*(existing.get("aliases") or []), *(normalized.get("aliases") or [])]:
            if value and value not in aliases:
                aliases.append(value)
        existing["aliases"] = aliases
        if severity_rank.get(normalized.get("severity", "UNKNOWN"), 4) < severity_rank.get(existing.get("severity", "UNKNOWN"), 4):
            for key in ("severity", "cvss_score", "description", "published", "fixed_version", "remediation"):
                if normalized.get(key):
                    existing[key] = normalized[key]
    return list(deduped.values())


def _json_loads_safe(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def run_security_scan_background(session_id: str, triggered_by: str):
    import sys
    import os as _os
    scanner_dir = _os.path.join(_os.path.dirname(__file__), "..", "..", "triggers", "securityScanner")
    scanner_dir = _os.path.abspath(scanner_dir)
    if scanner_dir not in sys.path:
        sys.path.insert(0, scanner_dir)

    conn = get_db()
    now = utc_now().strftime("%Y-%m-%d %H:%M:%S")
    scan_date = utc_now().strftime("%Y-%m-%d")

    try:
        import boto3 as _boto3

        # Build a dedicated boto3 session using scanner-specific credentials if provided,
        # otherwise fall back to the instance role (useful for local dev).
        _scanner_session_kwargs: dict = {"region_name": SECURITY_SCANNER_AWS_REGION}
        if SECURITY_SCANNER_ACCESS_KEY_ID and SECURITY_SCANNER_SECRET_ACCESS_KEY:
            _scanner_session_kwargs["aws_access_key_id"] = SECURITY_SCANNER_ACCESS_KEY_ID
            _scanner_session_kwargs["aws_secret_access_key"] = SECURITY_SCANNER_SECRET_ACCESS_KEY
        _scanner_session = _boto3.Session(**_scanner_session_kwargs)

        # Phase 1 — inventory
        _update_security_session(conn, session_id, current_phase="inventory", phase_detail="Discovering AWS assets...")
        from aws_inventory import inventory_full
        inventory = inventory_full(SECURITY_SCANNER_AWS_REGION, session=_scanner_session)
        assets = inventory["assets"]
        dependencies = inventory["dependencies"]
        tool_results = inventory["tool_results"]
        _update_security_session(
            conn,
            session_id,
            assets_count=len(assets),
            dependencies_count=len(dependencies),
            tools_json=json.dumps(tool_results, default=str),
            phase_detail=f"Discovered {len(assets)} assets and {len(dependencies)} dependency edges.",
        )

        # Phase 2 — package extraction
        _update_security_session(conn, session_id, current_phase="package_extraction", phase_detail="Extracting Lambda deployment packages...")
        from lambda_package_extractor import extract_lambda_dependencies
        lmb = _scanner_session.client("lambda")
        extracted_lambdas = 0
        extracted_packages = 0
        for asset in assets:
            if asset["asset_type"] != "lambda" or asset.get("package_type") == "Image":
                continue
            _update_security_session(conn, session_id, phase_detail=f"Extracting: {asset['service']}")
            pkgs = extract_lambda_dependencies(lmb, asset["service"])
            extracted_lambdas += 1
            extracted_packages += len(pkgs)
            runtime = asset.get("runtime", "")
            comp_type = "npm_package" if runtime.startswith("nodejs") else "pip_package"
            for pkg in pkgs:
                asset["components"].append({"type": comp_type, "name": pkg["name"], "version": pkg["version"]})
        tool_results.append({
            "tool": "lambda_package_extractor",
            "category": "dependency_source",
            "status": "ok",
            "assets": extracted_lambdas,
            "findings": 0,
            "packages": extracted_packages,
            "message": "",
        })

        # Phase 3 — CVE lookup
        _update_security_session(conn, session_id, current_phase="cve_lookup", phase_detail="Starting CVE lookup...")
        from cve_lookup import lookup_cves
        all_findings: list[dict] = []
        for asset in assets:
            for component in asset.get("components", []):
                name = component.get("name", "")
                version = component.get("version", "unknown")
                if not name or version in ("unknown", "latest", ""):
                    continue
                _update_security_session(conn, session_id, phase_detail=f"Checking {name} {version}")
                findings = lookup_cves(component, asset.get("service", ""), asset.get("asset_type", ""), os.getenv("NVD_API_KEY"))
                for finding in findings:
                    finding.setdefault("asset_id", asset.get("asset_id") or asset.get("function_arn") or asset.get("instance_id") or asset.get("service"))
                    finding.setdefault("asset_type", asset.get("asset_type", ""))
                    finding.setdefault("service", asset.get("service", ""))
                all_findings.extend(findings)
        tool_results.append({
            "tool": "osv_nvd",
            "category": "vulnerability_source",
            "status": "ok",
            "findings": len(all_findings),
            "message": "",
        })

        # Phase 3b — Inspector
        _update_security_session(conn, session_id, phase_detail="Collecting AWS Inspector active findings...")
        from aws_inspector import collect_inspector_findings
        inspector_findings, inspector_result = collect_inspector_findings(
            SECURITY_SCANNER_AWS_REGION,
            session=_scanner_session,
        )
        all_findings.extend(inspector_findings)
        tool_results.append(inspector_result)
        all_findings = _dedupe_security_findings(all_findings)

        # Phase 4 — save findings
        _update_security_session(conn, session_id, current_phase="report", phase_detail="Saving findings to database...")
        from report import build_report
        report = build_report(assets, all_findings, dependencies=dependencies, tool_results=tool_results)
        critical = sum(1 for f in all_findings if f.get("severity") == "CRITICAL")
        high = sum(1 for f in all_findings if f.get("severity") == "HIGH")
        seen_fingerprints: set[str] = set()
        for finding in all_findings:
            seen_fingerprints.add(_upsert_cve_finding(conn, finding, scan_date, now))
        stale_closed = _close_stale_security_findings(conn, seen_fingerprints, now)
        tool_breakdown = _security_tool_breakdown(report, all_findings)

        _update_security_session(
            conn, session_id,
            status="completed",
            current_phase="report",
            phase_detail=f"Done — {len(all_findings)} unique CVE finding(s), {stale_closed} stale finding(s) closed",
            assets_count=len(assets),
            dependencies_count=len(dependencies),
            findings_count=len(all_findings),
            critical_count=critical,
            high_count=high,
            tools_json=json.dumps(tool_breakdown, default=str),
            report_json=json.dumps(report, default=str),
            completed_at=now,
        )

    except Exception as exc:
        _update_security_session(
            conn, session_id,
            status="failed",
            error_message=str(exc)[:1000],
            completed_at=now,
        )
    finally:
        conn.close()


@app.post("/security/invoke")
def invoke_security_scan(
    payload: SecurityInvokeRequest,
    bg_tasks: BackgroundTasks,
    actor: dict[str, Any] = Depends(require_permission("issues.update")),
):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id FROM security_scan_sessions WHERE status = 'processing' LIMIT 1"
            )
            active = cur.fetchone()
        if active:
            raise HTTPException(
                status_code=409,
                detail=f"A scan is already in progress (session: {active['session_id']}). Wait for it to complete.",
            )
        session_id = str(uuid.uuid4())
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO security_scan_sessions (session_id, status, triggered_by, current_phase, phase_detail)
                   VALUES (%s, 'processing', %s, 'inventory', 'Initialising...')""",
                (session_id, actor["username"]),
            )
    finally:
        conn.close()

    bg_tasks.add_task(run_security_scan_background, session_id, actor["username"])
    return {"message": "Security scan started", "session_id": session_id}


@app.get("/security/sessions")
def list_security_sessions(
    limit: int = 20,
    actor: dict[str, Any] = Depends(require_permission("issues.read")),
):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT session_id, status, triggered_by, current_phase, phase_detail,
                          assets_count, dependencies_count, findings_count, critical_count, high_count,
                          tools_json, error_message, started_at, completed_at, created_at
                   FROM security_scan_sessions
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (min(limit, 50),),
            )
            rows = cur.fetchall()
        sessions = []
        for r in rows:
            item = {
                **r,
                "started_at": dt_to_str(r.get("started_at")),
                "completed_at": dt_to_str(r.get("completed_at")),
                "created_at": dt_to_str(r.get("created_at")),
                "tools": _json_loads_safe(r.get("tools_json"), []),
            }
            item.pop("tools_json", None)
            sessions.append(item)
        in_progress = any(s["status"] == "processing" for s in sessions)
    finally:
        conn.close()
    return {"sessions": sessions, "in_progress": in_progress}


@app.get("/security/sessions/{session_id}/progress")
def get_security_session_progress(
    session_id: str,
    actor: dict[str, Any] = Depends(require_permission("issues.read")),
):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT session_id, status, triggered_by, current_phase, phase_detail,
                          assets_count, dependencies_count, findings_count, critical_count, high_count,
                          tools_json, report_json, error_message, started_at, completed_at, created_at
                   FROM security_scan_sessions WHERE session_id = %s LIMIT 1""",
                (session_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    response = {
        **row,
        "started_at": dt_to_str(row.get("started_at")),
        "completed_at": dt_to_str(row.get("completed_at")),
        "created_at": dt_to_str(row.get("created_at")),
        "tools": _json_loads_safe(row.get("tools_json"), []),
        "report": _json_loads_safe(row.get("report_json"), None),
    }
    response.pop("tools_json", None)
    response.pop("report_json", None)
    return response


@app.get("/security/findings")
def list_security_findings(
    q: str | None = None,
    service_name: str | None = None,
    criticality: str | None = None,
    limit: int = 500,
    actor: dict[str, Any] = Depends(require_permission("issues.read")),
):
    conn = get_db()
    try:
        conditions = ["source = 'security_scanner'"]
        params: list[Any] = []
        if q:
            conditions.append("(description LIKE %s OR service_name LIKE %s OR request_id LIKE %s)")
            like = f"%{q}%"
            params += [like, like, like]
        if service_name:
            conditions.append("service_name = %s")
            params.append(service_name)
        if criticality:
            sev_map = {"critical": "cve_critical", "high": "cve_high", "medium": "cve_medium", "low": "cve_low"}
            mapped = sev_map.get(criticality.lower())
            if mapped:
                conditions.append("issue_type = %s")
                params.append(mapped)
        where = " AND ".join(conditions)
        params.append(min(limit, 1000))
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT id, fingerprint, service_name, issue_type, source, description,
                           stack_trace, entire_execution_logs, request_id, frequency,
                           first_seen, last_seen, status, created_at
                    FROM service_exception_log
                    WHERE {where}
                    ORDER BY FIELD(issue_type,'cve_critical','cve_high','cve_medium','cve_low'), last_seen DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
        items = []
        for r in rows:
            metadata = _json_loads_safe(r.get("entire_execution_logs"), {})
            item = {
                **r,
                "first_seen": dt_to_str(r.get("first_seen")),
                "last_seen": dt_to_str(r.get("last_seen")),
                "created_at": dt_to_str(r.get("created_at")),
                "severity": r["issue_type"].replace("cve_", "").upper() if r.get("issue_type", "").startswith("cve_") else "UNKNOWN",
                "cve_id": metadata.get("cve_id") or r.get("request_id", ""),
                "tool_name": metadata.get("tool_name") or metadata.get("source") or "unknown",
                "component": metadata.get("component") or "",
                "component_type": metadata.get("component_type") or "",
                "affected_version": metadata.get("affected_version") or "",
                "fixed_version": metadata.get("fixed_version") or "",
                "asset_type": metadata.get("asset_type") or "",
                "asset_id": metadata.get("asset_id") or "",
                "cvss_score": metadata.get("cvss_score"),
            }
            item.pop("entire_execution_logs", None)
            items.append(item)
    finally:
        conn.close()
    return {"items": items, "total": len(items)}


def _jira_issue_type_to_bug_daddy(jira_issue_type: str) -> str:
    mapping = {
        "Bug": "jira_bug",
        "Incident": "jira_incident",
        "Task": "jira_task",
        "Story": "jira_story",
        "Epic": "jira_epic",
        "Sub-task": "jira_subtask",
    }
    return mapping.get(jira_issue_type, "jira_issue")


@app.post("/webhooks/jira", status_code=200)
def jira_webhook(payload: dict[str, Any]):
    print("JIRA WEBHOOK PAYLOAD:", json.dumps(payload, default=str), flush=True)
    webhook_event = payload.get("webhookEvent", "")
    issue = payload.get("issue", {})
    issue_fields = issue.get("fields", {})

    if not issue:
        return {"status": "ignored", "reason": "no issue in payload"}

    jira_key = issue.get("key", "")
    jira_id = issue.get("id", "")
    summary = issue_fields.get("summary", "")
    description_raw = issue_fields.get("description") or ""
    if isinstance(description_raw, dict):
        # Jira doc format — flatten to plain text
        description_raw = json.dumps(description_raw)
    project = (issue_fields.get("project") or {}).get("name", "")
    jira_issue_type_name = (issue_fields.get("issuetype") or {}).get("name", "Bug")
    priority = (issue_fields.get("priority") or {}).get("name", "")
    reporter = (issue_fields.get("reporter") or {}).get("displayName", "")
    assignee_obj = issue_fields.get("assignee") or {}
    assignee = assignee_obj.get("displayName") or assignee_obj.get("emailAddress") or None
    jira_status = (issue_fields.get("status") or {}).get("name", "")
    environment = issue_fields.get("environment") or ""
    labels = issue_fields.get("labels") or []
    components = [c.get("name", "") for c in (issue_fields.get("components") or [])]
    stack_trace = issue_fields.get("customfield_10100") or ""  # adjust field id if needed

    service_name = project or "jira"
    issue_type = _jira_issue_type_to_bug_daddy(jira_issue_type_name)
    jira_url = f"{JIRA_BASE_URL}/browse/{jira_key}" if jira_key else None

    description_parts = [f"[{jira_key}] {summary}"]
    if priority:
        description_parts.append(f"Priority: {priority}")
    if reporter:
        description_parts.append(f"Reporter: {reporter}")
    if jira_status:
        description_parts.append(f"Jira Status: {jira_status}")
    if environment:
        description_parts.append(f"Environment: {environment}")
    if labels:
        description_parts.append(f"Labels: {', '.join(labels)}")
    if components:
        description_parts.append(f"Components: {', '.join(components)}")
    if description_raw:
        description_parts.append(f"\n{description_raw}")
    full_description = "\n".join(description_parts)

    fingerprint = hashlib.sha256(f"jira|{jira_key}".encode()).hexdigest()

    now = utc_now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM service_exception_log WHERE fingerprint = %s LIMIT 1",
                (fingerprint,),
            )
            existing = cur.fetchone()

            if existing:
                cur.execute(
                    """UPDATE service_exception_log
                       SET last_seen = %s, description = %s, stack_trace = %s,
                           assigned_to = %s, resolution_jira = %s, frequency = frequency + 1
                       WHERE id = %s""",
                    (now, full_description, stack_trace or None, assignee, jira_url, existing["id"]),
                )
                return {"status": "updated", "id": existing["id"], "jira_key": jira_key}
            else:
                cur.execute(
                    """INSERT INTO service_exception_log (
                           fingerprint, service_name, issue_type, source, description,
                           stack_trace, frequency, first_seen, last_seen, status,
                           assigned_to, resolution_jira, created_at
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        fingerprint, service_name, issue_type, "jira",
                        full_description, stack_trace or None,
                        1, now, now, "open",
                        assignee, jira_url, now,
                    ),
                )
                new_id = cur.lastrowid
                return {"status": "created", "id": new_id, "jira_key": jira_key}
    finally:
        conn.close()
