# Bug Daddy — Low Level Design

## 1. Agents Layer

### 1.1 Directory Structure

```
agents/
├── apps/
│   └── bug_daddy/
│       └── main.py                  # BedrockAgentCoreApp entrypoint
├── src/agentic_solution/
│   ├── agents.py                    # Agent bundle builders
│   ├── config.py                    # AppConfig from environment
│   ├── contracts.py                 # Pydantic request/response schemas
│   ├── execution.py                 # ExecutionLogger (callback to platform)
│   ├── heuristics.py                # Pure-function classifiers (severity, NON_CODE tag)
│   ├── mcp.py                       # MCPToolBundle (GitHub, Jira, Slack, Bitbucket)
│   ├── prompts.py                   # System prompts for every agent role
│   ├── secrets.py                   # Typed secrets loader (env → AWS Secrets Manager ready)
│   ├── services/
│   │   ├── incident.py              # IncidentDaddyRuntime
│   │   ├── bug.py                   # BugDaddyRuntime
│   │   ├── reviewer.py              # ReviewerDaddyRuntime
│   │   ├── sme.py                   # SMEAgentRuntime
│   │   ├── classifier.py            # ClassifierRuntime
│   │   ├── feature.py               # FeatureDaddyRuntime
│   │   └── combined.py              # CombinedBugDaddyRuntime (router)
│   └── orchestrator/
│       ├── contracts.py             # RawTrigger, NormalizedEvent, RemediationPlan, AgentOutcome
│       ├── ingestion.py             # IngestionGate (dedup, journal)
│       ├── normalization.py         # EventNormalizer (enrichment, severity scoring)
│       ├── scheduler.py             # PriorityScheduler (weighted-fair queue)
│       ├── routing/
│       │   ├── router.py            # RoutingEngine (incident class → agent mapping)
│       │   └── registry.py          # AgentRegistry (capabilities, health, concurrency limits)
│       ├── runtime/
│       │   ├── executor.py          # AgentExecutor (retry, timeout)
│       │   ├── circuit_breaker.py   # Breaker (open/closed/half-open state machine)
│       │   ├── recovery.py          # RecoveryCoordinator (LIFO compensation replay)
│       │   └── supervisor.py        # RemediationSupervisor (multi-agent DAG orchestration)
│       └── observability/
│           ├── audit.py             # AuditJournal (durable event log)
│           ├── logging.py           # StructuredLogger (JSON)
│           └── metrics.py           # MetricsCollector (latency, success, cost)
└── tests/                           # 125+ unit and integration tests
```

---

### 1.2 Configuration — `config.py`

**`AppConfig`** (loaded once at startup from environment):

```python
aws_region:           str   # env AWS_REGION | AWS_DEFAULT_REGION | boto3 session | "us-west-2"
bedrock_model_id:     str   # env BEDROCK_MODEL_ID, default "qwen.qwen3-coder-480b-a35b-v1:0"
dry_run:              bool  # env DRY_RUN, default False
peer_timeout_seconds: float # env PEER_TIMEOUT_SECONDS, default 20.0

slack:      MCPServerConfig
jira:       MCPServerConfig
bitbucket:  MCPServerConfig
github:     MCPServerConfig

bug_daddy:       PeerAgentConfig  # env BUG_DADDY_URL
incident_daddy:  PeerAgentConfig  # env INCIDENT_DADDY_URL
reviewer_daddy:  PeerAgentConfig  # env REVIEWER_DADDY_URL
sme_agent:       PeerAgentConfig  # env SME_AGENT_URL
feature_daddy:   PeerAgentConfig  # env FEATURE_DADDY_URL
```

**`MCPServerConfig`**:
```python
name:           str
transport:      str        # "stdio" | "sse"
command:        str | None # stdio command path
args:           list[str]  # argv
url:            str | None # sse endpoint
tool_allowlist: list[str]  # env <NAME>_MCP_TOOL_ALLOWLIST (JSON array), empty = all tools
```

---

### 1.3 Contracts — `contracts.py`

#### Common Base — `IssueContext`
```python
fingerprint:    str
service_name:   str
issue_type:     str
source:         str
description:    str
stack_trace:    str | None
logs:           list[str]
jira_key:       str | None
repository:     str | None
metadata:       dict
```

#### `IncidentRequest`
```python
prompt:          str
source:          str  # "cloudwatch" | "prometheus" | "slack" | "api"
service_name:    str | None
repository:      str | None
logs:            list[str]
telemetry:       dict       # metrics, region, tags
kb_context:      str | None # runbook excerpt
metadata:        dict       # incident_channel, owner_hint, etc.
trigger:         str | None # "microservice_logs" | "cve" | "security_finding" | ...
criticality:     Criticality  # critical | high | medium | low | unknown
priority:        Priority      # p0 | p1 | p2 | p3 | p4 | unknown
opened_at:       datetime | None
acknowledged_at: datetime | None
resolved_at:     datetime | None
```

#### `BugRequest` (extends IssueContext)
```python
incident_summary:   str | None
incident_severity:  Severity      # sev1 | sev2 | sev3 | unknown
criticality:        Criticality
priority:           Priority
incident_artifacts: list[dict]    # analysis, orchestration, report outputs
```

#### `ReviewRequest`
```python
issue:            IssueContext
strategy_plan:    str
context_analysis: str
sme_guidance:     str
fix_proposal:     str
critique:         str
metadata:         dict
```

#### `SMEQueryRequest`
```python
question:     str
requested_by: str  # "incident_daddy" | "bug_daddy"
context:      IssueContext
```

