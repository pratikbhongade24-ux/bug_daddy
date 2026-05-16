from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import relationship
from backend.shared.db.database import Base


class AuditMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(100), nullable=False, server_default="system")
    updated_by = Column(String(100), nullable=False, server_default="system")


class Customer(Base, AuditMixin):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_email", "email"),
        Index("ix_customers_phone", "phone"),
        {"schema": "onboarding"},
    )

    id = Column(Integer, primary_key=True)
    customer_ref = Column(String(30), unique=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    dob = Column(Date, nullable=False)
    employment_type = Column(String(50), nullable=False)
    annual_income = Column(Numeric(12, 2), nullable=False)
    credit_score = Column(Integer, nullable=False)
    eligibility_status = Column(
        Enum("PENDING", "ELIGIBLE", "REVIEW", "REJECTED", name="eligibility_status_enum"),
        nullable=False,
        server_default="PENDING",
    )

    kyc_records = relationship("KYCRecord", back_populates="customer")
    loans = relationship("LoanApplication", back_populates="customer")


class KYCRecord(Base, AuditMixin):
    __tablename__ = "kyc_records"
    __table_args__ = (
        Index("ix_kyc_customer_id", "customer_id"),
        Index("ix_kyc_status", "status"),
        {"schema": "kyc"},
    )

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("onboarding.customers.id", ondelete="CASCADE"), nullable=False)
    document_type = Column(
        Enum("AADHAAR", "PAN", "PASSPORT", "DRIVING_LICENSE", name="doc_type_enum"),
        nullable=False,
    )
    document_number = Column(String(50), nullable=False)
    document_url = Column(Text, nullable=False)
    status = Column(
        Enum("UPLOADED", "UNDER_REVIEW", "VERIFIED", "REJECTED", name="kyc_status_enum"),
        nullable=False,
        server_default="UPLOADED",
    )
    reviewer_notes = Column(Text, nullable=True)

    customer = relationship("Customer", back_populates="kyc_records")


class LoanApplication(Base, AuditMixin):
    __tablename__ = "loan_applications"
    __table_args__ = (
        Index("ix_loan_customer_id", "customer_id"),
        Index("ix_loan_status", "status"),
        CheckConstraint("requested_amount > 0", name="ck_requested_amount_positive"),
        {"schema": "loan"},
    )

    id = Column(Integer, primary_key=True)
    loan_ref = Column(String(40), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("onboarding.customers.id", ondelete="RESTRICT"), nullable=False)
    loan_type = Column(String(40), nullable=False)
    requested_amount = Column(Numeric(12, 2), nullable=False)
    approved_amount = Column(Numeric(12, 2), nullable=True)
    interest_rate = Column(Numeric(5, 2), nullable=True)
    tenure_months = Column(Integer, nullable=False)
    status = Column(
        Enum("SUBMITTED", "APPROVED", "REJECTED", "DISBURSED", name="loan_status_enum"),
        nullable=False,
        server_default="SUBMITTED",
    )
    sanction_notes = Column(Text, nullable=True)

    customer = relationship("Customer", back_populates="loans")
    disbursements = relationship("DisbursementTransaction", back_populates="loan")
    emis = relationship("EMISchedule", back_populates="loan")


class DisbursementTransaction(Base, AuditMixin):
    __tablename__ = "disbursement_transactions"
    __table_args__ = (
        Index("ix_disbursement_loan_id", "loan_id"),
        Index("ix_disbursement_txn_ref", "txn_ref", unique=True),
        {"schema": "loan"},
    )

    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loan.loan_applications.id", ondelete="CASCADE"), nullable=False)
    txn_ref = Column(String(50), nullable=False)
    disbursed_amount = Column(Numeric(12, 2), nullable=False)
    disbursed_on = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    mode = Column(String(30), nullable=False)
    status = Column(
        Enum("INITIATED", "SUCCESS", "FAILED", name="disbursement_status_enum"),
        nullable=False,
        server_default="INITIATED",
    )

    loan = relationship("LoanApplication", back_populates="disbursements")


