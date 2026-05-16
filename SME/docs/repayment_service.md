# Repayment Service (SME)

## Purpose
Manage EMI schedules, capture repayments, and detect overdue obligations.

## Base URL
`http://localhost:8004`

## Endpoints
- `GET /health`
- `POST /emis/generate`: generate full EMI schedule from approved loan
- `POST /repayments`: post repayment against EMI row
- `GET /emis`: list EMI schedules and mark overdue where applicable

## Business Logic
- EMI generation requires approved loan amount.
- Existing schedule is protected from duplicate regeneration.
- Payment status transitions to `PAID` when cumulative paid amount reaches total due.
- EMI due date in past with unpaid status becomes `OVERDUE`.

## Data Artifacts
- `repayment.emi_schedules`
- `repayment.repayment_transactions`