#### `IncidentResponse`
```python
component:       "incident_daddy"
summary:         str
severity:        Severity
criticality:     Criticality
priority:        Priority
sla_kpis:        IncidentSLAKPI
owner_hint:      str | None
next_action:     str
handoff_to_bug:  bool
bug_request:     dict | None     # serialized BugRequest if handoff_to_bug=True
incident_report: IncidentReport | None
artifacts:       list[dict]      # [analysis_output, orchestration_output, report_output]
diagnostics:     dict            # MCP availability, peer status
```

#### `IncidentSLAKPI`
```python
ack_target_seconds:     int
resolve_target_seconds: int
remaining_ack_minutes:  float | None
remaining_resolve_minutes: float | None
ack_breached:           bool
resolve_breached:       bool
```

#### `BugResponse`
```python
component:       "bug_daddy"
summary:         str
resolution_kind: BugResolution  # review_required | pull_request | jira_ticket | rework_required
review_request:  dict | None
review_response: dict | None
artifacts:       list[dict]
diagnostics:     dict
```

#### `ReviewResponse`
```python
component:   "reviewer_daddy"
disposition: ReviewDisposition  # pull_request | jira_ticket | rework_required
summary:     str
pr_url:      str | None
artifacts:   list[dict]
diagnostics: dict
```

#### `FeatureResponse`
```python
component:    "feature_daddy"
feature_name: str
summary:      str
disposition:  FeatureDisposition  # pull_request | jira_ticket | rework_required
jira_key:     str | None
pr_url:       str | None
artifacts:    list
diagnostics:  dict
```

---

### 1.4 Agent Bundles — `agents.py`

All bundles are instantiated per-invocation (not shared across requests — Strands agents are stateful).

**Model initialization:**
```python
model = BedrockModel(
    model_id=config.bedrock_model_id,
    region_name=config.aws_region,
    temperature=0.1,
)
```

#### `IncidentAgentBundle`
| Sub-agent | Role | System Prompt | MCP Tools |
|-----------|------|---------------|-----------|
| `analyzer` | Extract facts, inferences, blast radius, likely owner | `INCIDENT_ANALYSER_PROMPT` | (none) |
| `orchestrator` | Triage, severity, Slack post, bug_daddy handoff decision | `INCIDENT_ORCHESTRATOR_PROMPT` | slack |
| `report_writer` | Generate markdown incident report | — | (none) |
| `report_reviewer` | Validate report quality | — | (none) |
| `slack_notifier` | Post incident updates | — | slack |

**`analyzer` output (JSON):**
```json
{
  "facts": ["..."],
  "inferences": ["..."],
  "blast_radius": "...",
  "likely_owner": "..."
}
```

**`orchestrator` output (JSON):**
```json
{
  "triage_summary": "...",
  "severity": "sev1|sev2|sev3",
  "next_action": "...",
  "bug_daddy_handoff": true
}
```

#### `BugAgentBundle`
| Sub-agent | Role | System Prompt | MCP Tools |
|-----------|------|---------------|-----------|
| `strategy_planner` | Remediation plan; emit `[RESOLUTION_TYPE: NON_CODE]` if operational only | `STRATEGY_PLANNER_PROMPT` | jira (update only) |
| `context_analyzer` | Read-only log + repo analysis | `CONTEXT_ANALYZER_PROMPT` | github_read_only |
| `coder` | Branch creation, minimal code fix | `CODER_PROMPT` | github_read_write |
| `critic` | Strategy + code proposal review | `CRITIC_PROMPT` | (none) |

#### `ReviewerAgentBundle`
| Sub-agent | Role | System Prompt | MCP Tools |
|-----------|------|---------------|-----------|
| `reviewer` | Final AI review; approve or send back | `REVIEWER_PROMPT` | github_pr |

#### `FeatureAgentBundle`
| Sub-agent | Role | MCP Tools |
|-----------|------|-----------|
| `prd_analyst` | Analyze PRD | (none) |
| `architect` | Design system changes | github_read_only |
| `implementer` | Implement code changes | github_read_write |
| `critic` | Code quality critique | (none) |
| `reviewer` | Final review + PR create | github_pr |

#### `SMEAgentBundle`
| Sub-agent | Role | MCP Tools |
|-----------|------|-----------|
| `expert` | SOP-backed guidance, ownership info | (none — inline context) |

---

### 1.5 Service Runtimes

#### `IncidentDaddyRuntime` — `services/incident.py`

```
run(request: IncidentRequest) -> IncidentResponse

Steps (sequential):
  1. sme_runtime.run(SMEQueryRequest) → sme_guidance
  2. bundle.analyzer.run(prompt + logs) → analysis_json (facts, inferences, blast_radius, owner)
  3. bundle.orchestrator.run(analysis + triage context) → orchestration_json
     - Posts Slack summary to #production_issue (channel C0B2QUEU4NN)
     - Decides handoff_to_bug
  4. bundle.report_writer.run(analysis + orchestration) → markdown_report
  5. bundle.report_reviewer.run(markdown_report) → validated_report
  6. bundle.slack_notifier.run(validated_report) → (posts update)
  7. jira_create_or_update(issue context) → jira_key
  8. Compute IncidentSLAKPI from criticality + opened_at
  9. Return IncidentResponse{
       handoff_to_bug: orchestration_json.bug_daddy_handoff,
       bug_request: serialize(BugRequest) if handoff_to_bug,
       ...
     }
```

#### `BugDaddyRuntime` — `services/bug.py`

```
run(request: BugRequest) -> BugResponse

Steps:
  1. sme_runtime.run(SMEQueryRequest) → sme_guidance
  2. bundle.context_analyzer.run(logs + repo context) → context_analysis
  3. bundle.strategy_planner.run(context + sme) → strategy_plan
  4. bundle.critic.run(strategy_plan) → strategy_critique
  5. If heuristics.is_non_code_resolution(strategy_plan, strategy_critique):
       → Return BugResponse{resolution_kind: jira_ticket} (early exit)
  6. bundle.coder.run(strategy + context) → fix_proposal
     - Creates branch: fix/<JIRA_KEY> on GitHub
     - Commits minimal fix
  7. bundle.critic.run(fix_proposal) → code_critique
  8. Build ReviewRequest{strategy_plan, context_analysis, sme_guidance, fix_proposal, critique}
  9. reviewer_runtime.run(ReviewRequest) → ReviewResponse
  10. Return BugResponse{resolution_kind: reviewer.disposition, review_response: ...}
```

