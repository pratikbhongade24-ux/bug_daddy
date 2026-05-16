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
from botocore.config import Config as BotocoreConfig
import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, EmailStr, Field

# --- DB connection pool ----------------------------------------------------
from microservices.db_pool import acquire, release

# Existing env vars ----------------------------------------------------------
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
# Helper models (unchanged) …
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# DB connection handling – now uses the lightweight pool
# ---------------------------------------------------------------------------

def get_db():
    """Return a pymysql connection drawn from the shared pool.
    The returned object's ``close()`` method is monkey‑patched to return the
    connection to the pool instead of actually closing the underlying socket.
    This allows existing ``finally: conn.close()`` patterns throughout the code
    to continue working without modification.
    """
    conn = acquire()
    # Preserve the original close in case we need to truly close (e.g., on shutdown)
    original_close = conn.close
    def pooled_close():
        # Return the connection to the pool for reuse
        release(conn)
    conn.close = pooled_close  # type: ignore[attr-defined]
    # Attach the original close for potential manual cleanup
    conn._original_close = original_close  # type: ignore[attr-defined]
    return conn

# ---------------------------------------------------------------------------
# Remaining helper functions (hashing, token handling, etc.) – unchanged
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# The rest of the file remains unchanged – all existing ``conn.close()`` calls
# will now return the connection to the pool, dramatically reducing the number
# of simultaneous TCP connections opened against the RDS Proxy.
# ---------------------------------------------------------------------------
