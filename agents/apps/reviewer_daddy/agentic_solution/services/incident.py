from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import IncidentAgentBundle, build_incident_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import BugRequest, IncidentRequest, IncidentResponse, IssueContext
from agentic_solution.heuristics import infer_incident_severity, needs_bug_handoff
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools
from agentic_solution.peer import PeerInvocationError, PeerRuntimeClient


@dataclass(slots=True)
class IncidentDaddyRuntime:
    config: AppConfig
    tools: MCPToolBundle
    agents: IncidentAgentBundle
    peers: PeerRuntimeClient

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = IncidentRequest.model_validate(payload)
        sme_summary, sme_diagnostics = self._query_sme(request)

        if self.config.dry_run:
            summary = (
                "Dry run only. incident_daddy would analyze the trigger, open Slack/Jira updates, "
                "and decide whether to hand off to bug_daddy."
            )
            response = IncidentResponse(
                summary=summary,
                severity=infer_incident_severity(f"{request.prompt} {' '.join(request.logs)}"),
                next_action="Review dry-run diagnostics and connect peer runtimes plus MCP servers.",
                handoff_to_bug=needs_bug_handoff(request.prompt, *request.logs),
                diagnostics={**self.tools.diagnostics, "sme_agent": sme_diagnostics},
            )
            return response.model_dump()

        analysis = str(self.agents.analyzer(_analysis_prompt(request, sme_summary)))
        orchestration = str(self.agents.orchestrator(_orchestrator_prompt(request, analysis, sme_summary)))
        severity = infer_incident_severity(f"{request.prompt}\n{analysis}\n{orchestration}")
        handoff = needs_bug_handoff(request.prompt, analysis, orchestration, *request.logs)

        artifacts: list[dict[str, Any]] = [
            {"type": "incident_analysis", "system": "incident_daddy", "content": analysis},
            {"type": "incident_summary", "system": "incident_daddy", "content": orchestration},
        ]
        diagnostics: dict[str, Any] = {**self.tools.diagnostics, "sme_agent": sme_diagnostics}

        bug_request_payload = None
        next_action = "Continue incident coordination in Slack and Jira."
        if handoff:
            bug_request_payload = self._build_bug_request(request, orchestration, severity, artifacts).model_dump()
            artifacts.append(
                {
                    "type": "bug_handoff_request",
                    "system": "bug_daddy",
                    "content": bug_request_payload,
                }
            )
            next_action = "Hand off to bug_daddy for remediation."

            if self.config.bug_daddy.enabled:
                try:
                    bug_response = self.peers.invoke(self.config.bug_daddy, bug_request_payload)
                    artifacts.append(
                        {
                            "type": "bug_handoff_response",
                            "system": "bug_daddy",
                            "content": bug_response,
                        }
                    )
                except PeerInvocationError as exc:
                    diagnostics["bug_daddy"] = {"status": "error", "error": str(exc)}
            else:
                diagnostics["bug_daddy"] = {"status": "disabled"}

        response = IncidentResponse(
            summary=orchestration,
            severity=severity,
            next_action=next_action,
            handoff_to_bug=handoff,
            bug_request=bug_request_payload,
            artifacts=artifacts,
            diagnostics=diagnostics,
        )
        return response.model_dump()

    def _query_sme(self, request: IncidentRequest) -> tuple[str, dict[str, Any]]:
        if not self.config.sme_agent.enabled:
            return request.kb_context or "No SME peer configured.", {"status": "disabled"}

        query = {
            "question": (
                "What service knowledge, SOP guidance, or ownership information is relevant to this incident?"
            ),
            "requested_by": "incident_daddy",
            "context": IssueContext.model_validate(request.model_dump()).model_dump(),
        }
        try:
            response = self.peers.invoke(self.config.sme_agent, query)
            return str(response.get("summary", "")), {"status": "ok"}
        except PeerInvocationError as exc:
            return request.kb_context or "SME peer unavailable.", {"status": "error", "error": str(exc)}

    @staticmethod
    def _build_bug_request(
        request: IncidentRequest,
        incident_summary: str,
        severity: str,
        artifacts: list[dict[str, Any]],
    ) -> BugRequest:
        return BugRequest(
            prompt=request.prompt,
            source=request.source,
            service_name=request.service_name,
            repository=request.repository,
            logs=request.logs,
            telemetry=request.telemetry,
            kb_context=request.kb_context,
            metadata=request.metadata,
            incident_summary=incident_summary,
            incident_severity=severity,
            incident_artifacts=artifacts,
        )


def build_runtime(config: AppConfig | None = None) -> IncidentDaddyRuntime:
    cfg = config or AppConfig.from_env()
    tools = load_mcp_tools(cfg)
    agents = build_incident_agents(
        cfg,
        tools={"slack": tools.slack_tools, "jira": tools.jira_tools, "bitbucket": tools.bitbucket_tools},
    )
    return IncidentDaddyRuntime(
        config=cfg,
        tools=tools,
        agents=agents,
        peers=PeerRuntimeClient(cfg),
    )


def _analysis_prompt(request: IncidentRequest, sme_summary: str) -> str:
    return f"""
Analyze the incident trigger and extract facts.

Trigger:
{request.trigger or request.source}

Prompt:
{request.prompt}

Service:
{request.service_name}

Logs:
{_joined(request.logs)}

Telemetry:
{request.telemetry}

SME context:
{sme_summary}
""".strip()


def _orchestrator_prompt(request: IncidentRequest, analysis: str, sme_summary: str) -> str:
    return f"""
Create the incident triage summary.

Prompt:
{request.prompt}

Service:
{request.service_name}

Incident analysis:
{analysis}

SME context:
{sme_summary}

Say clearly if bug_daddy should be engaged.
""".strip()


def _joined(items: list[str]) -> str:
    return "\n".join(items) if items else "None provided"
