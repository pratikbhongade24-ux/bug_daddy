from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_solution.agents import SMEAgentBundle, build_sme_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import SMEQueryRequest, SMEQueryResponse


@dataclass(slots=True)
class SMEAgentRuntime:
    config: AppConfig
    agents: SMEAgentBundle

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = SMEQueryRequest.model_validate(payload)

        if self.config.dry_run:
            response = SMEQueryResponse(
                summary=(
                    "Dry run only. SME agent would answer using SOP, ownership, and architecture "
                    "context if the retrieval backend were connected."
                ),
                references=_fallback_references(request),
                diagnostics={"dry_run": True},
            )
            return response.model_dump()

        answer = str(self.agents.expert(_query_prompt(request)))
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
