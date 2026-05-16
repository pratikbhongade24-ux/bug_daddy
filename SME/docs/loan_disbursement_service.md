# Loan Disbursement Service (SME)

## Purpose
Drive loan lifecycle from application through sanctioning and disbursement settlement.

## Base URL
`http://localhost:8003`

## Endpoints
- `GET /health`
- `POST /loans`: submit loan request
- `PATCH /loans/{loan_id}/approve`: approve with sanction details
- `POST /loans/{loan_id}/disburse`: create disbursement transaction
- `GET /loans`: list loans

## Business Controls
- Loan must reference a valid customer.
- Approval sets `approved_amount`, `interest_rate`, and notes.
- Disbursement marks loan status as `DISBURSED` and records transaction.

## Data Artifacts
- Primary: `loan.loan_applications`
- Secondary: `loan.disbursement_transactions`

## Suggested Extensions
- Multi-stage underwriting rules
- Risk engine integration
- Maker-checker authorization
- Idempotent disbursement keys
