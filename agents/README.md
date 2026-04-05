# Agentic Solution

This folder now follows the bifurcated architecture from your latest diagram:

- `incident_daddy`
- `bug_daddy`
- `reviewer_daddy`
- shared `sme_agent`

Each folder under `apps/` is now a self-contained deployable code base. That means you can point AgentCore at `apps/incident_daddy`, `apps/bug_daddy`, `apps/reviewer_daddy`, or `apps/sme_agent` independently, and each folder already contains its own local `agentic_solution` package plus its own `pyproject.toml`.

The repo-root `src/agentic_solution/` remains as the source mirror used to keep the four app copies aligned, but it is not required at deployment time if you deploy from within an `apps/*` directory.

## Topology

Flow:

1. Triggers arrive at `incident_daddy`.
2. `incident_daddy` performs triage, Slack/Jira coordination, and decides whether to hand off.
3. `bug_daddy` owns remediation planning, evidence gathering, coding, and critique.
4. `reviewer_daddy` is the final AI gate for PR creation or Jira-only closure.
5. `sme_agent` is a shared agent-backed knowledge layer used by `incident_daddy` and `bug_daddy`.

The external system boundary is still:

- Slack MCP
- Jira MCP
- Bitbucket MCP

## Structure

- `apps/incident_daddy/main.py`: AgentCore entrypoint for incident triage.
- `apps/bug_daddy/main.py`: AgentCore entrypoint for remediation.
- `apps/reviewer_daddy/main.py`: AgentCore entrypoint for review and PR/Jira actions.
- `apps/sme_agent/main.py`: AgentCore entrypoint for shared SME reasoning.
- `apps/*/pyproject.toml`: Per-app dependencies for independent packaging.
- `apps/*/agentic_solution/`: Self-contained local package copied into each app folder.
- `src/agentic_solution/contracts.py`: Shared handoff schemas.
- `src/agentic_solution/config.py`: Bedrock, MCP, and peer-runtime config.
- `src/agentic_solution/mcp.py`: MCP loading and tool allowlisting.
- `src/agentic_solution/peer.py`: HTTP handoff client for peer AgentCore runtimes.
- `src/agentic_solution/services/`: Runtime implementations.

## Local Setup

```bash
cd agents
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Defaults:

- model: `anthropic.claude-haiku-4-5-20251001-v1:0`
- region resolution order: `AWS_REGION` -> `AWS_DEFAULT_REGION` -> local boto3/AWS CLI session -> `us-west-2`

Populate `.env` with:

- the real Slack/Jira/Bitbucket MCP server commands and tool names
- the deployed URLs for `BUG_DADDY_URL`, `REVIEWER_DADDY_URL`, and `SME_AGENT_URL`

## Deployable Apps

Each app is deployed separately with AgentCore using its own folder as the code base. Example:

```bash
cd apps/sme_agent
agentcore configure -e main.py
agentcore deploy

cd ../reviewer_daddy
agentcore configure -e main.py
agentcore deploy

cd ../bug_daddy
agentcore configure -e main.py
agentcore deploy

cd ../incident_daddy
agentcore configure -e main.py
agentcore deploy
```

After deployment, wire the peer URLs back into `.env` or your deployment environment:

```bash
BUG_DADDY_URL=https://...
REVIEWER_DADDY_URL=https://...
SME_AGENT_URL=https://...
```

Recommended deployment order:

1. `sme_agent`
2. `reviewer_daddy`
3. `bug_daddy`
4. `incident_daddy`

That order matches the dependency graph.

## Runtime Contracts

`incident_daddy` input:

```json
{
  "prompt": "P1 outage in checkout",
  "source": "slack",
  "trigger": "microservice_logs",
  "service_name": "checkout-service",
  "repository": "org/checkout-service",
  "logs": ["java.lang.NullPointerException at CheckoutFlow:42"],
  "telemetry": {"region": "ap-south-1"},
  "kb_context": "Runbook excerpt or SOP text",
  "metadata": {"incident_channel": "checkout-p1"}
}
```

`bug_daddy` receives a richer handoff payload that includes `incident_summary`, `incident_severity`, and `incident_artifacts`.

`reviewer_daddy` receives a review package containing:

- issue context
- remediation plan
- gathered context
- SME guidance
- log analysis
- fix proposal
- critique

`sme_agent` receives:

```json
{
  "question": "What SOP or ownership info matters here?",
  "requested_by": "incident_daddy",
  "context": {
    "prompt": "P1 outage in checkout",
    "service_name": "checkout-service"
  }
}
```

## Implementation Notes

- `incident_daddy` and `bug_daddy` call `sme_agent` over HTTP using `peer.py`.
- `incident_daddy` can hand off to `bug_daddy`.
- `bug_daddy` can hand off to `reviewer_daddy`.
- In `DRY_RUN=true`, each runtime validates the payload and returns a safe simulated response without invoking peer runtimes or MCP tools.
- The current `sme_agent` is agent-backed and contract-ready, but it does not yet connect to a real vector DB. It uses inline context until you wire a retrieval backend behind it.
- Because each `apps/*` directory is self-contained, there are no deployment-time imports from the repo root when you package an app folder independently.
