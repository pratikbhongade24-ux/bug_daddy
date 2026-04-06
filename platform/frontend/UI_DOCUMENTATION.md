# Bug Daddy Platform - UI Documentation

## Overview

Bug Daddy Platform is a **control room UI** for trigger ingestion, multi-agent orchestration, and autonomous code maintenance. The entire experience lives on **two pages**: a single consolidated dashboard and an issue detail drill-down.

---

## Tech Stack

| Layer     | Technology                                   |
| --------- | -------------------------------------------- |
| Framework | Next.js (App Router), TypeScript, React      |
| Fonts     | Sora (display), Manrope (body)               |
| Styling   | Custom BEM CSS (globals.css)                  |
| Real-time | WebSockets (`/ws/dashboard`, `/ws/runs/:id`) |
| API       | REST via `lib/api.ts` (default `localhost:8000`) |

---

## Page Structure

```
AppShell (header + "Dashboard" nav link)
  ├── /                  Dashboard (everything in one view)
  └── /issues/[issueId]  Issue Detail (drill-down)
```

---

## Page 1: Dashboard (`/`)

A single page that consolidates all operational views. Fetches dashboard summary, scenarios, and triggers on the server, then hydrates `DashboardLiveClient` for real-time updates.

### Layout (top to bottom)

| Row | Left Column | Right Column |
| --- | ----------- | ------------ |
| **Hero** | Tagline, system description, 3 highlight chips (active agent, resolved count, reviewer success rate) | Live signal indicator + Orchestration Board (5-node agent pipeline) |
| **Metrics** | 6 `MetricCard` tiles spanning full width: Issues resolved, Running, Total triggers, Auto PRs, Mean resolve time, Engineer hours saved | |
| **Row 1** | **Issue Radar** - table of recent issues (title, service, severity, status, agent) linking to detail | **Trust Layer** - 3 insight cards: guardrail state, second-pair-of-eyes count, reviewer confidence |
| **Row 2** | **Scenario Library** - launchable demo scenario cards (source, severity, title, summary, service, recurrence, launch button) | **Signal Mix** - bar charts for trigger source distribution + service hotspots |
| **Row 3** | **Reasoning Log** - numbered timeline of recent system events | **Runtime Fleet** - agent runtime cards (name, status, ARN, version, latency, success rate) + connector health cards |
| **Row 4** | **Trigger Feed** - recent raw trigger events with JSON payload (full width, shown only when triggers exist) | |

### Key Behaviors

- **WebSocket** at `/ws/dashboard` listens for `dashboard_refresh` events, then refetches via REST.
- **Scenario launch** posts to `/api/triggers/simulate` and redirects to the new issue detail page.
- Heartbeat ping every 15 seconds.

---

## Page 2: Issue Detail (`/issues/[issueId]`)

A deep-dive into a single issue. Server-fetches `IssueDetail`, hydrates `IssueDetailClient` for live run updates.

### Layout (top to bottom)

| Section | Content |
| ------- | ------- |
| **Issue Hero** | Back link, external ID, title, description, meta (status, severity, service, type, confidence %). Stat chips: blast radius, guardrail state, recurrence. Action buttons: Retry / Replay. |
| **Invocation Inspector** | Left: `RunCanvas` (6-node execution graph with event/tool/token counts per node). Right: `RunTerminal` (scrollable monospace log with timestamps, node names, tool calls, handoffs, token usage). |
| **Detail Grid** | Left: **Agent Sessions** - per-agent session cards with event lists. Right: **Artifacts** - generated outputs (PRs, Jira tickets, Slack messages). |
| **Reasoning Timeline** | Flat chronological feed of all run events. |
| **Evidence Grid** | Left: **Evidence Bundle** - logs, telemetry JSON, SME context. Right: **Trigger Payload** - source payload JSON + trigger history. |

### Key Behaviors

- **WebSocket** at `/ws/runs/:runId` listens for `run_event` messages, then refetches the full issue.
- **Retry** preserves history; **Replay** creates a fresh run from the same scenario.

