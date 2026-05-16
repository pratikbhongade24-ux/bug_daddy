# Runbook (SME)

## Startup
1. Ensure Docker Desktop engine is running.
2. Execute: `docker compose up`
3. Open UI: `http://localhost:8080`

## API Documentation
- Onboarding: `http://localhost:8001/docs`
- KYC: `http://localhost:8002/docs`
- Loan: `http://localhost:8003/docs`
- Repayment: `http://localhost:8004/docs`

## Smoke Test Path
1. Create customer
2. Upload KYC
3. Verify KYC
4. Create loan
5. Approve & disburse
6. Generate EMI

## Common Issues
- Docker daemon inaccessible: restart Docker Desktop.
- CORS/network errors: verify service ports and browser origin.
- Unique constraint conflicts: use randomized test email/phone values.

## Shutdown
- Stop stack: `docker compose down`