#### `ReviewerDaddyRuntime` — `services/reviewer.py`

```
run(request: ReviewRequest) -> ReviewResponse

Steps:
  1. bundle.reviewer.run(fix_proposal + critique + strategy) → review_text
  2. disposition = heuristics.infer_review_disposition(review_text)
     - "pull_request" if PR URL found in text
     - "jira_ticket" if Jira update only
     - "rework_required" otherwise
  3. pr_url = extract_pr_url(review_text) via regex if disposition == "pull_request"
  4. execution_logger.map_pull_request_resolution(pr_url) if pr_url
  5. Return ReviewResponse{disposition, pr_url}
```

#### `ClassifierRuntime` — `services/classifier.py`

```
run(raw_payload: dict) -> ClassificationResult

Steps:
  1. Read issue fields (description, stack_trace, source, freq)
  2. Classify: incident | bug | feature | security_finding
     - freq > 1000 → soft INCIDENT signal (not deterministic gate)
  3. Create Jira ticket in SCRUM project if jira_key absent
  4. Return {issue_type, jira_key}
```

#### `CombinedBugDaddyRuntime` — `services/combined.py`

```
run(payload: dict) -> dict

Routing logic:
  - payload["target"] == "incident_daddy"  → IncidentDaddyRuntime
  - payload["target"] == "bug_daddy"       → BugDaddyRuntime
  - payload["target"] == "reviewer_daddy"  → ReviewerDaddyRuntime
  - payload["target"] == "sme_agent"       → SMEAgentRuntime
  - payload["target"] == "classifier"      → ClassifierRuntime
  - payload["target"] == "feature_daddy"   → FeatureDaddyRuntime
  - default                                → IncidentDaddyRuntime

Peer handoffs via LocalPeerRuntimeClient (in-process, no HTTP).
```

---

### 1.6 MCP Tool Bundle — `mcp.py`

```python
class MCPToolBundle:
    jira_tools:              list[Tool]  # create_issue, update_issue, assign_issue, close_issue
    bitbucket_tools:         list[Tool]  # clone, list_files, read_blob, create_pr
    github_read_only_tools:  list[Tool]  # list_files, read_file, get_commit
    github_read_write_tools: list[Tool]  # create_branch, create_commit, push
    github_pr_tools:         list[Tool]  # create_pr, get_pr, merge_pr
    slack_tools:             list[Tool]  # post_message, send_thread_message

    @staticmethod
    def build(config: MCPServerConfig) -> list[Tool]:
        # Starts MCP server subprocess (stdio) or connects SSE endpoint
        # Filters to tool_allowlist if provided
        # Returns typed Tool objects for Strands agents
```

Slack MCP is created **per-request** (dynamic channel targeting). GitHub, Jira, Bitbucket MCP servers are initialized once at bundle build time.

---

### 1.7 Execution Logger — `execution.py`

```python
class ExecutionLogger:
    session_id: str
    callback_url: str  # env AGENT_EXECUTION_CALLBACK_URL
    secret: str        # env AGENT_EXECUTION_LOG_SECRET

    def emit(event_type: str, **fields) -> None:
        # POST {callback_url}/agent/executions/{session_id}/events
        # Header: X-Agent-Execution-Secret: {secret}
        # Body: {event_type, node_id, node_name, agent_name, status, level,
        #        title, description, reasoning_summary, input_summary, output_summary,
        #        tool_name, duration_ms, input_tokens, output_tokens, error_message}

    def map_jira_resolution(jira_url: str) -> None:
        # POST {callback_url}/agent/executions/{session_id}/resolution/jira
        # Body: {jira_url}

    def map_pull_request_resolution(pr_url: str) -> None:
        # POST {callback_url}/agent/executions/{session_id}/resolution/pr
        # Body: {pr_url}

    def update_issue_status_to_review() -> None:
        # POST {callback_url}/agent/executions/{session_id}/issue-status
        # Body: {status: "in_review"}
```

---

### 1.8 Heuristics — `heuristics.py`

```python
def infer_incident_severity(log_text: str) -> Severity:
    # Keyword matching: "critical" | "fatal" | "down" → sev1
    #                   "error" | "exception" | "fail" → sev2
    #                   everything else → sev3 | unknown

def is_non_code_resolution(strategy: str, critic: str) -> bool:
    # Returns True iff "[RESOLUTION_TYPE: NON_CODE]" present in strategy or critic text

def infer_review_disposition(review_text: str) -> ReviewDisposition:
    # Regex search for PR URL (github.com/*/pull/*) → "pull_request"
    # Regex search for Jira URL (*.atlassian.net/browse/*) → "jira_ticket"
    # Default → "rework_required"
```

---

### 1.9 Orchestrator Layer — `orchestrator/`

The orchestrator is a production-grade event pipeline that sits between raw triggers and agent runtimes.

#### `IngestionGate` — `ingestion.py`
```
accept(raw_trigger: RawTrigger) -> NormalizedEvent | None
  1. Compute correlation_id from trigger content
  2. Check dedup store (in-memory TTL cache or Redis): if seen recently → discard
  3. Journal raw trigger to AuditJournal
  4. Forward to EventNormalizer
```

