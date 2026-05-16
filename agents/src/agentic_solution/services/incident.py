from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strands import Agent

from agentic_solution.agents import IncidentAgentBundle, _build_model, build_incident_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import (
    BugRequest,
    IncidentReport,
    IncidentRequest,
    IncidentResponse,
    IssueContext,
)
from agentic_solution.execution import ExecutionLogger
from agentic_solution.heuristics import infer_incident_severity
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools, slack_client_context
from agentic_solution.peer import PeerInvocationError, PeerRuntimeClient
from agentic_solution.prompts import SLACK_NOTIFIER_PROMPT


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
                "slack": [],  # slack_notifier is rebuilt with live tools inside _post_report_to_slack
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
                handoff_to_bug=False,
                diagnostics={**self.tools.diagnostics, "sme_agent": sme_diagnostics},
            )
            logger.node_completed("inc", "Incident Daddy", "Dry-run incident orchestration complete", started, summary)
            return response.model_dump()

        started = logger.node_started("iana", "Incident Analyzer", "Analyze incident trigger", request.prompt)
        analysis_raw, analysis = _call_agent_with_json_retry(
            agents.analyzer,
            _analysis_prompt(request, sme_summary),
            ["facts", "inferences", "blast_radius", "likely_owner"],
        )
        logger.node_completed("iana", "Incident Analyzer", "Incident analysis complete", started, analysis_raw)

        started = logger.node_started("inc", "Incident Daddy", "Coordinate incident orchestration", analysis_raw)
        orchestration_raw, orchestration = _call_agent_with_json_retry(
            agents.orchestrator,
            _orchestrator_prompt(request, analysis_raw, sme_summary),
            ["triage_summary", "severity", "next_action", "bug_daddy_handoff"],
        )
        logger.node_completed("inc", "Incident Daddy", "Incident orchestration complete", started, orchestration_raw)

        incident_report = self._write_and_review_report(agents, request, analysis_raw, orchestration_raw, sme_summary, logger)
        self._post_report_to_slack(incident_report, logger)

        severity = orchestration.get("severity") or infer_incident_severity(f"{request.prompt}\n{analysis_raw}\n{orchestration_raw}")
        handoff = bool(orchestration.get("bug_daddy_handoff", False))

        artifacts: list[dict[str, Any]] = [
            {"type": "incident_analysis", "system": "incident_daddy", "content": analysis},
            {"type": "incident_summary", "system": "incident_daddy", "content": orchestration},
            {"type": "incident_report", "system": "incident_daddy", "content": incident_report.raw_markdown},
        ]
        diagnostics: dict[str, Any] = {**self.tools.diagnostics, "sme_agent": sme_diagnostics}

        bug_request_payload = None
        next_action = "Continue incident coordination in Slack and Jira."
        if handoff:
            bug_request_payload = self._build_bug_request(request, orchestration.get("triage_summary", orchestration_raw), severity, artifacts).model_dump()
            artifacts.append(
                {
                    "type": "bug_handoff_request",
                    "system": "bug_daddy",
                    "content": bug_request_payload,
                }
            )
            next_action = "Hand off to bug_daddy for remediation."

            if self.config.bug_daddy.enabled:
                started = logger.node_started("bug", "Bug Daddy", "Hand off to bug_daddy", orchestration_raw)
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
            summary=orchestration.get("triage_summary", orchestration_raw),
            severity=severity,
            next_action=orchestration.get("next_action", next_action),
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
        _report_keys = ["title", "severity", "owner", "status", "summary", "blast_radius", "root_cause", "actions_taken"]
        _review_keys = ["decision"]

        started = logger.node_started("irw", "Report Writer", "Write incident report", orchestration)
        draft_raw, draft = _call_agent_with_json_retry(
            agents.report_writer,
            _report_writer_prompt(request, analysis, orchestration, sme_summary),
            _report_keys,
        )
        logger.node_completed("irw", "Report Writer", "Incident report draft complete", started, draft_raw)

        started = logger.node_started("irr", "Report Reviewer", "Review incident report", draft_raw)
        review_raw, review = _call_agent_with_json_retry(
            agents.report_reviewer,
            f"Review this incident report JSON:\n\n{draft_raw}",
            _review_keys,
        )
        logger.node_completed("irr", "Report Reviewer", "Incident report reviewed", started, review_raw)

        if review.get("decision") == "REWORK":
            reason = review.get("reason", "unspecified")
            started = logger.node_started("irw", "Report Writer", "Rework incident report", reason)
            draft_raw, draft = _call_agent_with_json_retry(
                agents.report_writer,
                _report_writer_prompt(request, analysis, orchestration, sme_summary)
                + f"\n\nPrevious draft was returned for rework. Reason: {reason}\nPlease fix and rewrite.",
                _report_keys,
            )
            logger.node_completed("irw", "Report Writer", "Rework complete", started, draft_raw)

        fallback_severity = infer_incident_severity(f"{request.prompt}\n{analysis}")
        return _build_incident_report(draft, draft_raw, fallback_severity)

    def _post_report_to_slack(self, report: IncidentReport, logger: ExecutionLogger) -> None:
        if not self.tools.slack_enabled:
            started = logger.node_started("slk", "Slack Notifier", "Post incident report to Slack")
            logger.node_failed(
                "slk", "Slack Notifier", "Slack notification skipped", started,
                RuntimeError("Slack MCP not configured — SLACK_MCP_COMMAND is not set"),
            )
            return

        slack_message = _format_slack_report(report)
        started = logger.node_started("slk", "Slack Notifier", "Post incident report to Slack")
        try:
            with slack_client_context(self.tools) as slack_tools:
                notifier = Agent(
                    model=_build_model(self.config),
                    system_prompt=SLACK_NOTIFIER_PROMPT,
                    tools=slack_tools,
                )
                notifier(
                    f"Post this exact message to Slack channel C0B2QUEU4NN using slack_post_message:\n\n{slack_message}"
                )
            logger.node_completed("slk", "Slack Notifier", "Slack notification sent", started, "ok")
        except Exception as exc:
            logger.node_failed("slk", "Slack Notifier", "Slack notification failed", started, exc)

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


