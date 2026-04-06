# Platform Backend

FastAPI backend for the Bug Daddy platform control plane.

## Responsibilities

- Ingest and normalize triggers
- Persist issues, runs, events, and artifacts
- Invoke AgentCore runtimes or simulate them locally
- Stream live orchestration updates over WebSocket
- Serve dashboard, issue, trigger, and agent APIs for the frontend

## Run

```bash
cd platform/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Database

Production target is MySQL.

For quick local development, if `DATABASE_URL` is omitted the app falls back to
SQLite at `platform/backend/platform.db`.
