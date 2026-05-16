from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import ReviewerAgentBundle, build_reviewer_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import ReviewRequest, ReviewResponse
from agentic_solution.execution import ExecutionLogger
from agentic_solution.heuristics import infer_review_disposition
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools

_PR_URL_RE = re.compile(r"https?://[^\s)>\"]+/pull(?:-requests?)?/\d+")


@dataclass(slots=True)
class ReviewerDaddyRuntime:
    config: AppConfig
    tools: MCPToolBundle

    def _build_agents(self) -> ReviewerAgentBundle:
        """Build fresh agent instances per invocation — Strands Agents are stateful and not concurrency-safe."""
        return build_reviewer_agents(
            self.config,
            tools={
                "slack": [],
                "jira": self.tools.jira_tools, 
                "bitbucket": self.tools.bitbucket_tools,
                "github": self.tools.github_tools,
                "github_read_write": self.tools.github_read_write_tools
            },
        )

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        agents = self._build_agents()
        logger = ExecutionLogger.from_payload(payload, "reviewer_daddy")
        request = ReviewRequest.model_validate(payload)

        if self.config.dry_run:
            started = logger.node_started("rev", "Reviewer Daddy", "Dry-run final AI review")
            response = ReviewResponse(
                disposition="pull_request",
                summary=(
                    "Dry run only. reviewer_daddy would perform the final AI review, then create "
                    "the pull request in Bitbucket and update Jira if the proposal passed."
                ),
                diagnostics=self.tools.diagnostics,
            )
            logger.node_completed("rev", "Reviewer Daddy", "Dry-run final AI review complete", started, response.summary)
            return response.model_dump()

        started = logger.node_started("airev", "AI Reviewer", "Perform final AI review", request.fix_proposal)
        review_text = str(agents.reviewer(_review_prompt(request)))
        logger.node_completed("airev", "AI Reviewer", "Final AI review complete", started, review_text)
        disposition = infer_review_disposition(review_text)
        artifacts = []

        pr_url: str | None = None
        if disposition == "pull_request":
            match = _PR_URL_RE.search(review_text)
            if match:
                pr_url = match.group(0)
                logger.map_pull_request_resolution(pr_url)
            logger.emit(
                "node.completed",
                node_id="jprf",
                node_name="PR & Update",
                status="succeeded",
                level="info",
                title="Pull request path approved",
                output_summary=review_text,
            )
            artifacts.append({"type": "pull_request", "system": "bitbucket", "content": review_text})
        elif disposition == "jira_ticket":
            logger.emit(
                "node.completed",
                node_id="jrf",
                node_name="Jira Update",
                status="succeeded",
                level="info",
                title="Jira ticket path approved",
                output_summary=review_text,
            )
            artifacts.append({"type": "jira_ticket", "system": "jira", "content": review_text})
        else:
            logger.emit(
                "node.completed",
                node_id="crit",
                node_name="Critic Agent",
                status="succeeded",
                level="warning",
                title="Rework required",
                output_summary=review_text,
            )
            artifacts.append({"type": "rework", "system": "reviewer_daddy", "content": review_text})

        response = ReviewResponse(
            disposition=disposition,
            summary=review_text,
            pr_url=pr_url,
            artifacts=artifacts,
            diagnostics=self.tools.diagnostics,
        )
        return response.model_dump()


def build_runtime(config: AppConfig | None = None) -> ReviewerDaddyRuntime:
    cfg = config or AppConfig.from_env()
    tools = load_mcp_tools(cfg)
    return ReviewerDaddyRuntime(config=cfg, tools=tools)


def _review_prompt(request: ReviewRequest) -> str:
    return f"""
Perform the final review for this remediation package.

Prompt:
{request.issue.prompt}

Service:
{request.issue.service_name}

Repository:
{request.issue.repository}

Jira:
{request.metadata.get("jira_key") or request.metadata.get("resolution_jira") or "None provided"}

Plan:
{request.strategy_plan}

Context summary:
{request.context_analysis}

SME guidance:
{request.sme_guidance}

Fix proposal:
{request.fix_proposal}

Critique:
{request.critique}

Metadata:
{request.metadata}
""".strip()