#### `EventNormalizer` — `normalization.py`
```
normalize(raw: RawTrigger) -> NormalizedEvent
  1. Parse source-specific payload (CloudWatch, Prometheus, Slack, API)
  2. Enrich: extract service_name, environment, region
  3. Score severity: re-score from log content (do NOT trust upstream severity)
  4. Classify incident type (deterministic taxonomy — 20 classes):
     CPU_SPIKE, MEMORY_PRESSURE, DATABASE_SATURATION, SERVICE_DOWNTIME,
     ELEVATED_ERROR_RATE, FAILED_DEPLOYMENT, CVE_VULNERABILITY,
     SUSPICIOUS_IAM, UNAUTHORIZED_API_ACCESS, WAF_ANOMALY, IDS_ANOMALY,
     TLS_EXPIRY, CLOUD_MISCONFIG, RANSOMWARE_INDICATOR, UNKNOWN, ...
  5. Return NormalizedEvent{correlation_id, severity, incident_class, ...}
```

#### `PriorityScheduler` — `scheduler.py`
```
Weighted-fair queue with weights:
  SEV0 → 100 | SEV1 → 60 | SEV2 → 25 | SEV3 → 8 | SEV4 → 1

enqueue(event: NormalizedEvent) → position
dequeue() → NormalizedEvent  # highest-weight event
```

#### `RoutingEngine` — `routing/router.py`
```
route(event: NormalizedEvent) -> list[AgentTarget]
  - Maps incident_class → one primary agent (plus optional parallel observers)
  - Example: ELEVATED_ERROR_RATE → incident_daddy (primary) + sme_agent (parallel context)
  - Example: CVE_VULNERABILITY → incident_daddy (primary) + security observer
```

#### `AgentRegistry` — `routing/registry.py`
```
Maintains per-agent:
  capabilities:      list[IncidentClass]
  health:            healthy | degraded | unavailable
  concurrency_limit: int
  active_count:      int

select(incident_class) -> AgentTarget | None  # respects health and concurrency
```

#### `AgentExecutor` — `runtime/executor.py`
```
execute(target: AgentTarget, event: NormalizedEvent) -> AgentOutcome
  - Invoke agent runtime (local or HTTP peer)
  - Timeout: per-agent configurable (default 20s for peers)
  - Retry: 3 attempts with exponential backoff
  - On max retries exhausted: emit error AgentOutcome
```

#### `CircuitBreaker` — `runtime/circuit_breaker.py`
```
States: CLOSED → OPEN → HALF_OPEN → CLOSED

CLOSED:    pass all requests through; count failures
OPEN:      reject all requests immediately (fail fast)
HALF_OPEN: allow one probe; if success → CLOSED, if fail → OPEN

Thresholds (configurable):
  failure_threshold: int   # failures in rolling window to trip open
  success_threshold: int   # successes in HALF_OPEN to re-close
  timeout_seconds: float   # time before OPEN → HALF_OPEN
```

#### `RecoveryCoordinator` — `runtime/recovery.py`
```
On agent failure:
  1. Look up compensation actions for each completed step (registered at step start)
  2. Replay in LIFO order (undo last action first)
  3. Log compensation outcomes to AuditJournal
  4. Escalate to manual if compensation fails
```

#### `RemediationSupervisor` — `runtime/supervisor.py`
```
supervise(plan: RemediationPlan) -> list[AgentOutcome]
  - Execute plan DAG steps in dependency order
  - Parallel execution for independent steps
  - Pass outputs of each step as inputs to dependent steps
  - On step failure: RecoveryCoordinator.compensate()
  - Emit structured audit events throughout
```

---

## 2. Platform Backend

### 2.1 Application Entry — `main.py`

```
FastAPI app with:
  - CORS middleware
  - JWT auth middleware (dependency injection)
  - Routers: auth, issues, users, admin, agent_callbacks, ai_queue, sonar, security, rag
  - Startup: create DB tables, seed roles/permissions, start SQS worker background task
  - Uvicorn on PORT (env BACKEND_PORT, default 8000)
```

---

### 2.2 Database Schema

**`service_exception_log`** — Central issue store
```sql
id              BIGINT PRIMARY KEY AUTO_INCREMENT
fingerprint     VARCHAR(255) UNIQUE NOT NULL    -- SHA256(service|type|normalized_msg)
service_name    VARCHAR(255) NOT NULL
issue_type      VARCHAR(255)                    -- bug|vulnerability|critical_code_smell|...
source          VARCHAR(64)                     -- cloudwatch|sonarqube|cve|techdebt
description     TEXT
stack_trace     LONGTEXT
entire_execution_logs LONGTEXT
request_id      VARCHAR(255)
frequency       BIGINT DEFAULT 1
first_seen      DATETIME
last_seen       DATETIME
status          VARCHAR(64) DEFAULT 'open'      -- open|in_progress|in_review|resolved|no_action
assigned_to     VARCHAR(255)
resolution_pr   VARCHAR(255)
resolution_jira VARCHAR(255)
created_at      DATETIME
resolved_at     DATETIME

INDEX: (fingerprint), (service_name), (status), (source), (last_seen), (created_at)
```

**`execution_sessions`**
```sql
id              VARCHAR(36) PRIMARY KEY         -- UUID
issue_id        BIGINT FK → service_exception_log.id
workflow_key    VARCHAR(100)                    -- "incident_daddy" | "bug_daddy" | ...
workflow_version VARCHAR(20) DEFAULT 'v1'
agent_target    VARCHAR(100)
status          VARCHAR(50)                     -- queued|executing|succeeded|failed
created_at      DATETIME
```

**`execution_events`**
```sql
id              BIGINT PRIMARY KEY AUTO_INCREMENT
session_id      VARCHAR(36) FK → execution_sessions.id
event_type      VARCHAR(50)                     -- node.started|node.completed|tool.executed|error.occurred
node_id         VARCHAR(100)
node_name       VARCHAR(200)
agent_name      VARCHAR(100)
status          VARCHAR(50)
level           VARCHAR(20)                     -- debug|info|warning|error
title           VARCHAR(500)
description     TEXT
reasoning_summary TEXT
input_summary   TEXT
output_summary  TEXT
tool_name       VARCHAR(200)
duration_ms     INT
input_tokens    INT
output_tokens   INT
error_message   TEXT
created_at      DATETIME
```

