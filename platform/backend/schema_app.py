import json
from typing import Any


BASE_TABLE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS roles (
      id INT NOT NULL AUTO_INCREMENT,
      name VARCHAR(100) NOT NULL,
      description VARCHAR(255) NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_roles_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS permissions (
      id INT NOT NULL AUTO_INCREMENT,
      permission_key VARCHAR(150) NOT NULL,
      description VARCHAR(255) NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_permissions_key (permission_key)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS role_permissions (
      role_id INT NOT NULL,
      permission_id INT NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (role_id, permission_id),
      KEY idx_role_permissions_permission (permission_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
      id CHAR(36) NOT NULL,
      username VARCHAR(100) NULL,
      email VARCHAR(255) NOT NULL,
      password_hash VARCHAR(255) NOT NULL,
      full_name VARCHAR(255) NULL,
      role_id INT NOT NULL,
      status VARCHAR(30) NOT NULL DEFAULT 'active',
      is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
      last_login_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_users_email (email),
      UNIQUE KEY uq_users_username (username),
      KEY idx_users_role (role_id),
      KEY idx_users_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
      id CHAR(36) NOT NULL,
      user_id CHAR(36) NOT NULL,
      refresh_token_hash VARCHAR(255) NOT NULL,
      expires_at DATETIME NOT NULL,
      revoked_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_user_sessions_token (refresh_token_hash),
      KEY idx_user_sessions_user (user_id),
      KEY idx_user_sessions_expiry (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
      id CHAR(36) NOT NULL,
      user_id CHAR(36) NOT NULL,
      token_hash VARCHAR(255) NOT NULL,
      expires_at DATETIME NOT NULL,
      used_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_password_reset_token (token_hash),
      KEY idx_password_reset_user (user_id),
      KEY idx_password_reset_expiry (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
      id BIGINT NOT NULL AUTO_INCREMENT,
      user_id CHAR(36) NULL,
      action VARCHAR(150) NOT NULL,
      entity_type VARCHAR(100) NULL,
      entity_id VARCHAR(255) NULL,
      metadata JSON NULL,
      ip_address VARCHAR(64) NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_audit_user (user_id),
      KEY idx_audit_action (action),
      KEY idx_audit_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS service_exception_log (
      id BIGINT NOT NULL AUTO_INCREMENT,
      fingerprint VARCHAR(255) NOT NULL,
      service_name VARCHAR(255) NOT NULL,
      issue_type VARCHAR(255) NOT NULL,
      source VARCHAR(64) NOT NULL COMMENT 'cloudwatch / sonarqube / cve / techdebt',
      description TEXT NULL,
      stack_trace LONGTEXT NULL,
      entire_execution_logs LONGTEXT NULL,
      request_id VARCHAR(255) NULL,
      frequency BIGINT NOT NULL DEFAULT 1,
      first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      last_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      status VARCHAR(64) NOT NULL DEFAULT 'open' COMMENT 'open / in_progress / in_review / resolved / no_action',
      assigned_to VARCHAR(255) NULL,
      resolution_pr VARCHAR(255) NULL,
      resolution_jira VARCHAR(255) NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      resolved_at DATETIME NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uq_service_exception_fingerprint (fingerprint),
      KEY idx_fingerprint (fingerprint),
      KEY idx_service_name (service_name),
      KEY idx_status (status),
      KEY idx_source (source),
      KEY idx_last_seen (last_seen)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


MICROSERVICE_TABLE_SQL = [
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


MICROSERVICE_TABLES = [
    "ms_service_registry",
    "ms_customers",
    "ms_onboarding_leads",
    "ms_kyc_verifications",
    "ms_bank_statements",
    "ms_bank_statement_transactions",
    "ms_auto_debit_mandates",
    "ms_auto_debit_executions",
    "ms_disbursements",
    "ms_support_tickets",
    "ms_service_events",
]


PERMISSIONS = {
    "issues.read": "Read issue dashboard data",
    "issues.update": "Update, assign, prioritize, and resolve issues",
    "users.read": "Read users and administrative status",
    "users.create": "Create users",
    "users.update": "Update users and admin settings",
    "users.delete": "Deactivate users",
    "roles.read": "Read roles and permissions",
    "roles.update": "Update role permissions",
    "audit.read": "Read audit logs",
}


SERVICE_REGISTRY = [
    {
        "service_name": "CustomerOnboardingService",
        "bounded_context": "customer_onboarding",
        "owner_team": "loan-origination",
        "description": "Validates customer profiles, computes lead risk signals, and manages onboarding journey status.",
        "capabilities": ["validateCustomerProfile", "createLead", "submitOnboarding", "getOnboardingStatus", "getCustomer360"],
    },
    {
        "service_name": "KYCService",
        "bounded_context": "identity_verification",
        "owner_team": "risk-platform",
        "description": "Runs PAN, Aadhaar, and face-match verification and stores verification evidence.",
        "capabilities": ["verifyPan", "verifyAadhaar", "runFaceMatch", "getKycStatus", "getVerificationHistory"],
    },
    {
        "service_name": "BankStatementService",
        "bounded_context": "cashflow_underwriting",
        "owner_team": "risk-platform",
        "description": "Stores uploaded bank statements, extracted transactions, cashflow summaries, and statement anomalies.",
        "capabilities": ["uploadStatement", "extractTransactions", "summarizeCashflow", "detectAnomalies", "getStatementInsights"],
    },
    {
        "service_name": "AutoDebitService",
        "bounded_context": "repayment_mandates",
        "owner_team": "payments",
        "description": "Registers mandates, validates them, and schedules debit executions.",
        "capabilities": ["registerMandate", "validateMandate", "executeDebit", "getMandateStatus", "getDebitHistory"],
    },
    {
        "service_name": "DisbursementService",
        "bounded_context": "loan_disbursement",
        "owner_team": "payments",
        "description": "Creates loan disbursements, validates beneficiary accounts, and tracks release status.",
        "capabilities": ["createDisbursement", "validateAccount", "releaseFunds", "getDisbursementStatus", "getDisbursementLedger"],
    },
    {
        "service_name": "SupportService",
        "bounded_context": "customer_support",
        "owner_team": "customer-ops",
        "description": "Creates, assigns, updates, and resolves customer support tickets linked to the loan journey.",
        "capabilities": ["createTicket", "assignTicket", "updateTicket", "getTicketStatus", "getTicketTimeline"],
    },
]


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), default=str)


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"SHOW COLUMNS FROM {table} LIKE %s", (column,))
    return cur.fetchone() is not None


def _index_exists(cur, table: str, index_name: str) -> bool:
    cur.execute(f"SHOW INDEX FROM {table} WHERE Key_name = %s", (index_name,))
    return cur.fetchone() is not None


def _add_column_if_missing(cur, table: str, column: str, definition: str) -> None:
    if not _column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _add_index_if_missing(cur, table: str, index_name: str, definition: str) -> None:
    if not _index_exists(cur, table, index_name):
        cur.execute(f"ALTER TABLE {table} ADD {definition}")


def ensure_core_schema(conn) -> None:
    with conn.cursor() as cur:
        for statement in BASE_TABLE_SQL + MICROSERVICE_TABLE_SQL:
            cur.execute(statement)

        _add_column_if_missing(cur, "users", "username", "VARCHAR(100) NULL AFTER id")
        _add_index_if_missing(cur, "users", "uq_users_username", "UNIQUE KEY uq_users_username (username)")

        _add_column_if_missing(cur, "service_exception_log", "entire_execution_logs", "LONGTEXT NULL AFTER stack_trace")
        _add_column_if_missing(cur, "service_exception_log", "request_id", "VARCHAR(255) NULL AFTER entire_execution_logs")


def seed_core_data(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO roles (name, description)
            VALUES ('admin', 'Full platform administrator'), ('user', 'Operational dashboard user')
            ON DUPLICATE KEY UPDATE description = VALUES(description)
            """
        )
        for permission_key, description in PERMISSIONS.items():
            cur.execute(
                """
                INSERT INTO permissions (permission_key, description)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE description = VALUES(description)
                """,
                (permission_key, description),
            )

        cur.execute("SELECT id FROM roles WHERE name = 'admin'")
        admin_role_id = int(cur.fetchone()["id"])
        cur.execute("SELECT id FROM roles WHERE name = 'user'")
        user_role_id = int(cur.fetchone()["id"])
        cur.execute("SELECT id, permission_key FROM permissions")
        permission_rows = cur.fetchall()
        for row in permission_rows:
            cur.execute(
                """
                INSERT IGNORE INTO role_permissions (role_id, permission_id)
                VALUES (%s, %s)
                """,
                (admin_role_id, row["id"]),
            )
            if row["permission_key"] in {"issues.read", "issues.update"}:
                cur.execute(
                    """
                    INSERT IGNORE INTO role_permissions (role_id, permission_id)
                    VALUES (%s, %s)
                    """,
                    (user_role_id, row["id"]),
                )

        for service in SERVICE_REGISTRY:
            cur.execute(
                """
                INSERT INTO ms_service_registry
                  (service_name, bounded_context, owner_team, description, capabilities, health_status)
                VALUES (%s, %s, %s, %s, %s, 'healthy')
                ON DUPLICATE KEY UPDATE
                  bounded_context = VALUES(bounded_context),
                  owner_team = VALUES(owner_team),
                  description = VALUES(description),
                  capabilities = VALUES(capabilities),
                  health_status = VALUES(health_status)
                """,
                (
                    service["service_name"],
                    service["bounded_context"],
                    service["owner_team"],
                    service["description"],
                    _json(service["capabilities"]),
                ),
            )

        demo_customers = [
            ("CUST-1001", "Asha Mehta", "asha@example.com", "B", "web", "SUBMITTED", "APPROVED", {"segment": "prime", "city": "Pune"}),
            ("CUST-1002", "Rohan Iyer", "rohan@example.com", "A", "partner", "IN_REVIEW", "PENDING", {"segment": "salaried", "city": "Bengaluru"}),
            ("CUST-9001", "Demo Regression", "demo@example.com", "C", "qa", "ESCALATED", "REVIEW", {"segment": "demo", "city": "Mumbai"}),
        ]
        for customer in demo_customers:
            cur.execute(
                """
                INSERT INTO ms_customers
                  (external_customer_id, name, email, risk_band, source, onboarding_status, kyc_status, profile_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  name = VALUES(name),
                  email = VALUES(email),
                  risk_band = VALUES(risk_band),
                  source = VALUES(source),
                  onboarding_status = VALUES(onboarding_status),
                  kyc_status = VALUES(kyc_status),
                  profile_json = VALUES(profile_json)
                """,
                (
                    customer[0],
                    customer[1],
                    customer[2],
                    customer[3],
                    customer[4],
                    customer[5],
                    customer[6],
                    _json(customer[7]),
                ),
            )

        cur.execute("SELECT id, external_customer_id FROM ms_customers WHERE external_customer_id IN ('CUST-1001', 'CUST-1002', 'CUST-9001')")
        customer_ids = {row["external_customer_id"]: row["id"] for row in cur.fetchall()}

        seed_leads = [
            ("LEAD-CUST-1001", customer_ids.get("CUST-1001"), "web", "SUBMITTED", "KYCService", {"kycScore": 91, "fraudScore": 8, "bureauScore": 768}, ["pan", "bank_statement"]),
            ("LEAD-CUST-1002", customer_ids.get("CUST-1002"), "partner", "CREATED", "KYCService", {"kycScore": 74, "fraudScore": 16, "bureauScore": 711}, ["pan"]),
        ]
        for lead in seed_leads:
            if not lead[1]:
                continue
            cur.execute(
                """
                INSERT INTO ms_onboarding_leads
                  (lead_id, customer_id, source, stage, assigned_service, risk_scores, documents_json, submitted_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE
                  stage = VALUES(stage),
                  assigned_service = VALUES(assigned_service),
                  risk_scores = VALUES(risk_scores),
                  documents_json = VALUES(documents_json)
                """,
                (lead[0], lead[1], lead[2], lead[3], lead[4], _json(lead[5]), _json(lead[6])),
            )

        if customer_ids.get("CUST-1001"):
            cur.execute(
                """
                INSERT INTO ms_bank_statements
                  (statement_id, customer_id, file_name, pages, status, avg_monthly_credit, avg_monthly_debit, stability, raw_payload)
                VALUES ('STM-CUST-1001', %s, 'asha-march-statement.pdf', 3, 'SUMMARIZED', 4000.00, 480.00, 'GOOD', %s)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status),
                  avg_monthly_credit = VALUES(avg_monthly_credit),
                  avg_monthly_debit = VALUES(avg_monthly_debit),
                  stability = VALUES(stability)
                """,
                (customer_ids["CUST-1001"], _json({"seeded": True})),
            )
            cur.execute(
                """
                INSERT INTO ms_support_tickets
                  (ticket_id, customer_id, priority, assigned_queue, status, issue_summary, resolution_code, comments_json)
                VALUES ('SUP-CUST-1001', %s, 'medium', 'loan-ops', 'OPEN', 'Customer requested disbursement ETA', NULL, %s)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status),
                  assigned_queue = VALUES(assigned_queue),
                  comments_json = VALUES(comments_json)
                """,
                (customer_ids["CUST-1001"], _json(["Seeded ticket for demo workflow"])),
            )


def schema_status(conn) -> dict[str, Any]:
    table_names = [
        "roles",
        "permissions",
        "users",
        "service_exception_log",
        *MICROSERVICE_TABLES,
    ]
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for table_name in table_names:
            try:
                cur.execute(f"SELECT COUNT(*) AS total FROM {table_name}")
                counts[table_name] = int(cur.fetchone()["total"])
            except Exception:
                counts[table_name] = -1

        cur.execute(
            """
            SELECT service_name, bounded_context, owner_team, health_status, capabilities, updated_at
            FROM ms_service_registry
            ORDER BY service_name
            """
        )
        services = cur.fetchall()

    for service in services:
        if isinstance(service.get("capabilities"), str):
            try:
                service["capabilities"] = json.loads(service["capabilities"])
            except json.JSONDecodeError:
                pass
    return {"tables": counts, "services": services}
