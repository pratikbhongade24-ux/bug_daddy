import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

import boto3
from botocore.config import Config as BotocoreConfig
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
SECURITY_SCANNER_AWS_REGION = os.getenv("SECURITY_SCANNER_AWS_REGION", AWS_REGION)
SECURITY_SCANNER_ACCESS_KEY_ID = os.getenv("SECURITY_SCANNER_ACCESS_KEY_ID")
SECURITY_SCANNER_SECRET_ACCESS_KEY = os.getenv("SECURITY_SCANNER_SECRET_ACCESS_KEY")

app = FastAPI(title="Bug Daddy API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Database connection handling
# ---------------------------------------------------------------------------
# A single pymysql connection is reused for the lifetime of the Lambda container.
# The connection object's ``close`` method is overridden with a no‑op so that
# existing ``finally: conn.close()`` patterns become harmless and do not actually
# terminate the shared socket. This dramatically reduces the number of TCP
# connections opened against the RDS Proxy, preventing pool exhaustion.

_db_conn: Optional[pymysql.connections.Connection] = None

def get_db():
    """Return a singleton MySQL connection.

    The connection is lazily created on first use and reused for subsequent
    calls within the same container. ``close`` is monkey‑patched to a no‑op so
    that legacy ``conn.close()`` calls do not close the shared connection.
    """
    global _db_conn
    if _db_conn is None or not getattr(_db_conn, "open", False):
        _db_conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=10,
        )
        # Override ``close`` to keep the connection alive for the container.
        def _noop_close():
            pass
        _db_conn.close = _noop_close  # type: ignore[attr-defined]
    return _db_conn

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
        # ``close`` is a no‑op; retained for backward compatibility.
        conn.close()

def require_permission(permission_key: str):
    def checker(user: dict[str, Any] = Depends(require_auth)):
        if permission_key not in user["permissions"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker

# ... (rest of the file remains unchanged) ...
