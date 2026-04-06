# Platform

`platform/` is the control plane for the Bug Daddy hackathon demo.

## Structure

- [`frontend`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend): Next.js operator UI
- [`backend`](/Users/danishgada/vscode/personal/bug_daddy/platform/backend): FastAPI orchestration backend and APIs

## What It Covers

- Trigger ingestion and scenario simulation
- Issue, run, event, and artifact persistence
- Realtime orchestration updates over WebSocket
- AgentCore runtime invocation from the backend
- Dashboard UI for triggers, issues, agent health, reasoning, and evidence

## Local Run

Backend:

```bash
cd platform/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Frontend:

```bash
cd platform/frontend
npm install
cp .env.local.example .env.local
npm run dev
```

## Deployment Direction

- Host `frontend` on Vercel or EC2
- Host `backend` on EC2 with FastAPI + Uvicorn
- Use MySQL in production
- Point backend env vars at the deployed AgentCore runtime ARNs for:
  - `incident_daddy`
  - `bug_daddy`
  - `reviewer_daddy`
  - `sme_agent`

## Deploy Scripts

The repo now includes EC2 deploy helpers under [`scripts`](/Users/danishgada/vscode/personal/bug_daddy/platform/scripts):

```bash
cd platform
./scripts/deploy-backend.sh
./scripts/deploy-frontend.sh
./scripts/deploy-all.sh
```

Defaults are set for the current environment:

- host: `ubuntu@3.109.87.158`
- ssh key: `~/.ssh/bug-daddy-key.pem`
- remote root: `/home/ubuntu/bug_daddy/platform`

You can override them with env vars:

```bash
DEPLOY_HOST=ubuntu@3.109.87.158 SSH_KEY=~/.ssh/bug-daddy-key.pem ./scripts/deploy-all.sh
```
