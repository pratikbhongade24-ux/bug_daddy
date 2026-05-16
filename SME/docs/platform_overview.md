# SME Platform Documentation

## 1. Platform Summary
FinFlow is a microservice-based bank loan application platform designed for end-to-end lifecycle execution:
- Customer onboarding
- KYC submission and verification
- Loan application, approval, and disbursement
- EMI generation and repayment tracking

The platform is modular, schema-driven, and designed for production operations with RAG-based knowledge retrieval.

## 2. Architecture Overview
- Frontend: Single-page dashboard (`frontend/`) for operations and observability.
- Backend: Four FastAPI microservices (`backend/`) with bounded contexts.
- Data Layer: Shared PostgreSQL database `app` with domain schemas.
- Orchestration: `docker-compose.yml` for local deployment.

## 3. Service Topology
- Onboarding Service: `http://localhost:8001`
- KYC Service: `http://localhost:8002`
- Loan Service: `http://localhost:8003`
- Repayment Service: `http://localhost:8004`
- Transaction Management Service: `http://localhost:8005`
- PostgreSQL: `localhost:5432`

## 4. Database Design
Database name: `app`

Schemas:
- `onboarding`: customer master and eligibility snapshot
- `kyc`: KYC records and verification trail
- `loan`: loan applications and disbursement transactions
- `repayment`: EMI schedules and repayment transactions
- `transaction`: parties, accounts, transfers, settlement, reconciliation reports, and audit logs

Global design principles:
- Cross-schema foreign keys for referential integrity
- Indexed query paths for operational reads
- Enum-driven statuses for workflow predictability
- Audit columns (`created_at`, `updated_at`, `created_by`, `updated_by`) on each entity

## 5. End-to-End Workflow
1. Customer created in onboarding schema
2. KYC record submitted and moved to verified/rejected
3. Loan created for customer
4. Loan approved and disbursed with transaction record
5. EMI schedule generated from approved loan
6. Repayment entries linked to EMI rows

## 6. Frontend Capabilities
- Real-time service health checks
- KPI cards across business lifecycle
- Interactive quick actions
- Full journey automation button
- Visual workflow pipeline with progress tracking
- Activity feed with event payloads

## 7. Observability
- `/health` endpoint on each service for liveness checks
- Swagger docs per service for operational API validation
- Timeline logs in UI for operational workflow replay

## 8. Security and Compliance Notes
Current implementation should be continuously hardened for production:
- Enforce authN/authZ (JWT/OAuth2)
- Encrypt sensitive documents and PII
- Strengthen request validation and idempotency keys
- Add audit event immutability and centralized SIEM export

## 9. RAG-Friendly Retrieval Hints
For semantic retrieval, index by:
- Service domain (`onboarding`, `kyc`, `loan`, `repayment`)
- Endpoint names and payload contracts
- Status transitions and business rules
- Table definitions and constraints

## 10. Document Index
- `docs/platform_overview.md`
- `docs/database_reference.md`
- `docs/onboarding_service.md`
- `docs/kyc_service.md`
- `docs/loan_disbursement_service.md`
- `docs/repayment_service.md`
- `docs/frontend_guide.md`
- `docs/runbook.md`
- `docs/bugdaddy_production_guide.md`
- `docs/transaction_management_service.md`
