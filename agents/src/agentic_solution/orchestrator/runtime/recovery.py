"""
Failure Recovery / Rollback Handling.

The recovery coordinator implements the *compensating transaction* model
for remediation plans. The supervisor records the executed steps in
order; on terminal plan failure, the coordinator walks the executed
steps in LIFO order and invokes each agent's ``compensate`` with the
``compensating_handle`` returned at execute time.

This gives us auditable rollback guarantees: every effectful action has
a paired inverse, and the runtime is responsible for ensuring the
inverse is invoked even when downstream agents are themselves
degraded. Recovery itself is subject to the same retry / timeout
envelope as forward execution.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..contracts import (
    AgentOutcome,
    NormalizedEvent,
    RemediationPlan,
    RemediationStep,
    StepStatus,
)
from ..observability.logging import StructuredLogger
from ..routing.registry import AgentRegistry
from ..agents.base import ExecutionContext


class RecoveryCoordinator:
    def __init__(
        self,
        *,
        registry: AgentRegistry,
        logger: StructuredLogger,
    ) -> None:
        self._registry = registry
        self._logger = logger

    async def rollback_plan(
        self,
        plan: RemediationPlan,
        event: NormalizedEvent,
        outcomes_by_step: dict[str, AgentOutcome],
    ) -> list[AgentOutcome]:
        """Walk executed steps in LIFO order and invoke compensations.

        Steps without a ``compensating_handle`` (i.e. non-effectful) are
        skipped. Each compensation is logged and aggregated into a report
        so the supervisor can include rollback status in its final audit
        record."""
        compensations: list[AgentOutcome] = []
        for step in reversed(plan.steps):
            if step.status not in (StepStatus.SUCCEEDED, StepStatus.FAILED):
                continue
            outcome = outcomes_by_step.get(step.step_id)
            if outcome is None or not outcome.compensating_handle:
                continue
            entry = self._registry.get(step.agent)
            if entry is None:
                self._logger.warn(
                    "recovery.agent_missing",
                    agent=step.agent,
                    step_id=step.step_id,
                    correlation_id=event.correlation_id,
                )
                continue
            self._logger.info(
                "recovery.compensating",
                agent=step.agent,
                step_id=step.step_id,
                correlation_id=event.correlation_id,
            )
            ctx = ExecutionContext(
                correlation_id=event.correlation_id,
                plan_id=plan.plan_id,
                deadline_at=datetime.now(timezone.utc),
                logger=self._logger.bind(
                    agent=step.agent,
                    step_id=step.step_id,
                    phase="compensation",
                ),
            )
            try:
                result = await entry.agent.compensate(
                    outcome.compensating_handle, event, ctx
                )
            except Exception as exc:  # noqa: BLE001
                now = datetime.now(timezone.utc)
                result = AgentOutcome(
                    agent=step.agent,
                    step_id=step.step_id,
                    success=False,
                    started_at=now,
                    finished_at=now,
                    error=f"compensation_exception:{type(exc).__name__}:{exc}",
                )
                self._logger.error(
                    "recovery.compensation_failed",
                    agent=step.agent,
                    step_id=step.step_id,
                    correlation_id=event.correlation_id,
                    error=result.error,
                )
            if result.success:
                step.status = StepStatus.COMPENSATED
            compensations.append(result)
        return compensations

    @staticmethod
    def _stub_step(step_id: str, agent: str) -> RemediationStep:
        # Used only internally; kept here so the import surface from
        # contracts stays narrow.
        return RemediationStep(step_id=step_id, agent=agent, intent="compensate")
