"""Recovery / rollback tests.

Invariants asserted:
- compensations run LIFO
- non-effectful steps (no handle) are skipped
- a failing compensation does not abort subsequent compensations
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentic_solution.orchestrator.agents.base import BaseRemediationAgent, make_outcome, utcnow
from agentic_solution.orchestrator.contracts import (
    AgentCapability,
    AgentOutcome,
    IncidentClass,
    NormalizedEvent,
    RemediationPlan,
    RemediationStep,
    SeverityTier,
    StepStatus,
    TriggerSource,
)
from agentic_solution.orchestrator.observability.logging import StructuredLogger
from agentic_solution.orchestrator.routing.registry import AgentRegistry
from agentic_solution.orchestrator.runtime.circuit_breaker import CircuitBreaker
from agentic_solution.orchestrator.runtime.recovery import RecoveryCoordinator


class _TracingAgent(BaseRemediationAgent):
    capability = AgentCapability(
        name="tracer",
        description="x",
        handles=(IncidentClass.CPU_SPIKE,),
    )

    def __init__(self, name: str, *, fail_compensate: bool = False):
        self.calls: list[str] = []
        self._name = name
        self._fail_compensate = fail_compensate
        self.capability = AgentCapability(
            name=name,
            description="x",
            handles=(IncidentClass.CPU_SPIKE,),
        )

    async def execute(self, step, event, ctx):
        return make_outcome(agent=self._name, step_id=step.step_id, success=True, started_at=utcnow())

    async def compensate(self, handle, event, ctx):
        self.calls.append(handle)
        if self._fail_compensate:
            raise RuntimeError("compensation refused")
        return make_outcome(agent=self._name, step_id=handle, success=True, started_at=utcnow())


def _event():
    return NormalizedEvent(
        correlation_id="c",
        fingerprint="f",
        source=TriggerSource.MANUAL,
        incident_class=IncidentClass.CPU_SPIKE,
        severity=SeverityTier.SEV1,
        received_at=datetime.now(UTC),
    )


def _plan(steps):
    return RemediationPlan(
        correlation_id="c",
        incident_class=IncidentClass.CPU_SPIKE,
        severity=SeverityTier.SEV1,
        steps=steps,
        primary_agent=steps[0].agent if steps else "x",
    )


def _step(agent_name: str, status: StepStatus = StepStatus.SUCCEEDED) -> RemediationStep:
    s = RemediationStep(agent=agent_name, intent="i")
    s.status = status
    return s


def _outcome(step_id: str, agent: str, handle: str | None) -> AgentOutcome:
    now = datetime.now(UTC)
    return AgentOutcome(
        agent=agent,
        step_id=step_id,
        success=True,
        started_at=now,
        finished_at=now,
        compensating_handle=handle,
    )


def _make_recovery(*agents):
    reg = AgentRegistry()
    for a in agents:
        reg.register(a, breaker=CircuitBreaker(name=a.capability.name))
    return RecoveryCoordinator(registry=reg, logger=StructuredLogger()), reg


@pytest.mark.asyncio
async def test_compensations_run_in_lifo_order():
    a1 = _TracingAgent("a1")
    a2 = _TracingAgent("a2")
    a3 = _TracingAgent("a3")
    rec, _ = _make_recovery(a1, a2, a3)

    s1, s2, s3 = _step("a1"), _step("a2"), _step("a3")
    plan = _plan([s1, s2, s3])
    outcomes = {
        s1.step_id: _outcome(s1.step_id, "a1", "h1"),
        s2.step_id: _outcome(s2.step_id, "a2", "h2"),
        s3.step_id: _outcome(s3.step_id, "a3", "h3"),
    }

    compensations = await rec.rollback_plan(plan, _event(), outcomes)

    assert [c.agent for c in compensations] == ["a3", "a2", "a1"]
    assert a3.calls == ["h3"]
    assert a2.calls == ["h2"]
    assert a1.calls == ["h1"]


@pytest.mark.asyncio
async def test_steps_without_handle_are_skipped():
    """Non-effectful steps don't need rollback — they emit no handle, and
    the coordinator must skip them rather than calling the no-op compensate
    and counting it as a phantom compensation."""
    a1 = _TracingAgent("a1")
    rec, _ = _make_recovery(a1)

    s1 = _step("a1")
    plan = _plan([s1])
    outcomes = {s1.step_id: _outcome(s1.step_id, "a1", handle=None)}

    compensations = await rec.rollback_plan(plan, _event(), outcomes)

    assert compensations == []
    assert a1.calls == []


@pytest.mark.asyncio
async def test_failing_compensation_does_not_abort_subsequent_ones():
    """A misbehaving agent in the middle of the rollback chain must not
    stop later compensations from running."""
    a1 = _TracingAgent("a1")
    a2 = _TracingAgent("a2", fail_compensate=True)
    a3 = _TracingAgent("a3")
    rec, _ = _make_recovery(a1, a2, a3)

    s1, s2, s3 = _step("a1"), _step("a2"), _step("a3")
    plan = _plan([s1, s2, s3])
    outcomes = {
        s1.step_id: _outcome(s1.step_id, "a1", "h1"),
        s2.step_id: _outcome(s2.step_id, "a2", "h2"),
        s3.step_id: _outcome(s3.step_id, "a3", "h3"),
    }

    compensations = await rec.rollback_plan(plan, _event(), outcomes)

    # 3 compensations attempted; a2's failed but a1 still ran.
    statuses = [c.success for c in compensations]
    assert statuses == [True, False, True]
    assert a1.calls == ["h1"]