---

## Agent Pipeline

Visualized in both the OrchestrationBoard (dashboard) and RunCanvas (issue detail):

```
1. Trigger Router   ->  Normalize and route incoming signals
2. Incident Daddy   ->  Triage severity, Slack/Jira/escalation
3. SME Agent        ->  SOPs, ownership, historical guidance
4. Bug Daddy        ->  Plan, gather code/logs, fix, critique
5. Reviewer Daddy   ->  Final review, PR or Jira-only resolution
   (6. Platform)    ->  Finalize artifacts (RunCanvas only)
```

---

## Components

| Component | Purpose |
| --------- | ------- |
| **AppShell** | Site header, nav, ambient background, main content wrapper |
| **DashboardLiveClient** | Full dashboard body with WebSocket, scenario launch, all sections |
| **IssueDetailClient** | Full issue detail body with WebSocket, retry/replay actions |
| **OrchestrationBoard** | 5-node horizontal pipeline with active/completed/idle states |
| **MetricCard** | Stat tile with label, value, accent color, hint |
| **StatusPill** | Colored badge mapping statuses to tones (green/blue/yellow/red/gray) |
| **SectionCard** | Card wrapper with eyebrow, title, optional subtitle, children |
| **IssueTable** | Linked issue rows with severity/status pills |
| **RunCanvas** | n8n-style 6-node execution graph with per-node metrics |
| **RunTerminal** | Monospace log viewer, auto-scrolls, shows tool calls/handoffs/tokens |
| **AgentSessionList** | Groups events by pipeline node, shows session-level metrics |

### Unused Workbench Components

A secondary IDE-style layout exists but is not yet routed:

| Component | Purpose |
| --------- | ------- |
| **RunWorkbench** | Full-screen 3-column layout (history rail, canvas+console, inspector) |
| **WorkflowCanvas** | React Flow interactive node graph |
| **RunHistoryRail** | Left sidebar listing past runs |
| **RunConsole** | Bottom panel with Terminal/Events/Tool Calls/Tokens tabs |
| **NodeInspector** | Right sidebar with node details and reasoning |
| **WorkbenchToolbar** | Top bar with issue ID, run status, pause/cancel |

> These use Tailwind utility classes (separate from main BEM CSS) and contain static/mock data.

---

## API Endpoints

| Function | Method | Endpoint | Returns |
| -------- | ------ | -------- | ------- |
| `getDashboardSummary` | GET | `/api/dashboard/summary` | `DashboardSummary` |
| `getScenarios` | GET | `/api/triggers/scenarios` | `Scenario[]` |
| `getIssues` | GET | `/api/issues` | `Issue[]` |
| `getIssueDetail` | GET | `/api/issues/:id` | `IssueDetail` |
| `getAgents` | GET | `/api/agents` | `AgentRuntime[]` |
| `getTriggers` | GET | `/api/triggers` | `TriggerEvent[]` |
| `launchScenario` | POST | `/api/triggers/simulate` | `{ issue_id, run_id }` |
| `retryIssue` | POST | `/api/issues/:id/retry` | `{ issue_id, run_id }` |
| `replayIssue` | POST | `/api/issues/:id/replay` | `{ issue_id, run_id }` |

---

## Component Tree

```
RootLayout
  └── AppShell
        ├── [/] OverviewPage
        │     └── DashboardLiveClient (WebSocket)
        │           ├── OrchestrationBoard
        │           ├── MetricCard (x6)
        │           ├── IssueTable -> StatusPill
        │           ├── SectionCard (x6 wrappers)
        │           ├── StatusPill (various)
        │           └── trigger-feed (inline)
        │
        └── [/issues/:id] IssueDetailPage
              └── IssueDetailClient (WebSocket)
                    ├── RunCanvas -> StatusPill
                    ├── RunTerminal
                    ├── AgentSessionList -> StatusPill
                    └── SectionCard (x5 wrappers)
```
