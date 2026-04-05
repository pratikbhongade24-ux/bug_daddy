from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import ReviewerAgentBundle, build_reviewer_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import ReviewRequest, ReviewResponse
from agentic_solution.heuristics import infer_review_disposition
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools


@dataclass(slots=True)
class ReviewerDaddyRuntime:
    config: AppConfig
    tools: MCPToolBundle
    agents: ReviewerAgentBundle

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = ReviewRequest.model_validate(payload)

        if self.config.dry_run:
            response = ReviewResponse(
                disposition="pull_request",
                summary=(
                    "Dry run only. reviewer_daddy would perform the final AI review, then create "
                    "the pull request in Bitbucket and update Jira if the proposal passed."
                ),
                diagnostics=self.tools.diagnostics,
            )
            return response.model_dump()

        review_text = str(self.agents.reviewer(_review_prompt(request)))
        disposition = infer_review_disposition(review_text)
        artifacts = []

        if disposition == "pull_request":
            artifacts.append({"type": "pull_request", "system": "bitbucket", "content": review_text})
        elif disposition == "jira_ticket":
            artifacts.append({"type": "jira_ticket", "system": "jira", "content": review_text})
        else:
            artifacts.append({"type": "rework", "system": "reviewer_daddy", "content": review_text})

        response = ReviewResponse(
            disposition=disposition,
            summary=review_text,
            artifacts=artifacts,
            diagnostics=self.tools.diagnostics,
        )
        return response.model_dump()


def build_runtime(config: AppConfig | None = None) -> ReviewerDaddyRuntime:
    cfg = config or AppConfig.from_env()
    tools = load_mcp_tools(cfg)
    agents = build_reviewer_agents(
        cfg,
        tools={"slack": tools.slack_tools, "jira": tools.jira_tools, "bitbucket": tools.bitbucket_tools},
    )
    return ReviewerDaddyRuntime(config=cfg, tools=tools, agents=agents)


def _review_prompt(request: ReviewRequest) -> str:
    return f"""
Perform the final review for this remediation package.

Prompt:
{request.issue.prompt}

Service:
{request.issue.service_name}

Repository:
{request.issue.repository}

Plan:
{request.plan}

Context summary:
{request.context_summary}

SME guidance:
{request.sme_guidance}

Log analysis:
{request.log_analysis}

Fix proposal:
{request.fix_proposal}

Critique:
{request.critique}

Metadata:
{request.metadata}
""".strip()
