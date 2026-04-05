from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import BugAgentBundle, build_bug_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import BugRequest, BugResponse, IssueContext, ReviewRequest
from agentic_solution.heuristics import is_non_code_resolution
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools
from agentic_solution.peer import PeerInvocationError, PeerRuntimeClient


@dataclass(slots=True)
class BugDaddyRuntime:
    config: AppConfig
    tools: MCPToolBundle
    agents: BugAgentBundle
    peers: PeerRuntimeClient

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = BugRequest.model_validate(payload)
        sme_summary, sme_diagnostics = self._query_sme(request)

        if self.config.dry_run:
            response = BugResponse(
                summary=(
                    "Dry run only. bug_daddy would plan the remediation, gather evidence, "
                    "propose a fix, and optionally hand off to reviewer_daddy."
                ),
                resolution_kind="review_required",
                diagnostics={**self.tools.diagnostics, "sme_agent": sme_diagnostics},
            )
            return response.model_dump()

        orchestration = str(self.agents.orchestrator(_orchestrator_prompt(request, sme_summary)))
        planner = str(self.agents.planner(_planner_prompt(request, orchestration)))
        gatherer = str(self.agents.gatherer(_gatherer_prompt(request, orchestration, sme_summary)))
        log_analysis = str(self.agents.log_analyser(_log_prompt(request, gatherer)))
        coder = str(self.agents.coder(_coder_prompt(request, planner, gatherer, sme_summary, log_analysis)))
        critic = str(self.agents.critic(_critic_prompt(request, coder)))

        diagnostics: dict[str, Any] = {**self.tools.diagnostics, "sme_agent": sme_diagnostics}
        artifacts: list[dict[str, Any]] = [
            {"type": "bug_orchestration", "system": "bug_daddy", "content": orchestration},
            {"type": "remediation_plan", "system": "bug_daddy", "content": planner},
            {"type": "gathered_context", "system": "bug_daddy", "content": gatherer},
            {"type": "log_analysis", "system": "bug_daddy", "content": log_analysis},
            {"type": "fix_proposal", "system": "bug_daddy", "content": coder},
            {"type": "critique", "system": "bug_daddy", "content": critic},
        ]

        if is_non_code_resolution(orchestration, coder, critic):
            summary = (
                "Non-code resolution identified. Create or update Jira with the operational action "
                "instead of sending the issue to reviewer_daddy."
            )
            artifacts.append({"type": "jira_ticket", "system": "jira", "content": summary})
            response = BugResponse(
                summary=summary,
                resolution_kind="jira_ticket",
                artifacts=artifacts,
                diagnostics=diagnostics,
            )
            return response.model_dump()

        review_request = ReviewRequest(
            issue=IssueContext(
                prompt=request.prompt,
                source=request.source,
                service_name=request.service_name,
                repository=request.repository,
                logs=request.logs,
                telemetry=request.telemetry,
                kb_context=request.kb_context,
                metadata=request.metadata,
            ),
            plan=planner,
            context_summary=gatherer,
            sme_guidance=sme_summary,
            log_analysis=log_analysis,
            fix_proposal=coder,
            critique=critic,
            metadata={
                "incident_summary": request.incident_summary,
                "incident_severity": request.incident_severity,
            },
        )

        review_payload = review_request.model_dump()
        artifacts.append(
            {"type": "review_handoff_request", "system": "reviewer_daddy", "content": review_payload}
        )

        if not self.config.reviewer_daddy.enabled:
            diagnostics["reviewer_daddy"] = {"status": "disabled"}
            response = BugResponse(
                summary="Technical remediation prepared and waiting for reviewer_daddy.",
                resolution_kind="review_required",
                review_request=review_payload,
                artifacts=artifacts,
                diagnostics=diagnostics,
            )
            return response.model_dump()

        try:
            review_response = self.peers.invoke(self.config.reviewer_daddy, review_payload)
            artifacts.append(
                {
                    "type": "review_handoff_response",
                    "system": "reviewer_daddy",
                    "content": review_response,
                }
            )
            resolution_kind = str(review_response.get("disposition", "review_required"))
            summary = str(review_response.get("summary", "reviewer_daddy returned no summary."))
            response = BugResponse(
                summary=summary,
                resolution_kind=resolution_kind,
                review_request=review_payload,
                review_response=review_response,
                artifacts=artifacts,
                diagnostics=diagnostics,
            )
            return response.model_dump()
        except PeerInvocationError as exc:
            diagnostics["reviewer_daddy"] = {"status": "error", "error": str(exc)}
            response = BugResponse(
                summary="Technical remediation prepared, but reviewer_daddy could not be reached.",
                resolution_kind="review_required",
                review_request=review_payload,
                artifacts=artifacts,
                diagnostics=diagnostics,
            )
            return response.model_dump()

    def _query_sme(self, request: BugRequest) -> tuple[str, dict[str, Any]]:
        if not self.config.sme_agent.enabled:
            return request.kb_context or "No SME peer configured.", {"status": "disabled"}

        query = {
            "question": "What service-specific domain context or SOP guidance should shape the remediation?",
            "requested_by": "bug_daddy",
            "context": IssueContext(
                prompt=request.prompt,
                source=request.source,
                service_name=request.service_name,
                repository=request.repository,
                logs=request.logs,
                telemetry=request.telemetry,
                kb_context=request.kb_context,
                metadata=request.metadata,
            ).model_dump(),
        }
        try:
            response = self.peers.invoke(self.config.sme_agent, query)
            return str(response.get("summary", "")), {"status": "ok"}
        except PeerInvocationError as exc:
            return request.kb_context or "SME peer unavailable.", {"status": "error", "error": str(exc)}


