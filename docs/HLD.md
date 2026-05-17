# Bug Daddy — High Level Design

## 1. Purpose

Bug Daddy is an autonomous AI-driven engineering operations platform. It ingests error signals from infrastructure and code-quality tooling, triages them through a multi-agent pipeline, and produces concrete remediation artefacts (GitHub PRs, Jira tickets, Slack notifications) with minimal human intervention.

---

## 2. System Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                          TRIGGER LAYER                                 │
│  kibana Logs  │  SonarQube (S3)  │  CVE Scanner  │  Manual / API  │
└────────┬──────────┴────────┬─────────┴───────┬────────┴───────┬────────┘
         │ Lambda            │ Lambda           │ Lambda         │ REST
         ▼                   ▼                  ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        PLATFORM BACKEND (FastAPI)                       │
│  ┌─────────────────────────┐   ┌──────────────────────────────────────┐ │
│  │  service_exception_log  │   │  ExecutionSession / ExecutionEvent   │ │
│  │  (MySQL — fingerprinted)│   │  (live streaming via SSE)            │ │
│  └─────────────────────────┘   └──────────────────────────────────────┘ │
│  ┌──────────────┐  ┌────────────┐  ┌─────────┐  ┌────────────────────┐ │
│  │  Auth / RBAC │  │  AI Queue  │  │  RAG    │  │  Sonar / Security  │ │
│  │  (JWT + PBKDF2)│ │  (SQS)    │  │ (pgvec) │  │  scan endpoints    │ │
│  └──────────────┘  └────────────┘  └─────────┘  └────────────────────┘ │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ Bedrock AgentCore invocation
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          AGENT LAYER (Bedrock AgentCore)               │
│                                                                        │
│  ┌──────────────┐   ┌─────────────┐   ┌────────────────┐              │
│  │ classifier   │ → │incident_daddy│ → │  bug_daddy     │              │
│  │              │   │              │   │                │              │
│  └──────────────┘   └─────────────┘   └────────┬───────┘              │
│                             ↑  SME queries      │                      │
│                      ┌──────┴──────┐            ▼                      │
│                      │  sme_agent  │   ┌────────────────┐              │
│                      └─────────────┘   │reviewer_daddy  │              │
│                                        └────────────────┘              │
│  ┌───────────────────────────────────────────┐                         │
│  │            feature_daddy                  │                         │
│  └───────────────────────────────────────────┘                         │
│                                                                        │
│  Internal Orchestrator (scheduler, router, circuit-breaker, recovery)  │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │ MCP tool calls
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
       GitHub              Jira (Atlassian)            Slack
    (read/write PRs)     (tickets + updates)      (notifications)
