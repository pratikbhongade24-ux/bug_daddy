from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import IncidentAgentBundle, build_incident_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import BugRequest, IncidentReport, IncidentRequest, IncidentResponse, IssueContext
from agentic_solution.execution import ExecutionLogger
from agentic_solution.heuristics import infer_incident_severity, needs_bug_handoff
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools
from agentic_solution.peer import PeerInvocationError, PeerRuntimeClient


@dataclass(slots=True)
class IncidentDaddyRuntime:
    config: AppConfig
    tools: MCPToolBundle
    peers: PeerRuntimeClient

    def _build_agents(self) -> IncidentAgentBundle:
        """Build fresh agent instances per invocation — Strands Agents are stateful and not concurrency-safe."""
        return build_incident_agents(
            self.config,
            tools={
                "slack": self.tools.slack_tools, 
                "jira": self.tools.jira_tools, 
                "bitbucket": self.tools.bitbucket_tools,
                "github": self.tools.github_tools
            },
        )

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        agents = self._build_agents()
        logger = ExecutionLogger.from_payload(payload, "incident_daddy")
        request = IncidentRequest.model_validate(payload)
        started = logger.node_started("sme", "SME", "Query SME guidance", request.prompt)
        sme_summary, sme_diagnostics = self._query_sme(request)
        logger.node_completed("sme", "SME", "SME guidance returned", started, sme_summary, sme_diagnostics)

        if self.config.dry_run:
            started = logger.node_started("inc", "Incident Daddy", "Dry-run incident orchestration")
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
            logger.node_completed("inc", "Incident Daddy", "Dry-run incident orchestration complete", started, summary)
            return response.model_dump()

        started = logger.node_started("iana", "Incident Analyzer", "Analyze incident trigger", request.prompt)
        analysis = str(agents.analyzer(_analysis_prompt(request, sme_summary)))
        logger.node_completed("iana", "Incident Analyzer", "Incident analysis complete", started, analysis)
        started = logger.node_started("inc", "Incident Daddy", "Coordinate incident orchestration", analysis)
        orchestration = str(agents.orchestrator(_orchestrator_prompt(request, analysis, sme_summary)))
        logger.node_completed("inc", "Incident Daddy", "Incident orchestration complete", started, orchestration)

        incident_report = self._write_and_review_report(agents, request, analysis, orchestration, sme_summary, logger)
        self._post_report_to_slack(agents, incident_report)

        severity = infer_incident_severity(f"{request.prompt}\n{analysis}\n{orchestration}")
        handoff = needs_bug_handoff(request.prompt, analysis, orchestration, *request.logs)

        artifacts: list[dict[str, Any]] = [
            {"type": "incident_analysis", "system": "incident_daddy", "content": analysis},
            {"type": "incident_summary", "system": "incident_daddy", "content": orchestration},
            {"type": "incident_report", "system": "incident_daddy", "content": incident_report.raw_markdown},
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
                started = logger.node_started("bug", "Bug Daddy", "Hand off to bug_daddy", orchestration)
                try:
                    bug_response = self.peers.invoke(self.config.bug_daddy, bug_request_payload)
                    logger.node_completed(
                        "bug",
                        "Bug Daddy",
                        "bug_daddy handoff complete",
                        started,
                        str(bug_response.get("summary", "")),
                        bug_response,
                    )
                    artifacts.append(
                        {
                            "type": "bug_handoff_response",
                            "system": "bug_daddy",
                            "content": bug_response,
                        }
                    )
                except PeerInvocationError as exc:
                    logger.node_failed("bug", "Bug Daddy", "bug_daddy handoff failed", started, exc)
                    diagnostics["bug_daddy"] = {"status": "error", "error": str(exc)}
            else:
                diagnostics["bug_daddy"] = {"status": "disabled"}

        response = IncidentResponse(
            summary=orchestration,
            severity=severity,
            next_action=next_action,
            handoff_to_bug=handoff,
            bug_request=bug_request_payload,
            incident_report=incident_report,
            artifacts=artifacts,
            diagnostics=diagnostics,
        )
        return response.model_dump()

    def _write_and_review_report(
        self,
        agents: IncidentAgentBundle,
        request: IncidentRequest,
        analysis: str,
        orchestration: str,
        sme_summary: str,
        logger: ExecutionLogger,
    ) -> IncidentReport:
        started = logger.node_started("irw", "Report Writer", "Write incident report", orchestration)
        draft = str(agents.report_writer(_report_writer_prompt(request, analysis, orchestration, sme_summary)))
        logger.node_completed("irw", "Report Writer", "Incident report draft complete", started, draft)

        started = logger.node_started("irr", "Report Reviewer", "Review incident report", draft)
        review = str(agents.report_reviewer(f"Review this incident report:\n\n{draft}"))
        logger.node_completed("irr", "Report Reviewer", "Incident report reviewed", started, review)

        if "[REPORT: REWORK]" in review:
            reason = review.split("[REPORT: REWORK]", 1)[-1].strip().splitlines()[0]
            started = logger.node_started("irw", "Report Writer", "Rework incident report", reason)
            draft = str(agents.report_writer(
                _report_writer_prompt(request, analysis, orchestration, sme_summary)
                + f"\n\nPrevious draft was returned for rework. Reason: {reason}\nPlease fix and rewrite."
            ))
            logger.node_completed("irw", "Report Writer", "Rework complete", started, draft)
        return _parse_incident_report(draft, infer_incident_severity(f"{request.prompt}\n{analysis}"))

    def _post_report_to_slack(self, agents: IncidentAgentBundle, report: IncidentReport) -> None:
        slack_message = _format_slack_report(report)
        try:
            agents.orchestrator(
                f"Post this exact message to Slack channel C0B2QUEU4NN using slack_post_message:\n\n{slack_message}"
            )
        except Exception:
            pass

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
    return IncidentDaddyRuntime(
        config=cfg,
        tools=tools,
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


def _report_writer_prompt(
    request: IncidentRequest,
    analysis: str,
    orchestration: str,
    sme_summary: str,
) -> str:
    return f"""
Write a structured incident report based on the following inputs.

Service: {request.service_name}

Incident Analysis:
{analysis}

Orchestrator Triage:
{orchestration}

SME Context:
{sme_summary}
""".strip()


def _parse_incident_report(raw_markdown: str, severity: str) -> IncidentReport:
    import re

    title_match = re.search(r"##\s*Incident Report:\s*(.+)", raw_markdown)
    title = title_match.group(1).strip() if title_match else "Incident"

    severity_match = re.search(r"\|\s*Severity\s*\|\s*(.+?)\s*\|", raw_markdown, re.IGNORECASE)
    report_severity = severity_match.group(1).strip().lower() if severity_match else severity

    owner_match = re.search(r"\|\s*Owner\s*\|\s*(.+?)\s*\|", raw_markdown, re.IGNORECASE)
    owner = owner_match.group(1).strip() if owner_match else None

    status_match = re.search(r"\|\s*Status\s*\|\s*(.+?)\s*\|", raw_markdown, re.IGNORECASE)
    status = status_match.group(1).strip() if status_match else "Investigating"

    blast_match = re.search(r"\*\*Blast Radius\*\*\s*\n(.+?)(?=\n\*\*|\Z)", raw_markdown, re.DOTALL)
    blast_radius = blast_match.group(1).strip() if blast_match else None

    root_match = re.search(r"\*\*Root Cause Hypothesis\*\*\s*\n(.+?)(?=\n\*\*|\Z)", raw_markdown, re.DOTALL)
    root_cause = root_match.group(1).strip() if root_match else None

    actions_block = re.search(r"\*\*Actions Taken\*\*\s*\n((?:- .+\n?)+)", raw_markdown)
    actions_taken = (
        [line.lstrip("- ").strip() for line in actions_block.group(1).strip().splitlines()]
        if actions_block
        else []
    )

    normalized_severity = report_severity if report_severity in ("sev1", "sev2", "sev3") else severity
    return IncidentReport(
        title=title,
        severity=normalized_severity,  # type: ignore[arg-type]
        blast_radius=blast_radius,
        root_cause=root_cause,
        actions_taken=actions_taken,
        owner=owner,
        status=status,
        raw_markdown=raw_markdown,
    )


def _format_slack_report(report: IncidentReport) -> str:
    sev_label = report.severity.upper() if report.severity != "unknown" else "UNKNOWN"
    actions = "\n".join(f"  • {a}" for a in report.actions_taken) if report.actions_taken else "  • None recorded"
    return (
        f":rotating_light: *Incident Report* — {report.title}\n"
        f"*Severity*: {sev_label}  |  *Owner*: {report.owner or 'Unknown'}  |  *Status*: {report.status}\n"
        f"\n"
        f"*Blast Radius*: {report.blast_radius or 'Under investigation'}\n"
        f"*Root Cause Hypothesis*: {report.root_cause or 'Under investigation'}\n"
        f"*Actions Taken*:\n{actions}\n"
        f"\n---\n_Reviewed by Reviewer Daddy · Auto-generated_"
    )
