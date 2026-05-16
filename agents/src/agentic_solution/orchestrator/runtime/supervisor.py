"""
Remediation Supervisor — the state-machine kernel of the orchestrator.

The supervisor owns the lifecycle of a single ``NormalizedEvent`` from
routing through plan-construction, execution, optional rollback, and
feedback emission. Every transition is logged with the correlation_id so
the entire incident is reconstructible from the audit journal alone.

Supervisor-mediated execution ensures controlled agent autonomy with
auditable rollback guarantees: an agent never decides on its own to
escalate, retry, or roll back — the supervisor decides, and the agent
executes a single bounded intent at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..contracts import (
    AgentOutcome,
    NormalizedEvent,
    RemediationPlan,
    RemediationStep,
)
from ..observability.audit import AuditJournal
from ..observability.logging import StructuredLogger
from ..routing.registry import AgentRegistry
from ..routing.router import RoutingEngine
from .executor import AgentExecutor
from .recovery import RecoveryCoordinator


@dataclass
class IncidentTrace:
    """End-to-end record of how the orchestrator handled one event."""

    event: NormalizedEvent
    plan: RemediationPlan | None
    outcomes: list[AgentOutcome] = field(default_factory=list)
    compensations: list[AgentOutcome] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    terminal_status: str = "pending"
    rationale: str = ""

    def as_audit_record(self) -> dict:
        return {
            "event_id": self.event.event_id,
            "correlation_id": self.event.correlation_id,
            "incident_class": self.event.incident_class.value,
            "severity": self.event.severity.value,
            "terminal_status": self.terminal_status,
            "rationale": self.rationale,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "plan": self.plan.model_dump(mode="json") if self.plan else None,
            "outcomes": [o.model_dump(mode="json") for o in self.outcomes],
            "compensations": [c.model_dump(mode="json") for c in self.compensations],
        }


class RemediationSupervisor:
    def __init__(
        self,
        *,
        registry: AgentRegistry,
        executor: AgentExecutor,
        router: RoutingEngine,
        recovery: RecoveryCoordinator,
        journal: AuditJournal,
        logger: StructuredLogger,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._router = router
        self._recovery = recovery
        self._journal = journal
        self._logger = logger

    async def handle(self, event: NormalizedEvent) -> IncidentTrace:
        trace = IncidentTrace(event=event, plan=None)
        log = self._logger.bind(correlation_id=event.correlation_id)
        log.info(
            "supervisor.handle.start",
            event_id=event.event_id,
            incident_class=event.incident_class.value,
            severity=event.severity.value,
            service=event.service,
        )

        snapshot = self._registry.snapshot()
        decision = self._router.route(event, snapshot)
        log.info(
            "supervisor.routing.decision",
            primary=decision.primary_agent,
            fallbacks=list(decision.fallback_agents),
            requires_human_approval=decision.requires_human_approval,
            rationale=decision.rationale,
        )

        if not decision.is_routable:
            trace.terminal_status = "unroutable"
            trace.rationale = decision.rationale
            trace.finished_at = datetime.now(UTC)
            await self._journal.append(
                kind="incident.unroutable",
                payload=trace.as_audit_record(),
            )
            return trace

        if decision.requires_human_approval:
            # We still build the plan so an operator can review it, but we
            # do not execute it. The audit record captures the proposed
            # plan for the approval workflow to act on.
            trace.plan = self._build_plan(event, decision)
            trace.terminal_status = "awaiting_human_approval"
            trace.rationale = decision.rationale
            trace.finished_at = datetime.now(UTC)
            await self._journal.append(
                kind="incident.awaiting_approval",
                payload=trace.as_audit_record(),
            )
            return trace

        # Build and execute the plan, falling through fallbacks on terminal
        # primary-agent failure.
        plan = self._build_plan(event, decision)
        trace.plan = plan

        outcomes_by_step: dict[str, AgentOutcome] = {}
        primary_failed = False

        for step in plan.steps:
            outcome = await self._executor.execute_step(step, event, plan_id=plan.plan_id)
            trace.outcomes.append(outcome)
            outcomes_by_step[step.step_id] = outcome
            if not outcome.success:
                primary_failed = True
                break

        if not primary_failed:
            trace.terminal_status = "remediated"
            trace.rationale = decision.rationale
            trace.finished_at = datetime.now(UTC)
            await self._journal.append(
                kind="incident.remediated",
                payload=trace.as_audit_record(),
            )
            return trace

        # Primary failed — rotate to fallback agents one at a time.
        for fallback in decision.fallback_agents:
            log.info("supervisor.fallback.attempt", fallback=fallback)
            fallback_step = self._build_single_step(
                event=event,
                agent_name=fallback,
                intent=f"fallback_remediation:{event.incident_class.value}",
            )
            plan.steps.append(fallback_step)
            outcome = await self._executor.execute_step(
                fallback_step, event, plan_id=plan.plan_id
            )
            trace.outcomes.append(outcome)
            outcomes_by_step[fallback_step.step_id] = outcome
            if outcome.success:
                trace.terminal_status = "remediated_via_fallback"
                trace.rationale = (
                    f"primary {plan.primary_agent} failed; "
                    f"fallback {fallback} succeeded"
                )
                trace.finished_at = datetime.now(UTC)
                await self._journal.append(
                    kind="incident.remediated_via_fallback",
                    payload=trace.as_audit_record(),
                )
                return trace

        # All agents failed — roll back any effectful steps.
        log.error(
            "supervisor.terminal_failure",
            attempted_agents=[plan.primary_agent, *plan.fallback_agents],
        )
        trace.compensations = await self._recovery.rollback_plan(
            plan, event, outcomes_by_step
        )
        trace.terminal_status = "failed_rolled_back"
        trace.rationale = (
            f"all agents exhausted for {event.incident_class.value}; "
            f"rollback executed"
        )
        trace.finished_at = datetime.now(UTC)
        await self._journal.append(
            kind="incident.failed_rolled_back",
            payload=trace.as_audit_record(),
        )
        return trace

    # ------------------------------------------------------------------
    # Plan construction.
    # ------------------------------------------------------------------

    def _build_plan(self, event: NormalizedEvent, decision) -> RemediationPlan:
        primary_step = self._build_single_step(
            event=event,
            agent_name=decision.primary_agent,
            intent=f"remediate:{event.incident_class.value}",
        )
        return RemediationPlan(
            correlation_id=event.correlation_id,
            incident_class=event.incident_class,
            severity=event.severity,
            steps=[primary_step],
            primary_agent=decision.primary_agent,
            fallback_agents=decision.fallback_agents,
            requires_human_approval=decision.requires_human_approval,
            notes=decision.rationale,
        )

    def _build_single_step(
        self,
        *,
        event: NormalizedEvent,
        agent_name: str,
        intent: str,
    ) -> RemediationStep:
        entry = self._registry.get(agent_name)
        cap = entry.capability if entry else None
        return RemediationStep(
            agent=agent_name,
            intent=intent,
            inputs={
                "service": event.service,
                "environment": event.environment,
                "region": event.region,
                "metrics": event.metrics,
                "indicators": event.indicators,
                "tags": event.tags,
            },
            timeout_seconds=cap.timeout_seconds if cap else 30.0,
            max_retries=cap.max_retries if cap else 2,
            compensating_intent=f"compensate:{intent}",
        )
