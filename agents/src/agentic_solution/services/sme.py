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

        references = _fallback_references(request)

        if "query_monitor" in (request.context.metadata or {}).get("source", "") or \
           "query_monitor" in (request.context.kb_context or "") or \
           "Query Monitor" in request.question:
            answer = answer + "\n\n" + _AXIS_REFUND_DOC
            references.append({"type": "refund_api_doc", "content": "AXIS Refund API documentation attached — see summary for known partial refund bug (AXIS-PARTIAL-REFUND-001)."})

        logger.node_completed("sme", "SME", "SME query complete", started, answer)
        response = SMEQueryResponse(
            summary=answer,
            references=references,
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


_AXIS_REFUND_DOC = """
--- AXIS REFUND API DOCUMENTATION ---

CRITICAL LIMITATION:
AXIS Bank Refund API does NOT support partial refunds.
If refundType="PARTIAL" is sent, AXIS ignores the refundAmount and processes a FULL refund
equal to the original payment amount. No error is returned — HTTP 200 with status REFUND_INITIATED.
This is silent data corruption detectable only via reconciliation.

WORKAROUND: Use refundType="FULL" only for AXIS. Route partial refunds via HDFC or ICICI.

KNOWN BUG: AXIS-PARTIAL-REFUND-001 (CRITICAL, Open)
Detection: ms_system_monitors — T-1 Refund vs Recon Discrepancy Check
Tables affected: ms_refunds (stores requested partial amount), ms_reconciliation_items (stores bank full amount, match_status=AMOUNT_MISMATCH)

BANK CAPABILITY MATRIX:
- HDFC:  Full ✅  Partial ✅  TAT: 3-5 days  Settlement: T+0
- ICICI: Full ✅  Partial ✅  TAT: 5-7 days  Settlement: T+1
- AXIS:  Full ✅  Partial ⛔  TAT: 2-3 days  Settlement: T+0

REFUND REQUEST FIELDS:
- originalPaymentId (required)
- bankCode (required): HDFC | ICICI | AXIS
- refundType (required): FULL | PARTIAL — AXIS only supports FULL
- reason (required)
- customerId (required)
- refundAmount (required if PARTIAL): ignored by AXIS
- originalAmount (optional): used by AXIS to determine full refund value
- remarks (optional)
- notifyCustomer (optional, default true)

AXIS BUG RESPONSE SIGNATURE:
bankResponse.refundAmount = original payment amount (NOT what was requested)
bankResponse.requestedRefundAmount = what was sent (the partial amount)
Delta = overpayment amount
--- END AXIS REFUND API DOCUMENTATION ---
""".strip()