def build_runtime(config: AppConfig | None = None) -> BugDaddyRuntime:
    cfg = config or AppConfig.from_env()
    tools = load_mcp_tools(cfg)
    agents = build_bug_agents(
        cfg,
        tools={"slack": tools.slack_tools, "jira": tools.jira_tools, "bitbucket": tools.bitbucket_tools},
    )
    return BugDaddyRuntime(
        config=cfg,
        tools=tools,
        agents=agents,
        peers=PeerRuntimeClient(cfg),
    )


def _orchestrator_prompt(request: BugRequest, sme_summary: str) -> str:
    return f"""
Decide the remediation strategy for this issue.

Prompt:
{request.prompt}

Incident summary:
{request.incident_summary or "No incident context provided"}

Service:
{request.service_name}

SME guidance:
{sme_summary}
""".strip()


def _planner_prompt(request: BugRequest, orchestration: str) -> str:
    return f"""
Create the remediation plan.

Prompt:
{request.prompt}

Repository:
{request.repository}

Orchestrator brief:
{orchestration}
""".strip()


def _gatherer_prompt(request: BugRequest, orchestration: str, sme_summary: str) -> str:
    return f"""
Gather the best available technical context.

Prompt:
{request.prompt}

Repository:
{request.repository}

Logs:
{_joined(request.logs)}

Telemetry:
{request.telemetry}

Orchestrator brief:
{orchestration}

SME guidance:
{sme_summary}
""".strip()


def _log_prompt(request: BugRequest, gatherer: str) -> str:
    return f"""
Analyze the logs and error patterns.

Prompt:
{request.prompt}

Logs:
{_joined(request.logs)}

Gathered context:
{gatherer}
""".strip()


def _coder_prompt(
    request: BugRequest,
    planner: str,
    gatherer: str,
    sme_summary: str,
    log_analysis: str,
) -> str:
    return f"""
Propose the code-level remediation if justified.

Prompt:
{request.prompt}

Repository:
{request.repository}

Plan:
{planner}

Gathered context:
{gatherer}

SME guidance:
{sme_summary}

Log analysis:
{log_analysis}
""".strip()


def _critic_prompt(request: BugRequest, coder: str) -> str:
    return f"""
Critique the proposed remediation.

Prompt:
{request.prompt}

Proposed remediation:
{coder}
""".strip()


def _joined(items: list[str]) -> str:
    return "\n".join(items) if items else "None provided"