def _try_parse_json(text: str) -> dict[str, Any] | None:
    import json
    import re
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _call_agent_with_json_retry(
    agent: Any,
    prompt: str,
    required_keys: list[str],
) -> tuple[str, dict[str, Any]]:
    """Call an agent, parse its JSON output, and retry once with feedback if parsing fails or keys are missing."""
    raw = str(agent(prompt))
    parsed = _try_parse_json(raw)

    missing = [k for k in required_keys if parsed is None or k not in parsed] if parsed is not None else required_keys
    if parsed is not None and not missing:
        return raw, parsed

    error_detail = (
        f"Missing required keys: {missing}" if parsed is not None
        else f"Output was not valid JSON. Got:\n{raw}"
    )
    retry_prompt = (
        f"{prompt}\n\n"
        f"Your previous response had a JSON error. {error_detail}\n"
        f"Required keys: {required_keys}\n"
        f"Respond with ONLY a valid JSON object containing all required keys. No preamble, no markdown fences."
    )
    raw = str(agent(retry_prompt))
    parsed = _try_parse_json(raw) or {}
    return raw, parsed


def _build_incident_report(data: dict[str, Any], raw: str, fallback_severity: str) -> IncidentReport:
    sev = str(data.get("severity", fallback_severity)).lower()
    normalized_severity = sev if sev in ("sev1", "sev2", "sev3") else fallback_severity
    return IncidentReport(
        title=str(data.get("title", "Incident")),
        severity=normalized_severity,  # type: ignore[arg-type]
        owner=data.get("owner") or None,
        status=str(data.get("status", "Investigating")),
        blast_radius=data.get("blast_radius") or None,
        root_cause=data.get("root_cause") or None,
        actions_taken=list(data.get("actions_taken", [])),
        raw_markdown=raw,
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