class EMISchedule(Base, AuditMixin):
    __tablename__ = "emi_schedules"
    __table_args__ = (
        Index("ix_emi_loan_due_date", "loan_id", "due_date"),
        {"schema": "repayment"},
    )

    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loan.loan_applications.id", ondelete="CASCADE"), nullable=False)
    installment_no = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)
    principal_component = Column(Numeric(12, 2), nullable=False)
    interest_component = Column(Numeric(12, 2), nullable=False)
    total_due = Column(Numeric(12, 2), nullable=False)
    paid_amount = Column(Numeric(12, 2), nullable=False, server_default="0")
    payment_status = Column(
        Enum("DUE", "PAID", "OVERDUE", name="emi_status_enum"),
        nullable=False,
        server_default="DUE",
    )

    loan = relationship("LoanApplication", back_populates="emis")
    repayments = relationship("RepaymentTransaction", back_populates="emi")


class RepaymentTransaction(Base, AuditMixin):
    __tablename__ = "repayment_transactions"
    __table_args__ = (
        Index("ix_repayment_emi_id", "emi_id"),
        Index("ix_repayment_txn_ref", "payment_ref", unique=True),
        {"schema": "repayment"},
    )

    id = Column(Integer, primary_key=True)
    emi_id = Column(Integer, ForeignKey("repayment.emi_schedules.id", ondelete="CASCADE"), nullable=False)
    payment_ref = Column(String(50), nullable=False)
    paid_on = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    paid_amount = Column(Numeric(12, 2), nullable=False)
    channel = Column(String(30), nullable=False)

    emi = relationship("EMISchedule", back_populates="repayments")


class TransactionParty(Base, AuditMixin):
    __tablename__ = "parties"
    __table_args__ = (
        Index("ix_tx_parties_code", "party_code", unique=True),
        {"schema": "transaction"},
    )

    id = Column(Integer, primary_key=True)
    party_code = Column(String(40), nullable=False)
    party_name = Column(String(120), nullable=False)
    party_type = Column(
        Enum("INDIVIDUAL", "BUSINESS", "INTERNAL", name="tx_party_type_enum"),
        nullable=False,
        server_default="INDIVIDUAL",
    )
    status = Column(
        Enum("ACTIVE", "INACTIVE", "BLOCKED", name="tx_party_status_enum"),
        nullable=False,
        server_default="ACTIVE",
    )


class TransactionAccount(Base, AuditMixin):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("ix_tx_accounts_number", "account_number", unique=True),
        Index("ix_tx_accounts_party", "party_id"),
        {"schema": "transaction"},
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("transaction.parties.id", ondelete="RESTRICT"), nullable=False)
    account_number = Column(String(40), nullable=False)
    account_type = Column(
        Enum("SAVINGS", "CURRENT", "SETTLEMENT", "NODAL", name="tx_account_type_enum"),
        nullable=False,
        server_default="SAVINGS",
    )
    currency = Column(String(10), nullable=False, server_default="INR")
    available_balance = Column(Numeric(14, 2), nullable=False, server_default="0")
    ledger_balance = Column(Numeric(14, 2), nullable=False, server_default="0")
    status = Column(
        Enum("ACTIVE", "DORMANT", "FROZEN", name="tx_account_status_enum"),
        nullable=False,
        server_default="ACTIVE",
    )