**`users`**
```sql
id              VARCHAR(36) PRIMARY KEY         -- UUID
username        VARCHAR(100) UNIQUE
email           VARCHAR(255) UNIQUE
password_hash   VARCHAR(255)                    -- PBKDF2-HMAC-SHA256, 120k iterations
full_name       VARCHAR(255)
role_id         INT FK → roles.id
status          VARCHAR(20) DEFAULT 'active'    -- active|inactive|locked
is_email_verified BOOLEAN DEFAULT FALSE
last_login_at   DATETIME
created_at      DATETIME
updated_at      DATETIME
```

**`roles`** / **`permissions`** / **`role_permissions`**
```sql
roles:        id, name (admin|user), description
permissions:  id, permission_key UNIQUE, description
              -- keys: issues.read|update, users.create|read|update|delete, roles.read|update, audit.read
role_permissions: (role_id, permission_id) composite PK
```

**`user_sessions`** (JWT refresh token management)
```sql
id                VARCHAR(36) PRIMARY KEY
user_id           VARCHAR(36) FK → users.id
refresh_token_hash VARCHAR(64)                  -- SHA256 of refresh token
expires_at        DATETIME
revoked_at        DATETIME NULL
created_at        DATETIME
```

**`ai_queue_config`** / **`ai_queue_items`**
```sql
ai_queue_config:
  id, is_active BOOLEAN, queue_length INT, queue_url VARCHAR(500)
  updated_by, created_at, updated_at

ai_queue_items:
  id, issue_id, sqs_message_id, status (queued|processing|completed|failed)
  worker_id, session_id, attempts, last_error
  enqueued_at, started_at, completed_at
```

---

### 2.3 API Endpoints

#### Authentication — `/auth`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | None | Username/email + password → `{access_token, refresh_token}` |
| POST | `/auth/refresh` | Refresh token | Rotate → new `access_token` |
| POST | `/auth/forgot-password` | None | Email → reset token (1h TTL, emailed) |
| POST | `/auth/reset-password` | None | Reset token + new_password |
| POST | `/auth/verify-email` | None | Email verification token (24h TTL) |

**JWT structure:**
```json
{ "sub": "<user_id>", "role": "admin|user", "exp": <unix_ts> }
```
Access token TTL: `ACCESS_TOKEN_MINUTES` (default 60).
Refresh token TTL: `REFRESH_TOKEN_DAYS` (default 14), stored as SHA-256 hash.

#### Issues — `/issues`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/issues?tab=backlog\|wip\|review\|resolved` | user | Paginated issue list by status |
| GET | `/issues/{id}` | user | Full detail with stack_trace, logs, resolution |
| PUT | `/issues/{id}` | user | Update status, assigned_to, resolution_pr, resolution_jira |
| GET | `/issues/{id}/execution-events` | user | ExecutionSession + ordered event timeline |
| POST | `/issues/{id}/ai-queue` | user | Enqueue issue for agent remediation |

**`GET /issues` tab → status mapping:**
```
backlog → status='open'
wip     → status='in_progress'
review  → status='in_review'
resolved → status IN ('resolved', 'no_action')
```

#### Admin — `/admin`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/admin/users` | admin | Create user |
| PUT | `/admin/users/{id}` | admin | Update user (role, status, etc.) |
| DELETE | `/admin/users/{id}` | admin | Deactivate user (soft delete: status=inactive) |
| GET | `/admin/users` | admin | Paginated user list |
| PUT | `/admin/roles/{role_id}/permissions` | admin | Replace role permission set |
| GET | `/admin/schema` | admin | Table list, record counts, service registry |
| GET | `/admin/audit-logs` | admin | Paginated audit trail |

#### Agent Callbacks — `/agent`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/agent/executions/{session_id}/events` | secret header | Agent emits execution event |
| POST | `/agent/executions/{session_id}/resolution/jira` | secret header | Agent maps Jira URL |
| POST | `/agent/executions/{session_id}/resolution/pr` | secret header | Agent maps PR URL |
| POST | `/agent/executions/{session_id}/issue-status` | secret header | Agent moves issue to in_review |

Auth: `X-Agent-Execution-Secret` header checked against `AGENT_EXECUTION_LOG_SECRET` env var.

#### RAG — `/rag`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/rag/ingest` | admin API key | Ingest repo directory into vector store |
| POST | `/rag/admin/reindex` | admin API key | Full reindex |
| GET | `/rag/conversations` | widget API key | List user conversations |
| POST | `/rag/chat/stream` | widget API key | Streaming chat (SSE) |
| GET | `/rag/messages/{conversation_id}` | widget API key | History + citations |
| POST | `/rag/feedback` | widget API key | Rating/comment on response |
| GET | `/rag/metrics` | admin API key | Usage metrics |

---

### 2.4 AI Queue — SQS Integration

**Worker startup (background task on app start):**
```
for i in range(AI_QUEUE_WORKERS):  # default 3
    asyncio.create_task(sqs_worker(i))

async def sqs_worker(worker_id):
    while True:
        messages = sqs.receive_message(
            QueueUrl=AI_QUEUE_URL,
            MaxNumberOfMessages=AI_QUEUE_DEFAULT_LENGTH,  # default 3
            WaitTimeSeconds=20
        )
        for msg in messages:
            issue_id = msg.body.issue_id
            session_id = create_execution_session(issue_id)
            update_ai_queue_item(status=processing, worker_id=worker_id)
            await invoke_agent(session_id, issue_id)
            sqs.delete_message(msg.receipt_handle)
        await asyncio.sleep(AI_QUEUE_POLL_SECONDS)  # default 10s
```