```

---

## 3. High-Level Components

### 3.1 Trigger Layer

Three families of triggers push raw signals into the platform. All triggers share the same persistence model: upsert into `service_exception_log` using a content-derived SHA-256 fingerprint for deduplication.

| Trigger | Source | Invocation |
|---------|--------|------------|
| **LogMonitoringBot** | kibana Logs | Lambda subscribed to log group via subscription filter |
| **SonarReportIngestor** | SonarQube JSON report | Lambda triggered by S3 PUT on report bucket |
| **SecurityScanner** | AWS assets (EC2, Lambda, RDS) + NVD/OSV CVE feeds | Scheduled Lambda orchestrator + ingestor Lambda |
| **Manual/API** | Platform UI or direct POST | REST endpoint on platform backend |

### 3.2 Platform Backend

A FastAPI service running on an EC2 instance (Uvicorn, port 8000). Responsibilities:

- **Issue lifecycle management** — CRUD over `service_exception_log`; status transitions (`open → in_progress → in_review → resolved`)
- **Authentication & RBAC** — JWT (access + refresh tokens), PBKDF2 password hashing, fine-grained permissions
- **AI Queue** — SQS-backed asynchronous agent invocation queue with configurable workers and polling
- **Execution tracking** — Receives streaming events from agents (node started/completed, tool executed, error); stores in `ExecutionSession` / `ExecutionEvent` tables; re-streams to frontend via SSE
- **Sonar integration** — Triggers SonarQube Lambda scans; presigns S3 report URLs
- **Security integration** — Triggers CVE scanner Lambda; surfaces findings
- **RAG subsystem** — Hybrid vector + keyword search over ingested engineering docs; streaming chat API backed by Bedrock embeddings + pgvector

### 3.3 Platform Frontend

A Next.js 16 (App Router) single-page application (port 3000). Views:

- **Issues** — Kanban-style backlog / WIP / review / resolved tabs; inline agent invocation; execution event timeline with DAG visualization
- **AI Queue** — Real-time queue depth and item status
- **Sonar** — Scan history and quality findings
- **Security** — CVE findings by severity
- **Admin** — User management, role permissions, audit logs
- **Grafana / Kibana** — Embedded monitoring and logging dashboards

### 3.4 Agent Layer

All agents run inside a single **Bedrock AgentCore** runtime (`claude-sonnet-4-6` equivalent — currently `qwen.qwen3-coder-480b-a35b-v1:0`). The runtime hosts agents in-process; handoffs between agents are local function calls (no inter-service HTTP in the default combined deployment).

| Agent | Primary Responsibility |
|-------|----------------------|
| **classifier** | Classify issue type; create initial Jira ticket |
| **incident_daddy** | Triage, severity assessment, Slack/Jira coordination, bug_daddy handoff |
| **sme_agent** | Subject-matter expertise — SOP retrieval, architectural guidance |
| **bug_daddy** | Root-cause analysis, code fix proposal, critic loop |
| **reviewer_daddy** | Final AI code review; PR creation or Jira-only closure |
| **feature_daddy** | PRD analysis → architecture design → implementation → PR |

### 3.5 MCP Tool Integrations

Agents call external services exclusively through Model Context Protocol (MCP) servers:

| MCP Server | Tools Exposed |
|-----------|---------------|
| **GitHub MCP** | Repo read, branch create, commit, push, PR create |
| **Jira MCP** | Create/update/assign/close tickets |
| **Slack MCP** | Post messages, thread replies |
| **Bitbucket MCP** | Repo read (alternative VCS) |

---

## 4. Key Data Flows

### 4.1 Error Ingestion (Trigger → Platform)

```
1. Error occurs in a microservice → kibana emits log event
2. LogMonitoringBot Lambda receives base64-gzipped log payload
3. Lambda classifies error, extracts full invocation log context
4. SHA-256 fingerprint computed from (service_name, issue_type, normalized_message)
5. Upsert to service_exception_log:
   - New: INSERT with status=open, frequency=1
   - Existing: UPDATE frequency++, last_seen, stack_trace
6. Platform dashboard reflects new/updated issue
```

### 4.2 Issue Remediation (Platform → Agents → Resolution)

```
1. Engineer clicks "Invoke AI" on an issue in the dashboard
2. Platform creates ExecutionSession, enqueues to SQS
3. SQS worker dequeues; platform invokes Bedrock AgentCore runtime
4. Runtime routes to classifier → incident_daddy (default path)

   incident_daddy pipeline:
   a. sme_agent query — get runbook/SOP context
   b. analyzer — extract facts, inferences, blast radius
   c. orchestrator — triage, post Slack summary, decide bug_daddy handoff
   d. report_writer — generate markdown incident report
   e. report_reviewer — validate report quality
   f. slack_notifier — post to #production_issue
   g. Jira update — create/update incident ticket

5. If handoff=true → bug_daddy pipeline:
   a. sme_agent query — remediation guidance
   b. context_analyzer — read logs + repo; identify root cause
   c. strategy_planner — emit remediation plan
      - If [RESOLUTION_TYPE: NON_CODE] tag present → skip to Jira-only closure
   d. critic — validate strategy
   e. coder — create branch (fix/<JIRA-KEY>), propose minimal fix
   f. critic — review code proposal
   g. → ReviewRequest to reviewer_daddy

6. reviewer_daddy:
   a. AI review of fix_proposal
   b. Disposition: pull_request | jira_ticket | rework_required
   c. If PR → create GitHub PR, emit PR URL to platform

