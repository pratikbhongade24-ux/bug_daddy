from sqlalchemy import (
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