**Agent invocation:**
```
invoke_agent(session_id, issue_id):
  1. Fetch issue from service_exception_log
  2. Build IncidentRequest from issue fields
  3. Call Bedrock AgentCore:
     bedrock.invoke_agent(
       agentAliasId=AGENTCORE_RUNTIME_ARN,
       sessionId=session_id,
       inputText=serialize(request)
     )
  4. Process streaming response chunks → update ExecutionSession status
  5. On completion: update ai_queue_item status=completed
```

---

### 2.5 RAG Subsystem — `rag/`

**Ingestion pipeline:**
```
ingest(repo_path: str):
  1. Walk directory tree
  2. parsers.parse(file) → list[RawChunk] (preserves file path, language)
  3. chunkers.chunk(raw_chunks) → list[Chunk] (semantic splits with overlap)
  4. For each chunk:
     a. bedrock.embed(chunk.text) → float[1536]  # Titan embedding
     b. INSERT INTO embeddings(chunk_id, vector, text, file_path, language)
     c. INSERT INTO keyword_index for BM25 (full-text)
```

**Retrieval (hybrid search + rerank):**
```
retrieve(question: str, top_k_merged=8) -> list[Chunk]:
  1. embed(question) → query_vector
  2. vector_search(query_vector, top_k=50) → vector_results (cosine similarity)
  3. keyword_search(question, top_k=50) → keyword_results (BM25)
  4. reciprocal_rank_fusion(vector_results, keyword_results, k=60) → merged (top 100)
  5. cross_encoder_rerank(merged, question) → reranked
  6. diversify_by_file(reranked, max_per_file=2) → diversified
  7. compress(diversified, max_chars=4000) → context
```

**Chat (streaming):**
```
POST /rag/chat/stream  →  SSE

  1. Rate limit check (per user, per endpoint)
  2. Retrieve conversation history (last MEMORY_MESSAGES=10)
  3. retrieve(question) → context chunks
  4. Build prompt: system + history + context + user question
  5. bedrock.stream_completion(prompt) → token stream
  6. Yield SSE events: {type: "token", content: "..."} per token
  7. On end: yield {type: "citations", citations: [{file, line, chunk_id}]}
  8. Save Message + Citation records to DB
```

---

## 3. Platform Frontend

### 3.1 Application Structure

```
platform/frontend/src/
├── app/
│   ├── layout.tsx              # Root layout — QueryClientProvider + global styles
│   ├── page.tsx                # Landing (redirects to /dashboard if authed)
│   ├── login/page.tsx          # Login page
│   ├── reset/page.tsx          # Password reset
│   └── dashboard/page.tsx      # Main dashboard (auth guard)
├── components/
│   ├── DashboardApp.tsx         # Root dashboard: tab routing + layout
│   ├── views/
│   │   ├── IssuesView.tsx       # Issue kanban (backlog/wip/review/resolved)
│   │   ├── AdminView.tsx        # User/role/audit management
│   │   ├── AiQueueView.tsx      # Queue depth + item status
│   │   ├── SonarView.tsx        # SonarQube findings
│   │   ├── SecurityView.tsx     # CVE findings
│   │   ├── GrafanaView.tsx      # Monitoring iframe
│   │   └── KibanaView.tsx       # Logging iframe
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   └── Topbar.tsx
│   └── shared/
│       ├── ExecutionGraphModal.tsx    # DAG visualization of agent steps
│       ├── AiThinkingBadge.tsx        # Spinner during agent execution
│       ├── CommandPalette.tsx
│       ├── AsyncActionButton.tsx
│       ├── ToastContainer.tsx
│       ├── SkeletonLoader.tsx
│       └── Metric.tsx                 # KPI card
└── lib/
    ├── types.ts                # TypeScript domain models
    └── api.ts                  # Fetch-based API client (JWT auto-attach + refresh)
```

---

### 3.2 API Client — `lib/api.ts`

**Token management:**
```typescript
// Store: localStorage (access_token, refresh_token)
// On every request: attach Authorization: Bearer {access_token}
// On 401: attempt refreshToken(); retry original request once
// On refresh failure: redirect to /login
```

**Key methods:**
```typescript
// Auth
login(identifier: string, password: string): Promise<AuthResponse>
refreshToken(): Promise<{access_token: string}>
logout(): void

// Issues
listIssues(tab: 'backlog'|'wip'|'review'|'resolved'): Promise<Issue[]>
getIssue(id: number): Promise<Issue>
updateIssue(id: number, fields: Partial<Issue>): Promise<Issue>
getExecutionEvents(id: number): Promise<ExecutionSession & {events: ExecutionEvent[]}>
invokeAgent(issue: Issue): Promise<{session_id: string}>

// Queue
getAiQueueStatus(): Promise<AiQueueStatus>
enqueueIssue(issueId: number): Promise<AiQueueItem>

// Sonar
getSonarStatus(): Promise<SonarStatus>
invokeSonarScan(repo: string): Promise<{scan_id: string}>
getSonarReports(): Promise<SonarReport[]>

// Security
getSecurityScanStatus(): Promise<SecurityScanStatus>
invokeSecurityScan(): Promise<{scan_id: string}>
getSecurityFindings(): Promise<SecurityFinding[]>

// Admin
listUsers(): Promise<User[]>
createUser(payload: CreateUserPayload): Promise<User>
updateUser(id: string, payload: Partial<User>): Promise<User>
deleteUser(id: string): Promise<void>
updateRolePermissions(roleId: number, permissionKeys: string[]): Promise<void>
getAuditLogs(page: number): Promise<AuditLog[]>
```

---

### 3.3 Key Type Definitions — `lib/types.ts`