7. At each step: ExecutionLogger POSTs event to platform callback URL
8. Platform stores events; SSE stream pushes to frontend
9. On resolution: issue.resolution_pr or resolution_jira updated
10. Issue status → resolved (or in_review pending human merge)
```

### 4.3 Feature Request Flow

```
1. Feature request surfaces (manual trigger or issue type=feature_request)
2. feature_daddy pipeline:
   prd_analyst → architect → implementer → critic → reviewer
3. reviewer creates PR; maps PR URL to issue
```

---

## 5. Cross-Cutting Concerns

### 5.1 Deduplication
Content-derived fingerprinting ensures that the same error appearing 10,000 times creates one record with `frequency=10000`, not 10,000 rows. Resolution of that one record resolves all recurrences.

### 5.2 SLA Tracking
Each incident carries `criticality` and `priority` which drive SLA KPIs:
- **SEV0/P0**: 60-second acknowledgement target
- **SEV1/P1**: 5-minute acknowledgement target
- **SEV2/P2**: 30-minute acknowledgement target
- **SEV3/P3**: 4-hour acknowledgement target
- **SEV4/P4**: 24-hour acknowledgement target

SLA breach flags are computed by `incident_daddy` and surfaced in `IncidentResponse.sla_kpis`.

### 5.3 Circuit Breaking & Recovery
The orchestrator layer wraps every agent invocation in a circuit breaker. On repeated failure, the breaker opens and routes to manual escalation. On partial success, the `RecoveryCoordinator` replays compensating actions in LIFO order.

### 5.4 Execution Observability
Every agent step emits a structured `ExecutionEvent` (type, agent_name, title, reasoning_summary, token counts, duration_ms). These events are stored in the platform DB and streamed to the frontend execution DAG view in real time.

### 5.5 Security
- All agent callbacks authenticated via `X-Agent-Execution-Secret` header
- Platform API secured with JWT; admin endpoints require `admin` role
- MCP server credentials sourced from environment (planned: AWS Secrets Manager)
- Passwords hashed with PBKDF2-HMAC-SHA256 (120k iterations)
- Audit log captures every mutation with user identity and IP

---

## 6. Deployment Topology

```
┌─────────────────────── EC2 (bugdaddy.in) ────────────────────────────┐
│                                                                       │
│  pm2 → Next.js frontend (:3000)                                       │
│  systemd → FastAPI backend (:8000, uvicorn)                           │
│  docker-compose → SME microservices (domain knowledge containers)     │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘

┌───────────── AWS Managed Services ────────────────────────────────────┐
│  RDS MySQL 8.0 — platform DB (service_exception_log, users, sessions) │
│  RDS PostgreSQL + pgvector — RAG vector store                         │
│  SQS — AI queue                                                       │
│  S3 — Sonar reports, security scan reports, Lambda deployment ZIPs    │
│  Bedrock AgentCore — agent runtime (ap-south-1)                       │
│  Lambda — LogMonitoringBot, SonarReportIngestor, SecurityScanner      │
└───────────────────────────────────────────────────────────────────────┘

┌──────────── External SaaS ────────────────────────────────────────────┐
│  Jira (bugdaddy.atlassian.net) — ticket management                    │
│  GitHub — source code, PRs                                            │
│  Slack — incident notifications                                        │
│  SonarQube — static analysis                                          │
│  NVD / OSV — CVE feeds                                                │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 7. Technology Stack Summary

| Layer | Technology |
|-------|-----------|
| Agent runtime | AWS Bedrock AgentCore, Strands SDK |
| Agent LLM | Qwen 3 Coder 480B (via Bedrock) |
| Agent tools | MCP (GitHub, Jira, Slack, Bitbucket) |
| Platform backend | FastAPI, Uvicorn, SQLAlchemy, PyMySQL |
| Platform DB | MySQL 8.0 (RDS) |
| RAG store | PostgreSQL + pgvector (RDS) |
| Queue | AWS SQS |
| Platform frontend | Next.js 16, React 19, TypeScript |
| Frontend state | TanStack Query |
| Charts | Recharts |
| Triggers | AWS Lambda (Python) |
| Deployment | EC2 + pm2 + systemd + Docker Compose |
| CI | GitHub Actions (Ruff, Mypy, pytest ≥70% coverage) |
