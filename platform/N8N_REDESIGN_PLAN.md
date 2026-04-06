# N8N-Like Orchestration Redesign Plan

## Goal
Transform the current `platform/frontend` issue experience from a card-based observability page into a true workflow execution surface that feels much closer to `n8n`:

- graph-first, not card-first
- execution-state visible at a glance
- node selection drives the right-side inspector
- bottom console shows the full live session
- every agent step, handoff, tool call, token count, latency, and artifact is inspectable

This is not a cosmetic tweak. It is a structural UI and backend telemetry redesign.

## Current Gap
The current implementation is still fundamentally a dashboard page:

- [`issue-detail-client.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/issue-detail-client.tsx) stacks sections vertically
- [`run-canvas.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/run-canvas.tsx) renders summary cards, not an actual execution graph
- [`run-terminal.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/run-terminal.tsx) is a plain log box, not a real execution console
- [`agent-session-list.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/agent-session-list.tsx) groups events, but does not behave like node-scoped execution inspection
- backend events in [`orchestration.py`](/Users/danishgada/vscode/personal/bug_daddy/platform/backend/app/services/orchestration.py) are useful, but still too flat for a true graph inspector

## Redesign Principles
The new issue screen should behave like an execution IDE.

### 1. Graph Is The Primary Surface
The main thing the user sees should be the workflow graph, not summary cards.

### 2. Execution Feels Alive
Active nodes pulse, edges animate during handoffs, logs stream continuously, and the selected node updates in place.

### 3. Inspection Is Localized
Clicking a node should reveal everything about that node in a side inspector:

- reasoning summary
- tool calls
- tool results
- token usage
- latency
- input payload
- output payload
- artifacts emitted
- handoffs in and out

### 4. Global Console Exists
There should be a bottom session console that shows the entire run across all agents with filters and tabs.

### 5. Dense But Calm
This should feel closer to operator tooling than marketing UI:

- darker execution workspace
- lighter shell around it
- crisp borders
- resizable panels
- monospace where needed
- minimal decorative surfaces

## Target Screen Architecture
The issue detail page should be rebuilt into a 4-region layout.

### Top Toolbar
Purpose:

- run identity
- issue identity
- current status
- elapsed time
- severity
- service
- controls

Controls:

- retry
- replay
- cancel
- pause stream
- follow live
- export trace JSON

### Left Rail
Purpose:

- issue summary
- run history
- trigger source
- quick filters

Contents:

- issue title and external ID
- severity and service
- run selector dropdown
- trigger metadata
- artifact shortcuts
- connector health mini panel

### Center Canvas
Purpose:

- the main workflow editor-like graph

This area should use a real node-canvas library and support:

- zoom
- pan
- fit-to-run
- active node focus
- edge animation
- step badges
- node status coloring
- node execution duration
- tool count per node
- token count per node

### Right Inspector
Purpose:

- selected node details

Tabs:

- `Overview`
- `Reasoning`
- `Tools`
- `I/O`
- `Artifacts`
- `Metrics`
- `Raw`

### Bottom Console
Purpose:

- session-wide logs and execution traces

Tabs:

- `Events`
- `Terminal`
- `Tool Calls`
- `Handoffs`
- `Tokens`
- `Errors`
- `Raw JSON`

## Frontend Work Plan

## Phase 1: Replace The Current Layout
Files to change:

- [`issue-detail-client.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/issue-detail-client.tsx)
- [`globals.css`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/app/globals.css)

What will change:

- remove the current vertical section flow as the primary experience
- replace it with a full-height app layout for the issue detail page
- make the issue page feel like a workflow workstation
- keep evidence and artifacts, but demote them into inspector tabs instead of standalone page sections

Deliverable:

- the issue screen becomes a real split-pane application

## Phase 2: Build A Real Workflow Canvas
Files to add:

- `platform/frontend/components/run-workbench.tsx`
- `platform/frontend/components/workflow-canvas.tsx`
- `platform/frontend/components/workflow-node.tsx`
- `platform/frontend/components/workflow-edge.tsx`
- `platform/frontend/components/workbench-toolbar.tsx`
- `platform/frontend/components/run-history-rail.tsx`

Files to replace or retire:

- [`run-canvas.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/run-canvas.tsx)

Implementation details:

- move from summary cards to `React Flow`
- create fixed node positions for:
  - `trigger_router`
  - `incident_daddy`
  - `sme_agent`
  - `bug_daddy`
  - `reviewer_daddy`
  - `platform`