```typescript
interface Issue {
  id: number
  fingerprint: string
  service_name: string
  issue_type: string
  source: 'cloudwatch' | 'sonarqube' | 'cve' | 'techdebt'
  description: string
  stack_trace: string | null
  entire_execution_logs: string | null
  frequency: number
  first_seen: string
  last_seen: string
  status: 'open' | 'in_progress' | 'in_review' | 'resolved' | 'no_action'
  assigned_to: string | null
  resolution_pr: string | null
  resolution_jira: string | null
  created_at: string
  resolved_at: string | null
}

interface ExecutionSession {
  id: string
  issue_id: number
  workflow_key: string
  agent_target: string
  status: 'queued' | 'executing' | 'succeeded' | 'failed'
  created_at: string
}

interface ExecutionEvent {
  id: number
  session_id: string
  event_type: 'node.started' | 'node.completed' | 'tool.executed' | 'error.occurred'
  node_id: string
  node_name: string
  agent_name: string
  status: string
  level: 'debug' | 'info' | 'warning' | 'error'
  title: string
  description: string | null
  reasoning_summary: string | null
  output_summary: string | null
  tool_name: string | null
  duration_ms: number | null
  input_tokens: number | null
  output_tokens: number | null
  error_message: string | null
  created_at: string
}

interface WorkflowGraph {
  nodes: Array<{id: string; label: string; status: string; agent: string}>
  edges: Array<{source: string; target: string}>
}

interface DashboardSummary {
  total: number
  backlog: number
  wip: number
  review: number
  resolved: number
  critical: number
}
```

---

### 3.4 Execution Graph Modal — `ExecutionGraphModal.tsx`

Renders the agent execution DAG as an interactive graph:

```
Data source: GET /issues/{id}/execution-events
  → ExecutionSession + ExecutionEvent[]

Graph construction:
  1. Group events by agent_name → nodes
  2. Derive edges from event sequence (node.started → node.completed → next node.started)
  3. Color-code by status: succeeded=green, failed=red, executing=yellow
  4. Show token counts and duration_ms per node on hover
  5. Expand node → show reasoning_summary, output_summary, tool calls
```

SSE polling (during active execution):
```
EventSource: GET /issues/{id}/execution-stream
  - Push ExecutionEvent objects as they arrive
  - Append to graph in real-time
  - Close stream when session status = succeeded | failed
```

---

## 4. Triggers Layer

### 4.1 `LogMonitoringBot` — CloudWatch Logs → MySQL

**Runtime:** AWS Lambda (Python 3.12)
**Trigger:** CloudWatch Logs Subscription Filter on monitored log groups

**Processing detail:**
```python
def lambda_handler(event, context):
    # 1. Decode payload
    compressed = base64.b64decode(event['awslogs']['data'])
    payload = json.loads(gzip.decompress(compressed))
    log_group = payload['logGroup']           # e.g., /aws/lambda/checkout-service
    log_stream = payload['logStream']
    log_events = payload['logEvents']

    for event in log_events:
        message = event['message']

        # 2. Classify
        issue_type = classify(message)
        # Rules (in order, first match wins):
        #   "timed out" | "Task timed out"  → "timeout"
        #   DB error keywords               → "database_exception"
        #   "Traceback (most recent"        → "python_traceback"
        #   "Exception" in message          → "exception"
        #   "Error" in message              → "error"
        #   Default                         → "log_exception"

        # 3. Normalize (remove noise for stable fingerprint)
        normalized = re.sub(r'[0-9a-f-]{8,}', '<ID>', message)  # UUIDs
        normalized = re.sub(r'\d+', '<N>', normalized)           # numbers

        # 4. Fingerprint
        service_name = extract_service(log_group)  # last path component
        fingerprint = sha256(f"{service_name}|{issue_type}|{normalized}")

        # 5. Fetch full invocation logs (START…END/REPORT boundary)
        full_logs = cloudwatch.filter_log_events(
            logGroupName=log_group,
            logStreamNames=[log_stream],
            filterPattern=f'"{request_id}"'
        )

        # 6. Upsert
        db.execute("""
            INSERT INTO service_exception_log
              (fingerprint, service_name, issue_type, source, description,
               stack_trace, entire_execution_logs, request_id, frequency,
               first_seen, last_seen, status, created_at)
            VALUES (%s, ...)
            ON DUPLICATE KEY UPDATE
              frequency = frequency + 1,
              last_seen = NOW(),
              stack_trace = VALUES(stack_trace),
              entire_execution_logs = VALUES(entire_execution_logs)
        """, ...)
```

---

### 4.2 `SonarReportIngestor` — SonarQube → MySQL

**Runtime:** AWS Lambda (Python 3.12)
**Trigger:** S3 PutObject notification on `bugdaddy-sonar-reports/` prefix

**Issue type mapping:**
```python
SONAR_TYPE_MAP = {
    ("BUG", "CRITICAL"): "bug",
    ("BUG", "MAJOR"):    "bug",
    ("BUG", "MINOR"):    "bug",
    ("VULNERABILITY", _): "vulnerability",
    ("CODE_SMELL", "CRITICAL"): "critical_code_smell",
    ("CODE_SMELL", "MAJOR"):    "major_code_smell",
    ("CODE_SMELL", _):          "code_smell",
}
```

**Stack trace construction:**
```
Rule: {issue.rule}
Severity: {issue.severity}
File: {issue.component}:{issue.line}
Message: {issue.message}
Data Flows:
  {location.msg} @ {location.component}:{location.textRange.startLine}
  ...
```

**Service name extraction:**
```python
# component = "bugdaddy:platform/backend/handlers/auth.py"
# service_name = "platform/backend"
service_name = "/".join(component.split(":")[1].split("/")[:-1])
```

---

### 4.3 `SecurityScanner` — CVE/SBOM → MySQL

