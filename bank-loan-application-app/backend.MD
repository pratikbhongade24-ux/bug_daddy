# Backend API Contracts

Based on the mocked "GrabHack 2.0 — Agentic Issue Intelligence" dashboard UI, the following REST and WebSocket APIs are required to fully transition the frontend to a dynamic backend architecture. 

## 1. Issues Management

### `GET /api/issues`
Fetches a paginated list of issues with robust filtering capabilities. Forms the core of the Issues Table and Escalation Queue.

**Query Parameters:**
- `search` (string): Text filter for JIRA ID or error description.
- `service` (string): Filter by specific microservice.
- `criticality` (string): 'Critical', 'High', 'Medium', 'Low'.
- `origin` (string): 'CloudWatch', 'CVE', 'SonarQube', 'JIRA'.
- `tab` (string): 'backlog', 'wip', 'resolved'.
- `min_freq` (number): Used for the escalation queue (e.g., `min_freq=400`).
- `limit` (number), `offset` (number): Pagination properties.

**Response:**
```json
{
  "total": 36,
  "issues": [
    {
      "id": 104,
      "jiraId": "GH-104",
      "service": "grabhack-BankStatementService",
      "shortSvc": "BankStatement",
      "type": "log_exception",
      "freq": 2,
      "err": "ValueError: invalid literal for int() — summarizeCashflow",
      "status": "open",
      "owner": "Priya S.",
      "criticality": "Low",
      "origin": "CloudWatch",
      "tab": "backlog",
      "eta": "~15m"
    }
  ]
}
```

### `GET /api/issues/stats`
Fetches the KPI numbers and service distribution for the dashboard headers and microservice breakdown bar charts.

**Response:**
```json
{
  "kpis": {
    "total": 36,
    "backlog": 10,
    "wip": 5,
    "resolved": 21,
    "critical": 8
  },
  "breakdownByService": {
    "grabhack-BankStatementService": { "total": 12, "backlog": 4, "wip": 2, "resolved": 6 },
    "grabhack-CustomerOnboardingService": { "total": 8, "backlog": 2, "wip": 1, "resolved": 5 }
  }
}
```

## 2. Actions & Mutations

### `POST /api/issues/{id}/prioritize`
Action triggered when clicking "Prioritize" on an issue in the backlog. Moves the item to the WIP queue and triggers execution.

**Response:**
```json
{
  "success": true,
  "issueId": 104,
  "newTab": "wip",
  "eta": "~15m",
  "message": "GH-104 prioritized → WIP queue"
}
```

### `POST /api/issues/escalate-all`
Action triggered by the top-right "Escalate All Critical" red button.

**Response:**
```json
{
  "success": true,
  "escalatedCount": 6,
  "message": "6 critical issues escalated → Incident Daddy"
}
```

## 3. Real-time Live Feed

### `WS /ws/feed`
WebSocket endpoint that streams live global events for the dashboard's "Live Activity Feed" (bottom right).

**Event Payload:**
```json
{
  "event": "new_feed_item",
  "data": {
    "ico": "🚨",
    "color": "#ff4060",
    "title": "BankStatementService freq=654 → Incident Daddy triggered",
    "meta": "GH-90 · CloudWatch",
    "timestamp": "2026-04-08T19:10:00Z"
  }
}
```

> **REST Fallback:** `GET /api/feed?limit=10` can be used on first page load to populate the initial list before the WebSocket takes over.

## 4. Execution Graph Modal

### `GET /api/executions/{id}`
Loads the historical data or exact configuration for generating the node graph visualization when "Live Graph" or "Summary" is clicked.

**Response:**
```json
{
  "issueId": 104,
  "isIncident": false,
  "status": "completed", 
  "activePath": ["cw", "esc", "db", "sch", "sme", "bug", "plan", "gath", "code", "crit", "bbag", "rev", "airev", "jprf"],
  "completedSteps": [
    {
      "nodeId": "cw",
      "icon": "☁️",
      "name": "CloudWatch Parser",
      "desc": "Lambda extracts error fingerprint and routes to tracker",
      "durationMs": 1100,
      "logs": [
        { "type": "info", "title": "Log group: /aws/lambda/Service", "lines": ["Event: FilteredLogEvent"] }
      ]
    }
  ]
}
```

### `WS /ws/executions/{id}`
WebSocket channel for streaming live agent steps as they execute. Updates the visual status of nodes (`RUNNING`, `DONE`, `ERROR`) and dynamically appends to the log stream in real-time.

**Event Payload:**
```json
{
  "event": "execution_step_update",
  "data": {
    "nodeId": "plan",
    "state": "active",
    "logType": "tool",
    "logTitle": "planner.analyze_scope(issue)",
    "logLines": ["target_file: lambda_function.py", "patch_type: type_guard"]
  }
}
```

## 5. Authentication

### `POST /api/auth/login`
Validates user email and password credentials for access to the GrabHack dashboard.

**Request Body:**
```json
{
  "email": "name@domain.com",
  "password": "supersecretpassword123"
}
```

**Response:**
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "email": "name@domain.com",
    "role": "SRE"
  }
}
```

### `POST /api/auth/logout`
Invalidates the current session/token.

**Response:**
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```
