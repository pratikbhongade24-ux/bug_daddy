# Database Reference (SME)

## Logical Model

### onboarding.customers
Purpose: canonical customer profile and initial eligibility metadata.
Key columns: `id`, `customer_ref`, `full_name`, `email`, `phone`, `dob`, `employment_type`, `annual_income`, `credit_score`, `eligibility_status`.
Constraints: unique (`customer_ref`, `email`, `phone`).
Indexes: email, phone.

### kyc.kyc_records
Purpose: track submitted identity documents and verification status.
Key columns: `id`, `customer_id`, `document_type`, `document_number`, `document_url`, `status`, `reviewer_notes`.
Foreign key: `customer_id -> onboarding.customers.id`.
Indexes: `customer_id`, `status`.

### loan.loan_applications
Purpose: capture loan request and sanctioning lifecycle.
Key columns: `id`, `loan_ref`, `customer_id`, `loan_type`, `requested_amount`, `approved_amount`, `interest_rate`, `tenure_months`, `status`, `sanction_notes`.
Constraints: `requested_amount > 0`, unique `loan_ref`.
Foreign key: `customer_id -> onboarding.customers.id`.
Indexes: `customer_id`, `status`.

### loan.disbursement_transactions
Purpose: disbursement event trail and payout reference tracking.
Key columns: `id`, `loan_id`, `txn_ref`, `disbursed_amount`, `disbursed_on`, `mode`, `status`.
Foreign key: `loan_id -> loan.loan_applications.id`.
Indexes: `loan_id`, unique `txn_ref`.

### repayment.emi_schedules
Purpose: EMI due plan and payment state progression.
Key columns: `id`, `loan_id`, `installment_no`, `due_date`, `principal_component`, `interest_component`, `total_due`, `paid_amount`, `payment_status`.
Foreign key: `loan_id -> loan.loan_applications.id`.
Indexes: composite (`loan_id`, `due_date`).

### repayment.repayment_transactions
Purpose: payment ledger against EMI rows.
Key columns: `id`, `emi_id`, `payment_ref`, `paid_on`, `paid_amount`, `channel`.
Foreign key: `emi_id -> repayment.emi_schedules.id`.
Indexes: `emi_id`, unique `payment_ref`.

## Audit Fields
Every table includes:
- `created_at`
- `updated_at`
- `created_by`
- `updated_by`

These fields support traceability, lineage reconstruction, and compliance reporting.

## Status Enums
- Eligibility: `PENDING`, `ELIGIBLE`, `REVIEW`, `REJECTED`
- KYC: `UPLOADED`, `UNDER_REVIEW`, `VERIFIED`, `REJECTED`
- Loan: `SUBMITTED`, `APPROVED`, `REJECTED`, `DISBURSED`
- Disbursement: `INITIATED`, `SUCCESS`, `FAILED`
- EMI: `DUE`, `PAID`, `OVERDUE`

## Data Integrity Patterns
- Cascade delete used where child lifecycle strictly depends on parent entity.
- Restrict delete on customer-loan relationship to prevent orphan financial records.
- Operational indexes align with dashboard and API query paths.