- support skipped branches:
  - bugs that start without `incident_daddy`
- animate edges when a handoff event is active
- visually distinguish:
  - idle
  - queued
  - running
  - completed
  - failed
  - blocked
- show mini metrics directly inside nodes:
  - event count
  - tool count
  - tokens
  - duration

Deliverable:

- the center area looks like a workflow engine, not a dashboard card grid

## Phase 3: Add Node-Scoped Inspector
Files to add:

- `platform/frontend/components/node-inspector.tsx`
- `platform/frontend/components/node-inspector-tabs.tsx`
- `platform/frontend/components/tool-call-table.tsx`
- `platform/frontend/components/token-usage-panel.tsx`
- `platform/frontend/components/io-payload-viewer.tsx`

Current component impact:

- [`agent-session-list.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/agent-session-list.tsx) should be retired or broken apart into inspector panels

Behavior:

- clicking a node selects it
- inspector shows only that node’s session
- default selected node is:
  - the currently running node
  - otherwise the last completed node
- inspector tabs expose:
  - summary
  - reasoning summary
  - tool invocations
  - tool outputs
  - token usage
  - raw JSON

Deliverable:

- inspection becomes contextual and interactive

## Phase 4: Build A Real Session Console
Files to add:

- `platform/frontend/components/run-console.tsx`
- `platform/frontend/components/console-toolbar.tsx`
- `platform/frontend/components/console-event-table.tsx`
- `platform/frontend/components/console-json-view.tsx`

Files to replace:

- [`run-terminal.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/run-terminal.tsx)

Behavior:

- bottom dock with resize handle
- tabs for different stream types
- filter by:
  - agent
  - event type
  - tool name
  - severity
- search over logs
- auto-follow toggle
- timestamp precision
- copy JSON
- export trace

Terminal mode should show entries like:

- `agent_thought`
- `tool_call`
- `tool_result`
- `agent_handoff`
- `review_note`
- `resolution`

Deliverable:

- the run console becomes a real debugging surface

## Phase 5: Introduce Resizable Pane System
Files to add:

- `platform/frontend/components/pane-layout.tsx`

Need:

- horizontal resize between left rail, canvas, right inspector
- vertical resize for bottom console
- persisted pane sizes in local storage

Deliverable:

- the issue page behaves like an application workspace

## Phase 6: Establish A Dark Execution Theme
Files to change:

- [`globals.css`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/app/globals.css)

Design direction:

- keep the overview page minimal and brand-forward
- make the issue execution page darker and more tool-like
- use:
  - dark graphite background for canvas
  - slightly lighter inspector and console panels
  - clear node accent states
  - subtle grid background
  - strong monospace for logs

Why:

- n8n-like workspaces are about operational focus, not hero cards

Deliverable:

- execution view feels serious and legible under dense information

## Phase 7: Improve Motion And Live State
Files impacted:

- new canvas and console components

Add:

- animated handoff edges
- node pulse while running
- stream-in highlight for new events
- selected-node focus ring
- soft transitions for status changes
- event badges that increment live

Deliverable:

- the run feels alive during demos

## Backend Work Plan

## Phase 8: Move From Flat Events To Structured Execution Spans
Files to change:

- [`orchestration.py`](/Users/danishgada/vscode/personal/bug_daddy/platform/backend/app/services/orchestration.py)
- [`models.py`](/Users/danishgada/vscode/personal/bug_daddy/platform/backend/app/models.py)
- [`schemas.py`](/Users/danishgada/vscode/personal/bug_daddy/platform/backend/app/schemas.py)

Current problem:

- events are flat and useful for a timeline
- a graph inspector needs richer node/session/span structure

What to add per event:

- `span_id`
- `parent_span_id`
- `session_id`
- `agent_name`
- `step_name`
- `phase`
- `started_at`
- `ended_at`
- `duration_ms`
- `input_payload`
- `output_payload`
- `tool_name`
- `tool_type`
- `tool_args`
- `tool_result`
- `token_usage.input_tokens`
- `token_usage.output_tokens`
- `token_usage.total_tokens`
- `cost_usd`
- `retry_count`
- `error_code`
- `error_message`
- `handoff_from`
- `handoff_to`

Deliverable:

- frontend can reconstruct a true execution graph and deep inspector

## Phase 9: Create Graph-Oriented APIs
Files to change:

