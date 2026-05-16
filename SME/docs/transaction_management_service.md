# Transaction Management Service

## Purpose
The Transaction Management service simulates production-like financial transfer workflows and intentionally injects controlled anomalies for BugDaddy detection and RCA demonstrations.

Base URL: `http://localhost:8005`

## Core Data Model
Schema: `transaction`
- `parties`: legal/account owners (Party A, Party B, etc.)
- `accounts`: account registry and balances
- `transfers`: transfer events and lifecycle status
- `ledger_entries`: debit/credit postings
- `settlement_records`: downstream settlement state
- `reconciliation_reports`: generated reconciliation summaries
- `reconciliation_mismatches`: mismatch-level findings
- `audit_logs`: trace-linked operational logs

## Intentional Anomaly Profiles
Supported `anomaly_profile` values for transfer creation:
- `incorrect_debit_credit_mapping`
- `duplicate_transaction`
- `missing_settlement`
- `reconciliation_mismatch`
- `delayed_posting`
- `wrong_beneficiary_transfer`

## API Contracts
### Health and Metrics
- `GET /health`
- `GET /metrics`
- `GET /observability/query-monitoring`

### Master Data
- `POST /parties`
- `POST /accounts`

### Transactions
- `POST /transactions/transfer`
- `GET /transactions`
- `GET /transactions/{transfer_id}`
- `POST /transactions/demo/bootstrap`
- `POST /transactions/demo/party-a-to-party-b-discrepancy`

### Reconciliation and Reports
- `POST /reconciliation/run`
- `GET /reconciliation/reports`
- `GET /reconciliation/reports/{report_id}`
- `GET /reconciliation/reports/{report_id}/analysis`

## Production Demo Mode (No Manual Setup)
The service now supports a production-safe demo bootstrap:
- On startup (default), it auto-seeds:
  - Demo Party A/B/C and accounts
  - 50 transfer records
  - only a few built-in anomalies (3-5)
- A logical API bug is intentionally enabled by default in transfer beneficiary routing for selected conditions.

### Key Demo Endpoints
- `POST /transactions/demo/seed` (idempotent seed to 50 records)
- `GET /demo/bug-status`
- `POST /demo/bug/fix`

## Demo Scenario (Party A -> Party B discrepancy)
1. Call `POST /transactions/demo/bootstrap` (safe to call repeatedly).
2. Call `POST /transactions/demo/seed` to ensure 50 baseline transactions with limited anomalies.
3. Run `POST /reconciliation/run`.
4. Fetch mismatch details and AI-style root-cause summary from:
   - `GET /reconciliation/reports/{report_id}`
   - `GET /reconciliation/reports/{report_id}/analysis`
5. Resolve the intentional logical bug by calling `POST /demo/bug/fix` (this is the simple BugDaddy agent action for demo).

## Observability and Tracing
- Every request emits `x-trace-id` and latency headers.
- DB query counts and slow query counters are tracked in-memory.
- Transaction audit events are written to `transaction.audit_logs` with trace IDs.

## BugDaddy Integration Guidance
- Use reconciliation mismatch payloads as anomaly inputs for BugDaddy incidents/issues.
- Route `reconciliation/reports/{id}/analysis` output into SME agent or Incident Daddy context.
- Map `mismatch_type`, `severity`, and `impacted_services` into existing issue severity and source conventions.
