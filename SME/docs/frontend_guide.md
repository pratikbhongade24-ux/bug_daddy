# Frontend Guide (SME)

## Objective
Provide a production operational UI for managing loan lifecycle services with fast visual diagnostics.

## Key UX Components
- Health cards: per-service connectivity state
- KPI cards: operational metrics and backlog indicators
- Workflow pipeline: lifecycle stage visibility and completion %
- Action center: controlled operational workflow steps
- Full journey automation: single-click lifecycle execution
- Live event feed: timestamped JSON event stream

## Integration Strategy
- Frontend uses direct fetch calls to FastAPI microservice endpoints.
- Workflow actions enforce preconditions for realistic sequencing.
- Refresh cycle pulls aggregate counts from all services.

## Responsiveness and Visual System
- Desktop-first command center layout with mobile breakpoint at 1100px
- Layered gradients, glassmorphism cards, and motion for polished feel
- Color semantics mapped to status states (healthy, pending, overdue)
