import hashlib
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

try:
    import pymysql
except ImportError:  # pragma: no cover - handled at runtime in lightweight local shells
    pymysql = None


SCHEMA_READY = False


MICRO_TABLE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS ms_service_registry (
      service_name VARCHAR(100) NOT NULL,
      bounded_context VARCHAR(100) NOT NULL,
      owner_team VARCHAR(100) NOT NULL,
      description TEXT NULL,
      capabilities JSON NULL,
      health_status VARCHAR(30) NOT NULL DEFAULT 'healthy',
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (service_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_customers (
      id BIGINT NOT NULL AUTO_INCREMENT,
      external_customer_id VARCHAR(100) NOT NULL,
      name VARCHAR(255) NULL,
      email VARCHAR(255) NULL,
      mobile_hash VARCHAR(64) NULL,
      mobile_last4 VARCHAR(4) NULL,
      pan_hash VARCHAR(64) NULL,
      pan_last4 VARCHAR(4) NULL,
      risk_band VARCHAR(20) NOT NULL DEFAULT 'B',
      source VARCHAR(50) NOT NULL DEFAULT 'web',
      onboarding_status VARCHAR(50) NOT NULL DEFAULT 'NEW',
      kyc_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
      profile_json JSON NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_customers_external (external_customer_id),
      KEY idx_ms_customers_status (onboarding_status, kyc_status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_onboarding_leads (
      id BIGINT NOT NULL AUTO_INCREMENT,
      lead_id VARCHAR(100) NOT NULL,
      customer_id BIGINT NOT NULL,
      source VARCHAR(50) NOT NULL DEFAULT 'web',
      stage VARCHAR(50) NOT NULL DEFAULT 'CREATED',
      assigned_service VARCHAR(100) NULL,
      risk_scores JSON NULL,
      documents_json JSON NULL,
      submitted_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_onboarding_leads_lead (lead_id),
      KEY idx_ms_onboarding_customer (customer_id),
      KEY idx_ms_onboarding_stage (stage)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_kyc_verifications (
      id BIGINT NOT NULL AUTO_INCREMENT,
      verification_id VARCHAR(100) NOT NULL,
      customer_id BIGINT NOT NULL,
      verification_type VARCHAR(50) NOT NULL,
      identifier_masked VARCHAR(100) NULL,
      status VARCHAR(50) NOT NULL,
      provider VARCHAR(100) NULL,
      score DECIMAL(8,4) NULL,
      review_mode VARCHAR(30) NULL,
      raw_payload JSON NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_kyc_verification (verification_id),
      KEY idx_ms_kyc_customer (customer_id),
      KEY idx_ms_kyc_type_status (verification_type, status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_bank_statements (
      id BIGINT NOT NULL AUTO_INCREMENT,
      statement_id VARCHAR(100) NOT NULL,
      customer_id BIGINT NULL,
      file_name VARCHAR(255) NULL,
      pages INT NOT NULL DEFAULT 0,
      status VARCHAR(50) NOT NULL DEFAULT 'UPLOADED',
      avg_monthly_credit DECIMAL(14,2) NULL,
      avg_monthly_debit DECIMAL(14,2) NULL,
      stability VARCHAR(50) NULL,
      raw_payload JSON NULL,
      uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_bank_statements_statement (statement_id),
      KEY idx_ms_bank_statements_customer (customer_id),
      KEY idx_ms_bank_statements_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_bank_statement_transactions (
      id BIGINT NOT NULL AUTO_INCREMENT,
      txn_id VARCHAR(120) NOT NULL,
      statement_id VARCHAR(100) NOT NULL,
      amount DECIMAL(14,2) NOT NULL,
      txn_type VARCHAR(20) NOT NULL,
      category VARCHAR(80) NULL,
      counterparty VARCHAR(255) NULL,
      txn_date DATE NULL,
      anomaly_flag BOOLEAN NOT NULL DEFAULT FALSE,
      anomaly_reason VARCHAR(255) NULL,
      raw_payload JSON NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_statement_txn (txn_id),
      KEY idx_ms_statement_txns_statement (statement_id),
      KEY idx_ms_statement_txns_anomaly (anomaly_flag)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_auto_debit_mandates (
      id BIGINT NOT NULL AUTO_INCREMENT,
      mandate_id VARCHAR(100) NOT NULL,
      customer_id BIGINT NULL,
      bank_code VARCHAR(50) NOT NULL,
      amount DECIMAL(14,2) NOT NULL DEFAULT 0,
      status VARCHAR(50) NOT NULL DEFAULT 'REGISTERED',
      retry_eligible BOOLEAN NOT NULL DEFAULT FALSE,
      last_execution_status VARCHAR(50) NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_auto_debit_mandate (mandate_id),
      KEY idx_ms_mandates_customer (customer_id),
      KEY idx_ms_mandates_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_auto_debit_executions (
      id BIGINT NOT NULL AUTO_INCREMENT,
      transaction_id VARCHAR(120) NOT NULL,
      mandate_id VARCHAR(100) NOT NULL,
      amount DECIMAL(14,2) NOT NULL,
      status VARCHAR(50) NOT NULL,
      scheduled_at DATETIME NULL,
      executed_at DATETIME NULL,
      raw_payload JSON NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_auto_debit_txn (transaction_id),
      KEY idx_ms_auto_debit_exec_mandate (mandate_id),
      KEY idx_ms_auto_debit_exec_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_disbursements (
      id BIGINT NOT NULL AUTO_INCREMENT,
      disbursement_id VARCHAR(100) NOT NULL,
      customer_id BIGINT NULL,
      amount DECIMAL(14,2) NOT NULL DEFAULT 0,
      destination_bank VARCHAR(100) NOT NULL,
      account_number_masked VARCHAR(100) NULL,
      ifsc VARCHAR(30) NULL,
      status VARCHAR(50) NOT NULL DEFAULT 'CREATED',
      utr VARCHAR(100) NULL,
      settlement_window VARCHAR(30) NULL,
      raw_payload JSON NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_disbursement (disbursement_id),
      KEY idx_ms_disbursement_customer (customer_id),
      KEY idx_ms_disbursement_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_support_tickets (
      id BIGINT NOT NULL AUTO_INCREMENT,
      ticket_id VARCHAR(100) NOT NULL,
      customer_id BIGINT NULL,
      priority VARCHAR(30) NOT NULL DEFAULT 'medium',
      assigned_queue VARCHAR(100) NOT NULL DEFAULT 'loan-ops',
      status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
      issue_summary TEXT NULL,
      resolution_code VARCHAR(100) NULL,
      comments_json JSON NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_ms_support_ticket (ticket_id),
      KEY idx_ms_support_customer (customer_id),
      KEY idx_ms_support_status (status),
      KEY idx_ms_support_queue (assigned_queue)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ms_service_events (
      id BIGINT NOT NULL AUTO_INCREMENT,
      service_name VARCHAR(100) NOT NULL,
      operation VARCHAR(100) NOT NULL,
      request_id VARCHAR(100) NOT NULL,
      trace_id VARCHAR(120) NULL,
      customer_id VARCHAR(100) NULL,
      entity_type VARCHAR(80) NULL,
      entity_id VARCHAR(120) NULL,
      status VARCHAR(30) NOT NULL DEFAULT 'SUCCESS',
      latency_ms INT NULL,
      payload_json JSON NULL,
      response_json JSON NULL,
      error_message TEXT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_ms_events_service_created (service_name, created_at),
      KEY idx_ms_events_request (request_id),
      KEY idx_ms_events_customer (customer_id),
      KEY idx_ms_events_entity (entity_type, entity_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


SERVICE_REGISTRY = {
    "CustomerOnboardingService": ("customer_onboarding", "loan-origination", ["validateCustomerProfile", "createLead", "submitOnboarding", "getOnboardingStatus", "getCustomer360"]),
    "KYCService": ("identity_verification", "risk-platform", ["verifyPan", "verifyAadhaar", "runFaceMatch", "getKycStatus", "getVerificationHistory"]),
    "BankStatementService": ("cashflow_underwriting", "risk-platform", ["uploadStatement", "extractTransactions", "summarizeCashflow", "detectAnomalies", "getStatementInsights"]),
    "AutoDebitService": ("repayment_mandates", "payments", ["registerMandate", "validateMandate", "executeDebit", "getMandateStatus", "getDebitHistory"]),
    "DisbursementService": ("loan_disbursement", "payments", ["createDisbursement", "validateAccount", "releaseFunds", "getDisbursementStatus", "getDisbursementLedger"]),
    "SupportService": ("customer_support", "customer-ops", ["createTicket", "assignTicket", "updateTicket", "getTicketStatus", "getTicketTimeline"]),
}


def db_metadata() -> dict[str, str | None]:
    return {
        "host": os.environ.get("DB_HOST"),
        "port": os.environ.get("DB_PORT", "3306"),
        "name": os.environ.get("DB_NAME"),
        "user": os.environ.get("DB_USER"),
    }


def connect_db():
    if pymysql is None:
        raise RuntimeError("pymysql is not installed; add microservices/requirements.txt to the Lambda package")
    required = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError(f"Missing database environment variable(s): {', '.join(missing)}")
    kwargs = {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
        "connect_timeout": 5,
    }
    try:
        return pymysql.connect(database=os.environ["DB_NAME"], **kwargs)
    except pymysql.err.OperationalError as exc:
        if not exc.args or exc.args[0] != 1049:
            raise
        db_name = os.environ["DB_NAME"]
        if not re.fullmatch(r"[A-Za-z0-9_]+", db_name):
            raise RuntimeError("DB_NAME may only contain letters, numbers, and underscores") from exc
        conn = pymysql.connect(**kwargs)
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
            cur.execute(f"USE `{db_name}`")
        return conn


def json_value(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), default=str)


def utc_sql() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def sha256_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def last4(value: Any) -> str | None:
    if value in (None, ""):
        return None
    cleaned = "".join(ch for ch in str(value) if ch.isalnum())
    return cleaned[-4:] if cleaned else None


def decimal_value(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except Exception:
        return Decimal(default)


def parse_json_columns(row: dict[str, Any] | None, *columns: str) -> dict[str, Any] | None:
    if not row:
        return row
    mapped = dict(row)
    for column in columns:
        if isinstance(mapped.get(column), str):
            try:
                mapped[column] = json.loads(mapped[column])
            except json.JSONDecodeError:
                pass
    for key, value in list(mapped.items()):
        if isinstance(value, datetime):
            mapped[key] = value.replace(tzinfo=timezone.utc).isoformat()
        elif isinstance(value, date):
            mapped[key] = value.isoformat()
        elif isinstance(value, Decimal):
            mapped[key] = float(value)
    return mapped


def normalize_rows(rows: list[dict[str, Any]], *json_columns: str) -> list[dict[str, Any]]:
    return [parse_json_columns(row, *json_columns) or {} for row in rows]


def ensure_schema(conn) -> None:
    global SCHEMA_READY
    if SCHEMA_READY:
        return
    with conn.cursor() as cur:
        for statement in MICRO_TABLE_SQL:
            cur.execute(statement)
        for service_name, (context, owner, capabilities) in SERVICE_REGISTRY.items():
            cur.execute(
                """
                INSERT INTO ms_service_registry
                  (service_name, bounded_context, owner_team, description, capabilities, health_status)
                VALUES (%s, %s, %s, %s, %s, 'healthy')
                ON DUPLICATE KEY UPDATE
                  bounded_context = VALUES(bounded_context),
                  owner_team = VALUES(owner_team),
                  capabilities = VALUES(capabilities),
                  health_status = VALUES(health_status)
                """,
                (
                    service_name,
                    context,
                    owner,
                    f"{service_name} owns the {context} bounded context.",
                    json_value(capabilities),
                ),
            )
    SCHEMA_READY = True


def customer_external_id(payload: dict[str, Any], response_payload: dict[str, Any] | None = None) -> str | None:
    response_payload = response_payload or {}
    profile = response_payload.get("profile") if isinstance(response_payload.get("profile"), dict) else {}
    return payload.get("customerId") or profile.get("customerId")


def ensure_customer(conn, payload: dict[str, Any], response_payload: dict[str, Any] | None = None) -> int | None:
    external_id = customer_external_id(payload, response_payload)
    if not external_id:
        return None
    response_payload = response_payload or {}
    profile = response_payload.get("profile") if isinstance(response_payload.get("profile"), dict) else {}
    name = payload.get("name") or profile.get("name")
    email = payload.get("email")
    risk_band = payload.get("riskBand") or profile.get("riskBand") or "B"
    source = payload.get("source") or profile.get("source") or "web"
    profile_json = {
        "payload": {key: value for key, value in payload.items() if key not in {"pan", "mobile", "aadhaar", "selfieImage"}},
        "profile": profile,
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ms_customers
              (external_customer_id, name, email, mobile_hash, mobile_last4, pan_hash, pan_last4,
               risk_band, source, profile_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              name = COALESCE(VALUES(name), name),
              email = COALESCE(VALUES(email), email),
              mobile_hash = COALESCE(VALUES(mobile_hash), mobile_hash),
              mobile_last4 = COALESCE(VALUES(mobile_last4), mobile_last4),
              pan_hash = COALESCE(VALUES(pan_hash), pan_hash),
              pan_last4 = COALESCE(VALUES(pan_last4), pan_last4),
              risk_band = VALUES(risk_band),
              source = VALUES(source),
              profile_json = VALUES(profile_json)
            """,
            (
                external_id,
                name,
                email,
                sha256_or_none(payload.get("mobile")),
                last4(payload.get("mobile")),
                sha256_or_none(payload.get("pan")),
                last4(payload.get("pan")),
                risk_band,
                source,
                json_value(profile_json),
            ),
        )
        cur.execute("SELECT id FROM ms_customers WHERE external_customer_id = %s", (external_id,))
        row = cur.fetchone()
    return int(row["id"]) if row else None


def update_customer_status(conn, customer_id: int | None, onboarding_status: str | None = None, kyc_status: str | None = None) -> None:
    if not customer_id:
        return
    fields: list[str] = []
    values: list[Any] = []
    if onboarding_status:
        fields.append("onboarding_status = %s")
        values.append(onboarding_status)
    if kyc_status:
        fields.append("kyc_status = %s")
        values.append(kyc_status)
    if not fields:
        return
    with conn.cursor() as cur:
        cur.execute(f"UPDATE ms_customers SET {', '.join(fields)} WHERE id = %s", (*values, customer_id))


def record_event(
    conn,
    *,
    service_name: str,
    operation: str,
    request_id: str,
    trace_id: str | None,
    payload: dict[str, Any],
    response_payload: dict[str, Any] | None,
    entity_type: str | None,
    entity_id: str | None,
    status: str,
    latency_ms: int | None,
    error_message: str | None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ms_service_events
              (service_name, operation, request_id, trace_id, customer_id, entity_type, entity_id,
               status, latency_ms, payload_json, response_json, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                service_name,
                operation,
                request_id,
                trace_id,
                payload.get("customerId"),
                entity_type,
                entity_id,
                status,
                latency_ms,
                json_value(payload),
                json_value(response_payload),
                error_message,
            ),
        )
        return int(cur.lastrowid)


def persist_operation(
    *,
    service_name: str,
    operation: str,
    request_id: str,
    trace_id: str | None,
    payload: dict[str, Any],
    response_payload: dict[str, Any] | None = None,
    status: str = "SUCCESS",
    error_message: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        conn = connect_db()
        try:
            ensure_schema(conn)
            dispatcher = DISPATCHERS.get((service_name, operation))
            entity = dispatcher(conn, payload, response_payload or {}) if dispatcher else {}
            latency_ms = int((time.perf_counter() - started) * 1000)
            event_id = record_event(
                conn,
                service_name=service_name,
                operation=operation,
                request_id=request_id,
                trace_id=trace_id,
                payload=payload,
                response_payload=response_payload,
                entity_type=entity.get("entity_type"),
                entity_id=entity.get("entity_id"),
                status=status,
                latency_ms=latency_ms,
                error_message=error_message,
            )
            return {
                "status": "written",
                "eventId": event_id,
                "latencyMs": latency_ms,
                "db": db_metadata(),
                **entity,
            }
        finally:
            conn.close()
    except Exception as exc:
        return {"status": "failed", "error": str(exc), "db": db_metadata()}


def persist_onboarding(conn, payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    operation = response_payload.get("operation_name")
    customer_id = ensure_customer(conn, payload, response_payload)
    external_id = customer_external_id(payload, response_payload)
    if operation == "validateCustomerProfile":
        update_customer_status(conn, customer_id, onboarding_status="PROFILE_VALIDATED")
        return {"entity_type": "customer", "entity_id": external_id, "tables": ["ms_customers"]}

    if operation == "createLead":
        lead = response_payload.get("lead") or {}
        lead_id = lead.get("leadId") or f"LEAD-{external_id or 'UNKNOWN'}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ms_onboarding_leads
                  (lead_id, customer_id, source, stage, assigned_service, risk_scores)
                VALUES (%s, %s, %s, %s, 'KYCService', %s)
                ON DUPLICATE KEY UPDATE
                  source = VALUES(source),
                  stage = VALUES(stage),
                  assigned_service = VALUES(assigned_service),
                  risk_scores = VALUES(risk_scores)
                """,
                (lead_id, customer_id, lead.get("source") or payload.get("source") or "web", lead.get("stage") or "CREATED", json_value(lead.get("scores"))),
            )
        update_customer_status(conn, customer_id, onboarding_status="LEAD_CREATED")
        return {"entity_type": "lead", "entity_id": lead_id, "tables": ["ms_customers", "ms_onboarding_leads"]}

    if operation == "submitOnboarding":
        lead_id = f"LEAD-{external_id or 'UNKNOWN'}"
        journey = response_payload.get("journey") or {}
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ms_onboarding_leads
                  (lead_id, customer_id, source, stage, assigned_service, documents_json, submitted_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  stage = VALUES(stage),
                  assigned_service = VALUES(assigned_service),
                  documents_json = VALUES(documents_json),
                  submitted_at = VALUES(submitted_at)
                """,
                (
                    lead_id,
                    customer_id,
                    payload.get("source") or "web",
                    journey.get("status") or "SUBMITTED",
                    journey.get("nextStep") or "KYCService",
                    json_value(journey.get("documentsReceived") or payload.get("documents") or []),
                    utc_sql(),
                ),
            )
        update_customer_status(conn, customer_id, onboarding_status="SUBMITTED")
        return {"entity_type": "lead", "entity_id": lead_id, "tables": ["ms_customers", "ms_onboarding_leads"]}

    if operation == "getOnboardingStatus":
        status_payload = response_payload.get("status") or {}
        update_customer_status(conn, customer_id, onboarding_status=status_payload.get("applicationStatus"))
    return {"entity_type": "customer", "entity_id": external_id, "tables": ["ms_customers"]}


def persist_kyc(conn, payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    operation = response_payload.get("operation_name")
    customer_id = ensure_customer(conn, payload, response_payload)
    external_id = customer_external_id(payload, response_payload)
    if operation == "verifyPan":
        verification = response_payload.get("verification") or {}
        return insert_kyc_verification(conn, customer_id, "PAN", last4(verification.get("pan") or payload.get("pan")), verification.get("status") or "VERIFIED", verification.get("provider"), None, None, payload)
    if operation == "verifyAadhaar":
        verification = response_payload.get("verification") or {}
        return insert_kyc_verification(conn, customer_id, "AADHAAR", verification.get("aadhaarMasked") or payload.get("aadhaarMasked"), verification.get("status") or "VERIFIED", "mock-aadhaar-registry", None, None, payload)
    if operation == "runFaceMatch":
        face = response_payload.get("faceMatch") or {}
        return insert_kyc_verification(conn, customer_id, "FACE_MATCH", None, face.get("result") or "MATCHED", "mock-face-match", face.get("score"), None, payload)
    if operation == "getKycStatus":
        status_payload = response_payload.get("status") or {}
        update_customer_status(conn, customer_id, kyc_status=status_payload.get("kycStatus"))
    return {"entity_type": "customer", "entity_id": external_id, "tables": ["ms_customers"]}


def insert_kyc_verification(
    conn,
    customer_id: int | None,
    verification_type: str,
    identifier_masked: str | None,
    status: str,
    provider: str | None,
    score: Any,
    review_mode: str | None,
    raw_payload: dict[str, Any],
) -> dict[str, Any]:
    if not customer_id:
        return {"entity_type": "kyc_verification", "entity_id": None, "tables": ["ms_kyc_verifications"]}
    verification_id = f"KYC-{verification_type}-{uuid.uuid4().hex[:16]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ms_kyc_verifications
              (verification_id, customer_id, verification_type, identifier_masked, status, provider, score, review_mode, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                verification_id,
                customer_id,
                verification_type,
                identifier_masked,
                status,
                provider,
                score,
                review_mode,
                json_value(raw_payload),
            ),
        )
    if status in {"VERIFIED", "MATCHED", "APPROVED"}:
        update_customer_status(conn, customer_id, kyc_status="APPROVED")
    return {"entity_type": "kyc_verification", "entity_id": verification_id, "tables": ["ms_customers", "ms_kyc_verifications"]}


def persist_bank_statement(conn, payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    operation = response_payload.get("operation_name")
    statement_id = payload.get("statementId") or (response_payload.get("upload") or {}).get("statementId") or "STM-001"
    customer_id = ensure_customer(conn, payload, response_payload)
    pages = int(payload.get("pages") or (response_payload.get("upload") or {}).get("pages") or 0)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ms_bank_statements
              (statement_id, customer_id, file_name, pages, status, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              customer_id = COALESCE(VALUES(customer_id), customer_id),
              file_name = COALESCE(VALUES(file_name), file_name),
              pages = GREATEST(pages, VALUES(pages)),
              status = VALUES(status),
              raw_payload = VALUES(raw_payload)
            """,
            (statement_id, customer_id, payload.get("fileName"), pages, "UPLOADED", json_value(payload)),
        )

    if operation in {"extractTransactions", "detectAnomalies"}:
        transactions = response_payload.get("transactions") or response_payload.get("anomalies") or []
        anomaly_ids = {item.get("txnId") for item in response_payload.get("anomalies", []) if isinstance(item, dict)}
        persist_statement_transactions(conn, statement_id, transactions, anomaly_ids)

    if operation == "summarizeCashflow":
        summary = response_payload.get("summary") or {}
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ms_bank_statements
                SET avg_monthly_credit = %s,
                    avg_monthly_debit = %s,
                    stability = %s,
                    status = 'SUMMARIZED'
                WHERE statement_id = %s
                """,
                (
                    decimal_value(summary.get("avgMonthlyCredit")),
                    decimal_value(summary.get("avgMonthlyDebit")),
                    summary.get("stability"),
                    statement_id,
                ),
            )
    return {"entity_type": "bank_statement", "entity_id": statement_id, "tables": ["ms_bank_statements", "ms_bank_statement_transactions"]}


def persist_statement_transactions(conn, statement_id: str, transactions: list[dict[str, Any]], anomaly_ids: set[str]) -> None:
    with conn.cursor() as cur:
        for item in transactions:
            if not isinstance(item, dict):
                continue
            source_txn_id = str(item.get("txnId") or uuid.uuid4().hex[:8])
            txn_id = f"{statement_id}-{source_txn_id}"
            txn_type = str(item.get("type") or "debit")
            amount = decimal_value(item.get("amount"))
            category = "income" if txn_type == "credit" and amount >= Decimal("1000") else "expense"
            anomaly_flag = bool(source_txn_id in anomaly_ids or amount > Decimal("2000"))
            anomaly_reason = "high_value_cashflow" if anomaly_flag else None
            cur.execute(
                """
                INSERT INTO ms_bank_statement_transactions
                  (txn_id, statement_id, amount, txn_type, category, counterparty, txn_date,
                   anomaly_flag, anomaly_reason, raw_payload)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  amount = VALUES(amount),
                  txn_type = VALUES(txn_type),
                  category = VALUES(category),
                  anomaly_flag = VALUES(anomaly_flag),
                  anomaly_reason = VALUES(anomaly_reason),
                  raw_payload = VALUES(raw_payload)
                """,
                (txn_id, statement_id, amount, txn_type, category, item.get("counterparty"), anomaly_flag, anomaly_reason, json_value(item)),
            )


def persist_auto_debit(conn, payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    operation = response_payload.get("operation_name")
    customer_id = ensure_customer(conn, payload, response_payload)
    mandate = response_payload.get("mandate") or response_payload.get("validation") or response_payload.get("status") or {}
    mandate_id = payload.get("mandateId") or mandate.get("mandateId") or "MANDATE-001"
    bank_code = payload.get("bankCode") or mandate.get("bankCode") or "MOCKBANK"
    amount = decimal_value(payload.get("amount") or mandate.get("amount"))
    status = mandate.get("status") or mandate.get("state") or "REGISTERED"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ms_auto_debit_mandates
              (mandate_id, customer_id, bank_code, amount, status, retry_eligible, last_execution_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              customer_id = COALESCE(VALUES(customer_id), customer_id),
              bank_code = VALUES(bank_code),
              amount = VALUES(amount),
              status = VALUES(status),
              retry_eligible = VALUES(retry_eligible),
              last_execution_status = COALESCE(VALUES(last_execution_status), last_execution_status)
            """,
            (mandate_id, customer_id, bank_code, amount, status, bool(mandate.get("retryEligible", False)), mandate.get("lastExecution")),
        )
    if operation == "executeDebit":
        debit = response_payload.get("debit") or {}
        transaction_id = debit.get("transactionId") or payload.get("transactionId") or f"DEBIT-{uuid.uuid4().hex[:8]}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ms_auto_debit_executions
                  (transaction_id, mandate_id, amount, status, scheduled_at, raw_payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  amount = VALUES(amount),
                  status = VALUES(status),
                  raw_payload = VALUES(raw_payload)
                """,
                (transaction_id, mandate_id, decimal_value(debit.get("amount") or payload.get("amount")), debit.get("status") or "SCHEDULED", utc_sql(), json_value(payload)),
            )
        return {"entity_type": "auto_debit_execution", "entity_id": transaction_id, "tables": ["ms_auto_debit_mandates", "ms_auto_debit_executions"]}
    return {"entity_type": "mandate", "entity_id": mandate_id, "tables": ["ms_auto_debit_mandates"]}


def persist_disbursement(conn, payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    disbursement = response_payload.get("disbursement") or response_payload.get("release") or response_payload.get("status") or {}
    validation = response_payload.get("accountValidation") or {}
    customer_id = ensure_customer(conn, payload, response_payload)
    disbursement_id = payload.get("disbursementId") or disbursement.get("disbursementId") or "DISB-001"
    status = disbursement.get("status") or disbursement.get("state") or ("ACCOUNT_VERIFIED" if validation else "CREATED")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ms_disbursements
              (disbursement_id, customer_id, amount, destination_bank, account_number_masked,
               ifsc, status, utr, settlement_window, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              customer_id = COALESCE(VALUES(customer_id), customer_id),
              amount = GREATEST(amount, VALUES(amount)),
              destination_bank = VALUES(destination_bank),
              account_number_masked = COALESCE(VALUES(account_number_masked), account_number_masked),
              ifsc = COALESCE(VALUES(ifsc), ifsc),
              status = VALUES(status),
              utr = COALESCE(VALUES(utr), utr),
              settlement_window = COALESCE(VALUES(settlement_window), settlement_window),
              raw_payload = VALUES(raw_payload)
            """,
            (
                disbursement_id,
                customer_id,
                decimal_value(payload.get("amount") or disbursement.get("amount")),
                payload.get("destinationBank") or disbursement.get("destination") or "MOCKBANK",
                validation.get("accountNumberMasked") or payload.get("accountNumberMasked"),
                payload.get("ifsc"),
                status,
                disbursement.get("utr") or payload.get("utr"),
                disbursement.get("settlementWindow"),
                json_value(payload),
            ),
        )
    return {"entity_type": "disbursement", "entity_id": disbursement_id, "tables": ["ms_disbursements"]}


def persist_support(conn, payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    ticket = response_payload.get("ticket") or response_payload.get("assignment") or response_payload.get("update") or response_payload.get("status") or {}
    customer_id = ensure_customer(conn, payload, response_payload)
    ticket_id = payload.get("ticketId") or ticket.get("ticketId") or "SUP-001"
    status = ticket.get("status") or ticket.get("currentState") or payload.get("status") or "OPEN"
    comments = payload.get("comments")
    if comments is None and ticket.get("resolutionCode"):
        comments = [f"Resolution: {ticket.get('resolutionCode')}"]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ms_support_tickets
              (ticket_id, customer_id, priority, assigned_queue, status, issue_summary, resolution_code, comments_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              customer_id = COALESCE(VALUES(customer_id), customer_id),
              priority = VALUES(priority),
              assigned_queue = VALUES(assigned_queue),
              status = VALUES(status),
              issue_summary = COALESCE(VALUES(issue_summary), issue_summary),
              resolution_code = COALESCE(VALUES(resolution_code), resolution_code),
              comments_json = COALESCE(VALUES(comments_json), comments_json)
            """,
            (
                ticket_id,
                customer_id,
                payload.get("priority") or ticket.get("priority") or "medium",
                payload.get("assignedQueue") or ticket.get("assignedQueue") or "loan-ops",
                status,
                payload.get("issue"),
                ticket.get("resolutionCode"),
                json_value(comments),
            ),
        )
    return {"entity_type": "support_ticket", "entity_id": ticket_id, "tables": ["ms_support_tickets"]}


def with_operation_name(operation: str, fn: Callable[[Any, dict[str, Any], dict[str, Any]], dict[str, Any]]):
    def wrapped(conn, payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
        return fn(conn, payload, {**response_payload, "operation_name": operation})

    return wrapped


DISPATCHERS = {
    ("CustomerOnboardingService", "validateCustomerProfile"): with_operation_name("validateCustomerProfile", persist_onboarding),
    ("CustomerOnboardingService", "createLead"): with_operation_name("createLead", persist_onboarding),
    ("CustomerOnboardingService", "submitOnboarding"): with_operation_name("submitOnboarding", persist_onboarding),
    ("CustomerOnboardingService", "getOnboardingStatus"): with_operation_name("getOnboardingStatus", persist_onboarding),
    ("KYCService", "verifyPan"): with_operation_name("verifyPan", persist_kyc),
    ("KYCService", "verifyAadhaar"): with_operation_name("verifyAadhaar", persist_kyc),
    ("KYCService", "runFaceMatch"): with_operation_name("runFaceMatch", persist_kyc),
    ("KYCService", "getKycStatus"): with_operation_name("getKycStatus", persist_kyc),
    ("BankStatementService", "uploadStatement"): with_operation_name("uploadStatement", persist_bank_statement),
    ("BankStatementService", "extractTransactions"): with_operation_name("extractTransactions", persist_bank_statement),
    ("BankStatementService", "summarizeCashflow"): with_operation_name("summarizeCashflow", persist_bank_statement),
    ("BankStatementService", "detectAnomalies"): with_operation_name("detectAnomalies", persist_bank_statement),
    ("AutoDebitService", "registerMandate"): with_operation_name("registerMandate", persist_auto_debit),
    ("AutoDebitService", "validateMandate"): with_operation_name("validateMandate", persist_auto_debit),
    ("AutoDebitService", "executeDebit"): with_operation_name("executeDebit", persist_auto_debit),
    ("AutoDebitService", "getMandateStatus"): with_operation_name("getMandateStatus", persist_auto_debit),
    ("DisbursementService", "createDisbursement"): with_operation_name("createDisbursement", persist_disbursement),
    ("DisbursementService", "validateAccount"): with_operation_name("validateAccount", persist_disbursement),
    ("DisbursementService", "releaseFunds"): with_operation_name("releaseFunds", persist_disbursement),
    ("DisbursementService", "getDisbursementStatus"): with_operation_name("getDisbursementStatus", persist_disbursement),
    ("SupportService", "createTicket"): with_operation_name("createTicket", persist_support),
    ("SupportService", "assignTicket"): with_operation_name("assignTicket", persist_support),
    ("SupportService", "updateTicket"): with_operation_name("updateTicket", persist_support),
    ("SupportService", "getTicketStatus"): with_operation_name("getTicketStatus", persist_support),
}


def safe_read(read_fn: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    try:
        conn = connect_db()
        try:
            ensure_schema(conn)
            return {"persistence": {"status": "read", "db": db_metadata()}, **read_fn(conn)}
        finally:
            conn.close()
    except Exception as exc:
        return {"persistence": {"status": "failed", "error": str(exc), "db": db_metadata()}}


def read_customer_360(customer_id: str | None) -> dict[str, Any]:
    def _read(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ms_customers WHERE external_customer_id = %s", (customer_id,))
            customer = parse_json_columns(cur.fetchone(), "profile_json")
            if not customer:
                return {"customer": None, "leads": [], "kyc": [], "statements": [], "mandates": [], "disbursements": [], "tickets": []}
            cur.execute("SELECT * FROM ms_onboarding_leads WHERE customer_id = %s ORDER BY updated_at DESC", (customer["id"],))
            leads = normalize_rows(cur.fetchall(), "risk_scores", "documents_json")
            cur.execute("SELECT * FROM ms_kyc_verifications WHERE customer_id = %s ORDER BY created_at DESC", (customer["id"],))
            kyc = normalize_rows(cur.fetchall(), "raw_payload")
            cur.execute("SELECT * FROM ms_bank_statements WHERE customer_id = %s ORDER BY updated_at DESC", (customer["id"],))
            statements = normalize_rows(cur.fetchall(), "raw_payload")
            cur.execute("SELECT * FROM ms_auto_debit_mandates WHERE customer_id = %s ORDER BY updated_at DESC", (customer["id"],))
            mandates = normalize_rows(cur.fetchall())
            cur.execute("SELECT * FROM ms_disbursements WHERE customer_id = %s ORDER BY updated_at DESC", (customer["id"],))
            disbursements = normalize_rows(cur.fetchall(), "raw_payload")
            cur.execute("SELECT * FROM ms_support_tickets WHERE customer_id = %s ORDER BY updated_at DESC", (customer["id"],))
            tickets = normalize_rows(cur.fetchall(), "comments_json")
        return {
            "customer": customer,
            "leads": leads,
            "kyc": kyc,
            "statements": statements,
            "mandates": mandates,
            "disbursements": disbursements,
            "tickets": tickets,
        }

    return safe_read(_read)


def read_verification_history(customer_id: str | None) -> dict[str, Any]:
    def _read(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM ms_customers WHERE external_customer_id = %s", (customer_id,))
            customer = cur.fetchone()
            if not customer:
                return {"items": []}
            cur.execute("SELECT * FROM ms_kyc_verifications WHERE customer_id = %s ORDER BY created_at DESC", (customer["id"],))
            return {"items": normalize_rows(cur.fetchall(), "raw_payload")}

    return safe_read(_read)


def read_statement_insights(statement_id: str | None) -> dict[str, Any]:
    def _read(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ms_bank_statements WHERE statement_id = %s", (statement_id,))
            statement = parse_json_columns(cur.fetchone(), "raw_payload")
            cur.execute("SELECT * FROM ms_bank_statement_transactions WHERE statement_id = %s ORDER BY txn_date DESC, id DESC", (statement_id,))
            transactions = normalize_rows(cur.fetchall(), "raw_payload")
        return {
            "statement": statement,
            "transactions": transactions,
            "anomalyCount": sum(1 for item in transactions if item.get("anomaly_flag")),
            "creditTotal": sum(float(item.get("amount") or 0) for item in transactions if item.get("txn_type") == "credit"),
            "debitTotal": sum(float(item.get("amount") or 0) for item in transactions if item.get("txn_type") == "debit"),
        }

    return safe_read(_read)


def read_debit_history(mandate_id: str | None) -> dict[str, Any]:
    def _read(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ms_auto_debit_mandates WHERE mandate_id = %s", (mandate_id,))
            mandate = parse_json_columns(cur.fetchone())
            cur.execute("SELECT * FROM ms_auto_debit_executions WHERE mandate_id = %s ORDER BY created_at DESC", (mandate_id,))
            executions = normalize_rows(cur.fetchall(), "raw_payload")
        return {"mandate": mandate, "executions": executions}

    return safe_read(_read)


def read_disbursement_ledger(disbursement_id: str | None) -> dict[str, Any]:
    def _read(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ms_disbursements WHERE disbursement_id = %s", (disbursement_id,))
            row = parse_json_columns(cur.fetchone(), "raw_payload")
        return {"disbursement": row}

    return safe_read(_read)


def read_ticket_timeline(ticket_id: str | None) -> dict[str, Any]:
    def _read(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ms_support_tickets WHERE ticket_id = %s", (ticket_id,))
            ticket = parse_json_columns(cur.fetchone(), "comments_json")
            cur.execute(
                """
                SELECT operation, status, payload_json, response_json, error_message, created_at
                FROM ms_service_events
                WHERE entity_type = 'support_ticket' AND entity_id = %s
                ORDER BY created_at ASC
                """,
                (ticket_id,),
            )
            events = normalize_rows(cur.fetchall(), "payload_json", "response_json")
        return {"ticket": ticket, "events": events}

    return safe_read(_read)
