import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException, status
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
        "resolved": "resolved",
        "no_action": "backlog",
    }.get(status, "backlog")


def map_issue(row: dict[str, Any]) -> dict[str, Any]:
    frequency = int(row.get("frequency") or 0)
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
        "criticality": issue_criticality(frequency),
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
    }


def fetch_issue_by_id(conn, issue_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, fingerprint, service_name, issue_type, source, description, stack_trace,
                   frequency, first_seen, last_seen, status, assigned_to, resolution_pr,
                   resolution_jira, created_at, resolved_at, entire_execution_logs, request_id
            FROM service_exception_log
            WHERE id = %s
            LIMIT 1
            """,
            (issue_id,),
        )
        row = cur.fetchone()
    return map_issue(row) if row else None


def ensure_schema_and_seed_data():
    conn = get_db()
    try:
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
                SELECT id, fingerprint, service_name, issue_type, source, description, stack_trace,
                       frequency, first_seen, last_seen, status, assigned_to, resolution_pr,
                       resolution_jira, created_at, resolved_at, entire_execution_logs, request_id
                FROM service_exception_log
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
                SELECT id, fingerprint, service_name, issue_type, source, description, stack_trace,
                       frequency, first_seen, last_seen, status, assigned_to, resolution_pr,
                       resolution_jira, created_at, resolved_at, entire_execution_logs, request_id
                FROM service_exception_log
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