- [`issues.py`](/Users/danishgada/vscode/personal/bug_daddy/platform/backend/app/api/issues.py)

New endpoints to add:

- `GET /api/issues/{issue_id}/graph`
- `GET /api/runs/{run_id}/console`
- `GET /api/runs/{run_id}/agents/{agent_name}`
- `GET /api/runs/{run_id}/tokens`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/trace`

What `graph` should return:

- node definitions
- edge definitions
- execution status per node
- metrics per node
- currently active node
- selected default node

Deliverable:

- the frontend stops deriving everything from one oversized issue payload

## Phase 10: Improve WebSocket Protocol
Files to change:

- realtime services
- issue page client listeners

Current problem:

- client just refreshes whole issue detail on each event

What to change:

- send typed messages:
  - `run.event`
  - `run.node.updated`
  - `run.console.append`
  - `run.metrics.updated`
  - `run.completed`
- patch local UI state incrementally instead of full refetch

Deliverable:

- smoother live execution and much less jitter

## Phase 11: Add Persisted Console Slices
Need:

- paginated event retrieval
- filtered queries by node and event type
- stable ordering
- raw trace export

Deliverable:

- console remains usable for long runs

## Data And Interaction Model

## Node States
Every node should explicitly support:

- `idle`
- `queued`
- `running`
- `success`
- `failed`
- `blocked`
- `skipped`

## Event Types
We should keep and normalize:

- `trigger_received`
- `agent_thought`
- `tool_call`
- `tool_result`
- `agent_step`
- `agent_handoff`
- `review_note`
- `resolution`
- `error`
- `retry`

## Reasoning Display
We should show reasoning summaries, not unsafe hidden internals.

Visible:

- concise reasoning summary
- why this tool was called
- what evidence mattered
- why the handoff occurred

Not required:

- raw private chain-of-thought dumps

## Concrete File-Level Execution Plan

## Frontend
1. Rebuild [`issue-detail-client.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/issue-detail-client.tsx) into a workspace shell.
2. Replace [`run-canvas.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/run-canvas.tsx) with a React Flow canvas.
3. Replace [`run-terminal.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/run-terminal.tsx) with a docked multi-tab console.
4. Remove the current standalone [`agent-session-list.tsx`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/components/agent-session-list.tsx) pattern and fold that data into the node inspector.
5. Split issue-page-specific styling out of [`globals.css`](/Users/danishgada/vscode/personal/bug_daddy/platform/frontend/app/globals.css) into clearer workspace classes.
6. Add selection state, console filters, and pane persistence.

## Backend
1. Expand run event shape in [`orchestration.py`](/Users/danishgada/vscode/personal/bug_daddy/platform/backend/app/services/orchestration.py).
2. Extend DB models and response schemas for node/session/span metadata.
3. Add graph and console-oriented endpoints in [`issues.py`](/Users/danishgada/vscode/personal/bug_daddy/platform/backend/app/api/issues.py).
4. Change websocket updates from full refresh triggers to typed incremental events.
5. Add raw trace export and token aggregation endpoints.

## What Will Make It Feel Credibly N8N-Like
These are the non-negotiables.

### Must Have
- a true node graph canvas
- selected node inspector on the right
- bottom log console
- animated execution flow
- node-level inputs and outputs
- tool calls visible under each node
- token and latency metrics per node
- run history and replay controls

### Nice To Have
- minimap
- keyboard shortcuts
- step pinning
- fullscreen canvas mode
- compare two runs side-by-side
- diff previous run vs current run

## Acceptance Criteria
We should consider this redesign successful only if all of these are true:

1. A first-time viewer immediately recognizes the issue page as a workflow execution UI, not a dashboard.
2. During a live run, the active node and current handoff are obvious without reading text blocks.
3. Clicking any node reveals its tools, reasoning summary, token usage, and I/O in one place.
4. The bottom console is useful enough to debug a failed run without leaving the page.
5. The UI can handle long runs without re-rendering the whole page on every event.
6. The issue detail page feels operationally dense and deliberate rather than decorative.

## Recommended Implementation Order
1. Data contract expansion in backend
2. Graph API and websocket protocol
3. New issue workspace shell
4. React Flow canvas
5. Node inspector
6. Console dock
7. Motion, filters, persistence, polish

## Immediate Next Step
The next coding pass should not tweak the current cards again.

It should start by:

1. introducing a dedicated issue workbench layout
2. adding a graph-specific API payload
3. replacing the current run canvas with a real node editor surface

