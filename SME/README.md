# Bank Loan Application Testing Platform

Production-style microservice testing platform for complete bank loan lifecycle validation.

## Components
- Frontend command center: modern interactive dashboard (`frontend/`)
- FastAPI microservices:
  - Customer Onboarding (`8001`)
  - KYC Service (`8002`)
  - Loan Disbursement (`8003`)
  - Repayment Service (`8004`)
- PostgreSQL database: `app`

## Quick Start
```bash
docker compose up
```

Frontend:
- `http://localhost:8080`

Swagger docs:
- `http://localhost:8001/docs`
- `http://localhost:8002/docs`
- `http://localhost:8003/docs`
- `http://localhost:8004/docs`

## Database Design
Schemas:
- `onboarding`
- `kyc`
- `loan`
- `repayment`

Model definitions:
- `backend/shared/models/entities.py`

## SME Documentation (RAG Ready)
- `docs/platform_overview.md`
- `docs/database_reference.md`
- `docs/onboarding_service.md`
- `docs/kyc_service.md`
- `docs/loan_disbursement_service.md`
- `docs/repayment_service.md`
- `docs/frontend_guide.md`
- `docs/runbook.md`
