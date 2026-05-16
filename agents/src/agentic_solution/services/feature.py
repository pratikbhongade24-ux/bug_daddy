from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import FeatureAgentBundle, build_feature_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import FeatureRequest, FeatureResponse
from agentic_solution.execution import ExecutionLogger
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools
from agentic_solution.peer import PeerRuntimeClient


@dataclass(slots=True)
class FeatureDaddyRuntime:
    config: AppConfig
    tools: MCPToolBundle

    def _build_agents(self) -> FeatureAgentBundle:
        return build_feature_agents(
            self.config,
            tools={
                "jira": self.tools.jira_tools,
                "bitbucket": self.tools.bitbucket_tools,
                "github": self.tools.github_tools,
                "github_read_write": self.tools.github_read_write_tools,
            },
        )

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        agents = self._build_agents()
        logger = ExecutionLogger.from_payload(payload, "feature_daddy")
        request = FeatureRequest.model_validate(payload)

        if self.config.dry_run:
            started = logger.node_started("feat", "Feature Daddy", "Dry-run feature implementation")
            response = FeatureResponse(
                feature_name="dry_run",
                summary=(
                    "Dry run only. feature_daddy would analyse the PRD, design the architecture, "
                    "implement the code, and open a pull request."
                ),
                disposition="review_required",
                diagnostics=self.tools.diagnostics,
            )
            logger.node_completed("feat", "Feature Daddy", "Dry-run complete", started, response.summary)
            return response.model_dump()

        # Step 1: PRD Analysis
        started = logger.node_started("prd", "PRD Analyst", "Parse and structure the PRD", request.prd)
        prd_analysis_raw = str(agents.prd_analyst(_prd_analyst_prompt(request)))
        prd_analysis = _parse_json_safe(prd_analysis_raw)
        feature_name = prd_analysis.get("feature_name", "unnamed_feature")
        logger.node_completed("prd", "PRD Analyst", "PRD parsed", started, prd_analysis_raw)

        # Step 2: Architecture Design
        started = logger.node_started("arch", "Architect", "Design technical approach", prd_analysis_raw)
        architecture = str(agents.architect(_architect_prompt(request, prd_analysis_raw)))
        jira_key = _extract_tag(architecture, "JIRA_KEY")
        logger.node_completed("arch", "Architect", "Architecture designed", started, architecture)

        artifacts: list[dict[str, Any]] = [
            {"type": "prd_analysis", "system": "feature_daddy", "content": prd_analysis},
            {"type": "architecture", "system": "feature_daddy", "content": architecture},
        ]
        diagnostics: dict[str, Any] = {**self.tools.diagnostics}

        # Step 3: Implementation
        started = logger.node_started("impl", "Implementer", "Write feature code", architecture)
        implementation = str(agents.implementer(_implementer_prompt(request, prd_analysis_raw, architecture, jira_key)))
        logger.node_completed("impl", "Implementer", "Implementation complete", started, implementation)

        # Step 4: Critic
        started = logger.node_started("crit", "Critic", "Critique implementation", implementation)
        critique = str(agents.critic(_critic_prompt(request, prd_analysis_raw, implementation)))
        logger.node_completed("crit", "Critic", "Critique complete", started, critique)

        artifacts.extend([
            {"type": "implementation", "system": "feature_daddy", "content": implementation},
            {"type": "critique", "system": "feature_daddy", "content": critique},
        ])

        if "[CRITIQUE: REWORK]" in critique:
            response = FeatureResponse(
                feature_name=feature_name,
                summary="Implementation requires rework before review — critic identified unmet acceptance criteria.",
                disposition="rework_required",
                jira_key=jira_key,
                artifacts=artifacts,
                diagnostics=diagnostics,
            )
            return response.model_dump()

        # Step 5: Final Review
        started = logger.node_started("rev", "Reviewer", "Final feature review", implementation)
        review = str(agents.reviewer(_reviewer_prompt(request, prd_analysis_raw, architecture, implementation, critique, jira_key)))
        logger.node_completed("rev", "Reviewer", "Review complete", started, review)
        artifacts.append({"type": "review", "system": "feature_daddy", "content": review})

        pr_url = _extract_pr_url(review)
        disposition = "pull_request" if "[DECISION: APPROVE]" in review else "rework_required"
        summary = _first_non_empty_line(review)

        response = FeatureResponse(
            feature_name=feature_name,
            summary=summary,
            disposition=disposition,
            jira_key=jira_key,
            pr_url=pr_url,
            artifacts=artifacts,
            diagnostics=diagnostics,
        )
        return response.model_dump()


def build_runtime(config: AppConfig | None = None) -> FeatureDaddyRuntime:
    cfg = config or AppConfig.from_env()
    tools = load_mcp_tools(cfg)
    return FeatureDaddyRuntime(config=cfg, tools=tools)


# ---------- prompt builders ----------

def _prd_analyst_prompt(request: FeatureRequest) -> str:
    return f"""
Analyse the following PRD and extract the engineering specification.

PRD:
{request.prd}

Service:
{request.service_name or "Not specified"}

Repository:
{request.repository or "Not specified"}

Additional context:
{request.kb_context or "None"}
""".strip()


def _architect_prompt(request: FeatureRequest, prd_analysis: str) -> str:
    return f"""
Design the technical approach for this feature.

PRD Analysis:
{prd_analysis}

Service:
{request.service_name or "Not specified"}

Repository:
{request.repository or "Not specified"}

Additional context:
{request.kb_context or "None"}
""".strip()


def _implementer_prompt(
    request: FeatureRequest,
    prd_analysis: str,
    architecture: str,
    jira_key: str | None,
) -> str:
    return f"""
Implement the feature according to the architecture and PRD analysis.

PRD Analysis:
{prd_analysis}

Architecture:
{architecture}

Repository:
{request.repository or "Not specified"}

Jira key (use for branch name):
{jira_key or "Not assigned"}
""".strip()


def _critic_prompt(request: FeatureRequest, prd_analysis: str, implementation: str) -> str:
    return f"""
Critique the feature implementation against the PRD acceptance criteria.

PRD Analysis:
{prd_analysis}

Implementation:
{implementation}
""".strip()


def _reviewer_prompt(
    request: FeatureRequest,
    prd_analysis: str,
    architecture: str,
    implementation: str,
    critique: str,
    jira_key: str | None,
) -> str:
    return f"""
Perform the final review of this feature implementation.

PRD Analysis:
{prd_analysis}

Architecture:
{architecture}

Implementation:
{implementation}

Critic Review:
{critique}

Jira key:
{jira_key or "Not assigned"}

Repository:
{request.repository or "Not specified"}
""".strip()


# ---------- helpers ----------

def _parse_json_safe(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"raw": raw}


def _extract_tag(text: str, tag: str) -> str | None:
    match = re.search(rf"\[{tag}:\s*([^\]]+)\]", text)
    return match.group(1).strip() if match else None


def _extract_pr_url(text: str) -> str | None:
    match = re.search(r"https?://\S+pull[s]?/\d+", text)
    return match.group(0) if match else None


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("["):
            return stripped
    return text[:200]
