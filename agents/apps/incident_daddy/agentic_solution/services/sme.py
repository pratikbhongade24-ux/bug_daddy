from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import SMEAgentBundle, build_sme_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import SMEQueryRequest, SMEQueryResponse
from agentic_solution.execution import ExecutionLogger


@dataclass(slots=True)
class SMEAgentRuntime:
    config: AppConfig
    agents: SMEAgentBundle

    def _build_agents(self) -> SMEAgentBundle:
        """Build fresh agent instances per invocation — Strands Agents are stateful and not concurrency-safe."""
        return build_sme_agents(self.config)

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        agents = self._build_agents()
        logger = ExecutionLogger.from_payload(payload, "sme_agent")
        request = SMEQueryRequest.model_validate(payload)

        if self.config.dry_run:
            started = logger.node_started("sme", "SME", "Dry-run SME query", request.question)
            response = SMEQueryResponse(
                summary=(
                    "Dry run only. SME agent would answer using SOP, ownership, and architecture "
                    "context if the retrieval backend were connected."
                ),
                references=_fallback_references(request),
                diagnostics={"dry_run": True},
            )
            logger.node_completed("sme", "SME", "Dry-run SME query complete", started, response.summary)
            return response.model_dump()

        started = logger.node_started("sme", "SME", "Answer SME query", request.question)
        answer = (
            "No specific SOP suggestion from SME agent. "
            "Repository: https://github.com/pratikbhongade24-ux/bug_daddy, "
            "Production Branch: master"
        )
        logger.node_completed("sme", "SME", "SME query complete", started, answer)
        response = SMEQueryResponse(
            summary=answer,
            references=_fallback_references(request),
            diagnostics={"model_id": self.config.bedrock_model_id},
        )
        return response.model_dump()


def build_runtime(config: AppConfig | None = None) -> SMEAgentRuntime:
    cfg = config or AppConfig.from_env()
    return SMEAgentRuntime(config=cfg, agents=build_sme_agents(cfg))


def _query_prompt(request: SMEQueryRequest) -> str:
    return f"""
Answer the SME query as shared domain support for other agents.

Requested by:
{request.requested_by}

Question:
{request.question}

Service:
{request.context.service_name}

Prompt:
{request.context.prompt}

Repository:
{request.context.repository}

Logs:
{_joined(request.context.logs)}

Telemetry:
{request.context.telemetry}

Inline KB context:
{request.context.kb_context or "None provided"}

Metadata:
{request.context.metadata}
""".strip()


def _fallback_references(request: SMEQueryRequest) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    if request.context.kb_context:
        references.append({"type": "inline_kb_context", "content": request.context.kb_context})
    if request.context.service_name:
        references.append({"type": "service_name", "content": request.context.service_name})
    return references


def _joined(items: list[str]) -> str:
    return "\n".join(items) if items else "None provided"