**Runtime:** AWS Lambda orchestrator + ingestor Lambda

**Phase 1 — Asset inventory (`aws_inventory.py`):**
```python
ec2_client.describe_instances() → filter running instances
lambda_client.list_functions()  → all functions in region
rds_client.describe_db_instances() → all DB instances
```

**Phase 1b — Lambda package extraction (`lambda_package_extractor.py`):**
```python
lambda_client.get_function(FunctionName=name)
  → download Code.Location (presigned S3 URL)
  → ZipFile.extractall()
  → parse requirements.txt or package.json
  → inject as {type: "pip_package"|"npm_package", name, version}
```

**Phase 2 — CVE lookup (`cve_lookup.py`):**
```python
# NVD API
GET https://services.nvd.nist.gov/rest/json/cves/2.0
  ?keywordSearch={package_name}&keywordExactMatch
  → filter by version range

# OSV API
POST https://api.osv.dev/v1/query
  {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}

# Cache hits by (package, version) to stay within rate limits
```

**Phase 3 — Report upload (`report.py`):**
```python
report = {timestamp, region, summary, assets, findings, dependencies}
s3.put_object(
    Bucket="bugdaddy-security-reports",
    Key=f"reports/{timestamp}.json",
    Body=json.dumps(report)
)
# S3 PutObject triggers SecurityIngestor Lambda
```

**SecurityIngestor Lambda:**
```python
for finding in report["findings"]:
    fingerprint = sha256(f"security_finding|{finding.cve_id}|{finding.asset_id}")
    severity_map = {"CRITICAL": "cve_critical", "HIGH": "cve_high", ...}
    db_upsert(fingerprint, issue_type=severity_map[finding.severity], source="cve", ...)
```

---

## 5. Environment Variables Reference

### Agents
| Variable | Default | Purpose |
|----------|---------|---------|
| `BEDROCK_MODEL_ID` | `qwen.qwen3-coder-480b-a35b-v1:0` | LLM for all agent bundles |
| `AWS_REGION` | `us-west-2` | Bedrock region |
| `DRY_RUN` | `false` | Skip external side-effects |
| `PEER_TIMEOUT_SECONDS` | `20.0` | HTTP timeout for peer runtime calls |
| `SLACK_MCP_COMMAND` | — | stdio command for Slack MCP server |
| `JIRA_MCP_COMMAND` | — | stdio command for Jira MCP server |
| `BITBUCKET_MCP_COMMAND` | — | stdio command for Bitbucket MCP server |
| `GITHUB_MCP_COMMAND` | — | stdio command for GitHub MCP server |
| `*_MCP_TOOL_ALLOWLIST` | `[]` (all) | JSON array of permitted tool names |
| `AGENT_EXECUTION_CALLBACK_URL` | — | Platform backend base URL |
| `AGENT_EXECUTION_LOG_SECRET` | — | Shared secret for callback auth |
| `AGENT_EXECUTION_LOG_TIMEOUT` | `3` | Callback HTTP timeout (seconds) |

### Platform Backend
| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_HOST/PORT/NAME/USER/PASSWORD` | — | MySQL connection |
| `TOKEN_SECRET` | — | JWT signing key |
| `ACCESS_TOKEN_MINUTES` | `60` | Access token TTL |
| `REFRESH_TOKEN_DAYS` | `14` | Refresh token TTL |
| `PBKDF2_ITERATIONS` | `120000` | Password hashing cost |
| `AWS_REGION` | `ap-south-1` | Platform AWS region |
| `AGENTCORE_RUNTIME_ARN` | — | Bedrock AgentCore runtime ARN |
| `JIRA_BASE_URL` | `https://bugdaddy.atlassian.net` | Jira instance |
| `SONAR_LAMBDA_NAME` | `bugdaddy-sonar-scan-trigger` | Lambda to invoke for scans |
| `SONAR_REPORT_BUCKET` | `bugdaddy-sonar-reports` | S3 bucket for reports |
| `AI_QUEUE_URL` | — | SQS queue URL |
| `AI_QUEUE_WORKERS` | `3` | Background worker count |
| `AI_QUEUE_POLL_SECONDS` | `10` | SQS polling interval |
| `AI_QUEUE_DEFAULT_LENGTH` | `3` | Max items per poll |
| `RAG_DATABASE_URL` | — | PostgreSQL + pgvector DSN |
| `RAG_WIDGET_API_KEY` | — | Public chat widget key |
| `RAG_ADMIN_API_KEY` | — | Admin operations key |
| `RETRIEVAL_TOP_K_VECTOR` | `50` | Vector search results |
| `RETRIEVAL_TOP_K_KEYWORD` | `50` | BM25 results |
| `RETRIEVAL_TOP_K_MERGED` | `8` | Final context chunks |

---

## 6. CI / Quality Gates

**File:** `.github/workflows/agents-ci.yml`

```yaml
steps:
  - ruff check (pycodestyle, pyflakes, isort, pyupgrade, bugbear, comprehensions, pytest rules)
  - mypy --strict-optional
  - pytest -x --asyncio-mode=auto
  - coverage: minimum 70% line coverage

Makefile targets:
  make test       # pytest suite
  make cov        # coverage report
  make lint       # ruff check
  make typecheck  # mypy
  make check      # all gates (lint + typecheck + test + cov)
  make demo       # orchestrator demo run
```

**Test structure:**
```
tests/
├── test_contracts.py
├── test_heuristics.py
├── test_incident.py
├── test_bug.py
├── test_reviewer.py
└── orchestrator/
    ├── test_ingestion.py
    ├── test_normalization.py
    ├── test_routing.py
    ├── test_scheduler.py
    ├── test_circuit_breaker.py
    ├── test_executor.py
    ├── test_recovery.py
    └── test_supervisor.py
```