class TransferTransaction(Base, AuditMixin):
    __tablename__ = "transfers"
    __table_args__ = (
        Index("ix_tx_transfers_ref", "transfer_ref", unique=True),
        Index("ix_tx_transfers_status", "status"),
        {"schema": "transaction"},
    )

    id = Column(Integer, primary_key=True)
    transfer_ref = Column(String(60), nullable=False)
    source_account_id = Column(Integer, ForeignKey("transaction.accounts.id", ondelete="RESTRICT"), nullable=False)
    beneficiary_account_id = Column(Integer, ForeignKey("transaction.accounts.id", ondelete="RESTRICT"), nullable=False)
    intended_beneficiary_account_id = Column(Integer, ForeignKey("transaction.accounts.id", ondelete="RESTRICT"), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    fee_amount = Column(Numeric(14, 2), nullable=False, server_default="0")
    status = Column(
        Enum("INITIATED", "POSTED", "SETTLED", "FAILED", "POSTING_DELAYED", name="tx_transfer_status_enum"),
        nullable=False,
        server_default="INITIATED",
    )
    initiated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    posted_at = Column(DateTime(timezone=True), nullable=True)
    settled_at = Column(DateTime(timezone=True), nullable=True)
    anomaly_flags = Column(Text, nullable=True)
    external_ref = Column(String(80), nullable=True)
    parent_transfer_id = Column(Integer, ForeignKey("transaction.transfers.id", ondelete="SET NULL"), nullable=True)


class LedgerEntry(Base, AuditMixin):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_tx_ledger_transfer", "transfer_id"),
        Index("ix_tx_ledger_account", "account_id"),
        {"schema": "transaction"},
    )

    id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey("transaction.transfers.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("transaction.accounts.id", ondelete="RESTRICT"), nullable=False)
    entry_type = Column(Enum("DEBIT", "CREDIT", name="tx_entry_type_enum"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    running_balance = Column(Numeric(14, 2), nullable=True)
    source_system = Column(String(30), nullable=False, server_default="core_ledger")
    posting_status = Column(
        Enum("POSTED", "PENDING", "FAILED", name="tx_posting_status_enum"),
        nullable=False,
        server_default="POSTED",
    )
    trace_id = Column(String(100), nullable=True)


class SettlementRecord(Base, AuditMixin):
    __tablename__ = "settlement_records"
    __table_args__ = (
        Index("ix_tx_settle_transfer", "transfer_id", unique=True),
        {"schema": "transaction"},
    )

    id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey("transaction.transfers.id", ondelete="CASCADE"), nullable=False)
    expected_amount = Column(Numeric(14, 2), nullable=False)
    settled_amount = Column(Numeric(14, 2), nullable=False, server_default="0")
    settlement_status = Column(
        Enum("PENDING", "SETTLED", "MISMATCH", "MISSING", name="tx_settlement_status_enum"),
        nullable=False,
        server_default="PENDING",
    )
    settlement_system = Column(String(30), nullable=False, server_default="payment_switch")
    settled_at = Column(DateTime(timezone=True), nullable=True)


class ReconciliationReport(Base, AuditMixin):
    __tablename__ = "reconciliation_reports"
    __table_args__ = (
        Index("ix_tx_recon_generated", "generated_at"),
        {"schema": "transaction"},
    )

    id = Column(Integer, primary_key=True)
    report_ref = Column(String(60), nullable=False, unique=True)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        Enum("COMPLETED", "FAILED", "PARTIAL", name="tx_recon_status_enum"),
        nullable=False,
        server_default="COMPLETED",
    )
    generated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    total_transfers = Column(Integer, nullable=False, server_default="0")
    mismatch_count = Column(Integer, nullable=False, server_default="0")
    missing_settlement_count = Column(Integer, nullable=False, server_default="0")
    duplicate_count = Column(Integer, nullable=False, server_default="0")
    analysis_summary = Column(Text, nullable=True)


class ReconciliationMismatch(Base, AuditMixin):
    __tablename__ = "reconciliation_mismatches"
    __table_args__ = (
        Index("ix_tx_recon_mismatch_report", "report_id"),
        Index("ix_tx_recon_mismatch_type", "mismatch_type"),
        {"schema": "transaction"},
    )

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("transaction.reconciliation_reports.id", ondelete="CASCADE"), nullable=False)
    transfer_id = Column(Integer, ForeignKey("transaction.transfers.id", ondelete="SET NULL"), nullable=True)
    mismatch_type = Column(
        Enum(
            "WRONG_BENEFICIARY",
            "DUPLICATE",
            "MISSING_SETTLEMENT",
            "AMOUNT_MISMATCH",
            "DELAYED_POSTING",
            "DEBIT_CREDIT_SWAP",
            name="tx_mismatch_type_enum",
        ),
        nullable=False,
    )
    severity = Column(
        Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="tx_severity_enum"),
        nullable=False,
        server_default="MEDIUM",
    )
    details = Column(Text, nullable=False)
    impacted_services = Column(Text, nullable=True)
    root_cause_hint = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, server_default="false")


class TransactionAuditLog(Base, AuditMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_tx_audit_trace", "trace_id"),
        Index("ix_tx_audit_action", "action"),
        {"schema": "transaction"},
    )

    id = Column(Integer, primary_key=True)
    trace_id = Column(String(100), nullable=True)
    action = Column(String(80), nullable=False)
    actor = Column(String(80), nullable=False, server_default="system")
    entity_type = Column(String(80), nullable=False)
    entity_id = Column(String(80), nullable=True)
    status = Column(String(30), nullable=False, server_default="success")
    details = Column(Text, nullable=True)
