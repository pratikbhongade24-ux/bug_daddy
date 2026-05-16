# KYC Service (SME)

## Purpose
Capture and verify customer identity artifacts with explicit workflow status.

## Base URL
`http://localhost:8002`

## Endpoints
- `GET /health`
- `POST /kyc`: create KYC record in `UNDER_REVIEW`
- `PATCH /kyc/{kyc_id}`: update status and reviewer notes
- `GET /kyc`: list KYC records

## Workflow States
- Intake: `UPLOADED` or `UNDER_REVIEW`
- Decision: `VERIFIED` or `REJECTED`

## Integrity Constraints
- KYC cannot be created without existing `customer_id`.
- Customer linkage enforced via cross-schema foreign key.

## Operational Guidance
- Extend with document hash, OCR confidence, and fraud checks for production hardening.
