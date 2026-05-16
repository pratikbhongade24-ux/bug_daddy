from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import BugAgentBundle, build_bug_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import BugRequest, BugResponse, IssueContext, ReviewRequest
from agentic_solution.execution import ExecutionLogger
from agentic_solution.heuristics import is_non_code_resolution
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools
from agentic_solution.peer import PeerInvocationError, PeerRuntimeClient


@dataclass(slots=True)
class BugDaddyRuntime:
    config: AppConfig
    tools: MCPToolBundle
    peers: PeerRuntimeClient

    def _build_agents(self) -> BugAgentBundle:
        """Build fresh agent instances per invocation — Strands Agents are stateful and not concurrency-safe."""
        return build_bug_agents(
            self.config,
            tools={
                "slack": [],
                "jira": self.tools.jira_tools,
                "bitbucket": self.tools.bitbucket_tools,
                "github": self.tools.github_tools,
                "github_read_only": self.tools.github_read_only_tools,
                "github_read_write": self.tools.github_read_write_tools,
            },
        )

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        agents = self._build_agents()
        logger = ExecutionLogger.from_payload(payload, "bug_daddy")
        request = BugRequest.model_validate(payload)
        started = logger.node_started("sme", "SME", "Query SME remediation guidance", request.prompt)
        sme_summary, sme_diagnostics = self._query_sme(request)
        logger.node_completed("sme", "SME", "SME remediation guidance returned", started, sme_summary, sme_diagnostics)

        if self.config.dry_run:
            started = logger.node_started("bug", "Bug Daddy", "Dry-run remediation orchestration")
            response = BugResponse(
                summary=(
                    "Dry run only. bug_daddy would plan the remediation, gather evidence, "
                    "propose a fix, and optionally hand off to reviewer_daddy."
                ),
                resolution_kind="review_required",
                diagnostics={**self.tools.diagnostics, "sme_agent": sme_diagnostics},
            )
            logger.node_completed("bug", "Bug Daddy", "Dry-run remediation orchestration complete", started, response.summary)
            return response.model_dump()

        started = logger.node_started("ctx", "Context Analyzer", "Gather context and analyze logs", request.prompt)
        context = str(agents.context_analyzer(_context_prompt(request, "", sme_summary)))
        logger.node_completed("ctx", "Context Analyzer", "Context gathered", started, context)

        started = logger.node_started("strat", "Strategy Planner", "Create remediation strategy and plan", request.prompt)
        strategy = str(agents.strategy_planner(_strategy_prompt(request, context, sme_summary)))
        logger.node_completed("strat", "Strategy Planner", "Remediation strategy complete", started, strategy)

        started = logger.node_started("crit1", "Critic Agent", "Critique strategy", strategy)
        critic_strategy = str(agents.critic(_critic_step_prompt(request, "Strategy Planner", strategy)))
        logger.node_completed("crit1", "Critic Agent", "Critique strategy complete", started, critic_strategy)

        diagnostics: dict[str, Any] = {**self.tools.diagnostics, "sme_agent": sme_diagnostics}
        artifacts: list[dict[str, Any]] = [
            {"type": "context_analysis", "system": "bug_daddy", "content": context},
            {"type": "strategy_plan", "system": "bug_daddy", "content": strategy},
            {"type": "critic_strategy", "system": "bug_daddy", "content": critic_strategy},
        ]

        if is_non_code_resolution(strategy, critic_strategy):
            logger.emit(
                "node.completed",
                node_id="jag",
                node_name="Jira Agent",
                status="succeeded",
                level="info",
                title="Jira-only resolution selected",
                output_summary="Non-code resolution identified; Jira ticket should carry the operational action.",
            )
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

        started = logger.node_started("code", "Coder Agent", "Propose code remediation", context)
        coder = str(agents.coder(_coder_prompt(request, strategy, context, sme_summary)))
        logger.node_completed("code", "Coder Agent", "Code remediation proposed", started, coder)

        started = logger.node_started("crit2", "Critic Agent", "Critique code proposal", coder)
        critic_coder = str(agents.critic(_critic_step_prompt(request, "Coder Agent", coder)))
        logger.node_completed("crit2", "Critic Agent", "Critique code complete", started, critic_coder)

        artifacts.extend([
            {"type": "fix_proposal", "system": "bug_daddy", "content": coder},
            {"type": "critic_coder", "system": "bug_daddy", "content": critic_coder},
        ])

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
            strategy_plan=strategy,
            context_analysis=context,
            sme_guidance=sme_summary,
            fix_proposal=coder,
            critique=critic_coder,
            metadata={
                **request.metadata,
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
            started = logger.node_started("rev", "Reviewer Daddy", "Hand off remediation package to reviewer_daddy")
            review_response = self.peers.invoke(self.config.reviewer_daddy, review_payload)
            logger.node_completed(
                "rev",
                "Reviewer Daddy",
                "reviewer_daddy handoff complete",
                started,
                str(review_response.get("summary", "")),
                review_response,
            )
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
            logger.node_failed("rev", "Reviewer Daddy", "reviewer_daddy handoff failed", started, exc)
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
    return BugDaddyRuntime(
        config=cfg,
        tools=tools,
        peers=PeerRuntimeClient(cfg),
    )


def _strategy_prompt(request: BugRequest, context: str, sme_summary: str) -> str:
    return f"""
Decide the remediation strategy and create the plan.

Prompt:
{request.prompt}

Incident summary:
{request.incident_summary or "No incident context provided"}

Service:
{request.service_name}

Repository:
{request.repository}

Jira:
{request.metadata.get("jira_key") or request.metadata.get("resolution_jira") or "None provided"}

Gathered Context:
{context}

SME guidance:
{sme_summary}
""".strip()


def _context_prompt(request: BugRequest, strategy: str, sme_summary: str) -> str:
    return f"""
Gather technical context and analyze logs.

Prompt:
{request.prompt}

Repository:
{request.repository}

Jira:
{request.metadata.get("jira_key") or request.metadata.get("resolution_jira") or "None provided"}

Logs:
{_joined(request.logs)}

Telemetry:
{request.telemetry}

Strategy:
{strategy}

SME guidance:
{sme_summary}
""".strip()


def _coder_prompt(
    request: BugRequest,
    strategy: str,
    context: str,
    sme_summary: str,
) -> str:
    return f"""
Propose the code-level remediation if justified.

Prompt:
{request.prompt}

Repository:
{request.repository}

Jira:
{request.metadata.get("jira_key") or request.metadata.get("resolution_jira") or "None provided"}

Strategy & Plan:
{strategy}

Gathered Context & Log Analysis:
{context}

SME guidance:
{sme_summary}
""".strip()


def _critic_step_prompt(request: BugRequest, step_name: str, content: str) -> str:
    return f"""
Critique the output of the '{step_name}' step.

Prompt:
{request.prompt}

Step Output:
{content}
""".strip()


def _joined(items: list[str]) -> str:
    return "\n".join(items) if items else "None provided"
