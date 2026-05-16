from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentic_solution.agents import SMEAgentBundle, build_sme_agents
from agentic_solution.config import AppConfig
from agentic_solution.contracts import SMEQueryRequest, SMEQueryResponse
from agentic_solution.execution import ExecutionLogger
from agentic_solution.rag import RetrievalResult, SMERagClient, build_default_client

# ---------------------------------------------------------------------------
# Constants — the stub answer is the contractual floor of an SME response.
# The RAG enrichment is appended on top; retrieval failure must still leave
# the stub intact so the caller never sees an empty answer.
# ---------------------------------------------------------------------------


_STUB_ANSWER = (
    "No specific SOP suggestion from SME agent. "
    "Repository: https://github.com/pratikbhongade24-ux/bug_daddy, "
    "Production Branch: master"
)


@dataclass(slots=True)
class SMEAgentRuntime:
    """SME agent runtime.

    Composition order (production path):
        1. Build the stub answer (repo + branch hint, inline KB context).
        2. Call the SME RAG platform with the question + service filter.
        3. If retrieval returned content, *append* it under a "RAG context"
           header. The stub is never replaced — a retrieval outage still
           leaves the caller with a usable response.
        4. Lift retrieval citations into ``references`` and retrieval
           health into ``diagnostics`` so the audit journal records exactly
           where the answer came from.
    """

    config: AppConfig
    agents: SMEAgentBundle
    rag_client: SMERagClient = field(default_factory=build_default_client)

    def _build_agents(self) -> SMEAgentBundle:
        """Build fresh agent instances per invocation — Strands Agents are stateful and not concurrency-safe."""
        return build_sme_agents(self.config)

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        _ = self._build_agents()
        logger = ExecutionLogger.from_payload(payload, "sme_agent")
        request = SMEQueryRequest.model_validate(payload)

        if self.config.dry_run:
            started = logger.node_started("sme", "SME", "Dry-run SME query", request.question)
            response = SMEQueryResponse(
                summary=_compose_dry_run_summary(),
                references=_fallback_references(request),
                diagnostics={"dry_run": True, "rag": {"status": "skipped_dry_run"}},
            )
            logger.node_completed("sme", "SME", "Dry-run SME query complete", started, response.summary)
            return response.model_dump()

        started = logger.node_started("sme", "SME", "Answer SME query", request.question)
        retrieval = self._safe_retrieve(request)
        summary = _compose_summary(stub=_STUB_ANSWER, retrieval=retrieval)
        references = _fallback_references(request) + _retrieval_references(retrieval)
        diagnostics: dict[str, Any] = {
            "model_id": self.config.bedrock_model_id,
            "rag": retrieval.diagnostics,
        }
        if retrieval.conversation_id is not None:
            diagnostics["rag_conversation_id"] = retrieval.conversation_id
        logger.node_completed("sme", "SME", "SME query complete", started, summary)
        response = SMEQueryResponse(
            summary=summary,
            references=references,
            diagnostics=diagnostics,
        )
        return response.model_dump()

    # ------------------------------------------------------------------
    # Retrieval — wrapped so any unexpected fault still falls back to stub.
    # ------------------------------------------------------------------

    def _safe_retrieve(self, request: SMEQueryRequest) -> RetrievalResult:
        try:
            return self.rag_client.query(
                question=request.question,
                external_user_id=request.requested_by or "sme_agent",
                session_id=_session_id_for(request),
                filters=_filters_for(request),
            )
        except Exception as exc:  # noqa: BLE001 — retrieval must never escape
            return RetrievalResult(
                diagnostics={
                    "status": "unexpected_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )


def build_runtime(config: AppConfig | None = None) -> SMEAgentRuntime:
    cfg = config or AppConfig.from_env()
    return SMEAgentRuntime(
        config=cfg,
        agents=build_sme_agents(cfg),
        rag_client=build_default_client(),
    )


# ---------------------------------------------------------------------------
# Composition + helpers.
# ---------------------------------------------------------------------------


def _compose_summary(*, stub: str, retrieval: RetrievalResult) -> str:
    """Stack the stub and the retrieval enrichment.

    Stub is always the lead so a caller scanning the first line sees the
    canonical repo / branch hint. When retrieval contributed content we
    add a header so reviewers know which paragraph came from the RAG
    pipeline vs. the stub default."""
    if not retrieval.has_content:
        return stub
    return (
        f"{stub}\n\n"
        f"--- RAG context (from SME knowledge base) ---\n"
        f"{retrieval.answer}"
    )


def _compose_dry_run_summary() -> str:
    return (
        "Dry run only. SME agent would answer using SOP, ownership, and architecture "
        "context if the retrieval backend were connected.\n\n"
        f"{_STUB_ANSWER}"
    )


def _fallback_references(request: SMEQueryRequest) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    if request.context.kb_context:
        references.append({"type": "inline_kb_context", "content": request.context.kb_context})
    if request.context.service_name:
        references.append({"type": "service_name", "content": request.context.service_name})
    return references


def _retrieval_references(retrieval: RetrievalResult) -> list[dict[str, Any]]:
    if not retrieval.citations:
        return []
    refs: list[dict[str, Any]] = []
    for cit in retrieval.citations:
        if not isinstance(cit, dict):
            continue
        refs.append({
            "type": "rag_citation",
            "source": cit.get("source_name") or cit.get("file_path"),
            "score": cit.get("score"),
            "content": cit.get("content") or cit.get("snippet") or "",
        })
    return refs


def _session_id_for(request: SMEQueryRequest) -> str:
    """Bind the conversation to the originating correlation when one is
    present, so repeated SME queries about the same incident accumulate
    in a single conversation thread on the RAG platform side."""
    md = request.context.metadata or {}
    return (
        md.get("correlation_id")
        or md.get("incident_channel")
        or md.get("session_id")
        or f"sme:{request.requested_by or 'unknown'}"
    )


def _filters_for(request: SMEQueryRequest) -> dict[str, Any] | None:
    """Scope retrieval to the affected service when known. The SME RAG
    platform indexes per-service docs (kyc_service.md, repayment_service.md,
    etc.) and the filter narrows retrieval to the relevant subset."""
    if request.context.service_name:
        return {"service_name": request.context.service_name}
    return None


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


def _joined(items: list[str]) -> str:
    return "\n".join(items) if items else "None provided"
