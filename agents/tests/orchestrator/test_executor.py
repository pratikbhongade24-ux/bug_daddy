"""Executor-level reliability tests: retries, timeouts, breaker integration."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from agentic_solution.orchestrator.agents.base import (
    BaseRemediationAgent,
    make_outcome,
    utcnow,
)
from agentic_solution.orchestrator.contracts import (
    AgentCapability,
    IncidentClass,
    NormalizedEvent,
    RemediationStep,
    SeverityTier,
    StepStatus,
    TriggerSource,
)
from agentic_solution.orchestrator.observability.logging import StructuredLogger
from agentic_solution.orchestrator.routing.registry import AgentRegistry
from agentic_solution.orchestrator.runtime.circuit_breaker import (
    BreakerConfig,
    CircuitBreaker,
)
from agentic_solution.orchestrator.runtime.executor import AgentExecutor


def _event():
    return NormalizedEvent(
        correlation_id="c",
        fingerprint="f",
        source=TriggerSource.MANUAL,
        incident_class=IncidentClass.CPU_SPIKE,
        severity=SeverityTier.SEV2,
        received_at=datetime.now(UTC),
    )


class _FlakyAgent(BaseRemediationAgent):
    """Fails ``fail_first_n`` calls, then succeeds."""

    capability = AgentCapability(
        name="flaky",
        description="x",
        handles=(IncidentClass.CPU_SPIKE,),
        timeout_seconds=1.0,
        max_retries=3,
    )

    def __init__(self, fail_first_n: int):
        self.calls = 0
        self.fail_first_n = fail_first_n

    async def execute(self, step, event, ctx):
        self.calls += 1
        started = utcnow()
        if self.calls <= self.fail_first_n:
            return make_outcome(
                agent=self.capability.name,
                step_id=step.step_id,
                success=False,
                started_at=started,
                error="simulated failure",
            )
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={"calls": self.calls},
        )


class _SlowAgent(BaseRemediationAgent):
    capability = AgentCapability(
        name="slow",
        description="x",
        handles=(IncidentClass.CPU_SPIKE,),
        timeout_seconds=0.1,
        max_retries=0,
    )

    async def execute(self, step, event, ctx):
        await asyncio.sleep(0.5)
        return make_outcome(agent=self.capability.name, step_id=step.step_id, success=True, started_at=utcnow())


class _BoomAgent(BaseRemediationAgent):
    capability = AgentCapability(
        name="boom",
        description="x",
        handles=(IncidentClass.CPU_SPIKE,),
        timeout_seconds=1.0,
        max_retries=0,
    )

    async def execute(self, step, event, ctx):
        raise RuntimeError("kaboom")


def _make_executor(agent):
    reg = AgentRegistry()
    reg.register(agent, breaker=CircuitBreaker(name=agent.capability.name))
    return AgentExecutor(registry=reg, logger=StructuredLogger()), reg


def _step(agent_name: str, *, timeout=None, retries=None) -> RemediationStep:
    kwargs = {"agent": agent_name, "intent": "test"}
    if timeout is not None:
        kwargs["timeout_seconds"] = timeout
    if retries is not None:
        kwargs["max_retries"] = retries
    return RemediationStep(**kwargs)


@pytest.mark.asyncio
async def test_executor_retries_until_success():
    agent = _FlakyAgent(fail_first_n=2)
    executor, _ = _make_executor(agent)

    step = _step("flaky", retries=3)
    outcome = await executor.execute_step(step, _event(), plan_id="p")

    assert outcome.success is True
    assert agent.calls == 3
    assert step.status is StepStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_executor_gives_up_after_max_retries():
    agent = _FlakyAgent(fail_first_n=99)
    executor, _ = _make_executor(agent)

    step = _step("flaky", retries=2)
    outcome = await executor.execute_step(step, _event(), plan_id="p")

    assert outcome.success is False
    assert agent.calls == 3  # 1 initial + 2 retries
    assert step.status is StepStatus.FAILED


@pytest.mark.asyncio
async def test_executor_records_timeout():
    executor, _ = _make_executor(_SlowAgent())
    step = _step("slow", timeout=0.05, retries=0)
    outcome = await executor.execute_step(step, _event(), plan_id="p")

    assert outcome.success is False
    assert step.status is StepStatus.TIMED_OUT


@pytest.mark.asyncio
async def test_executor_catches_uncaught_exceptions():
    """An agent that raises must not propagate past the executor — uniform
    outcome envelope is the contract the supervisor depends on."""
    executor, _ = _make_executor(_BoomAgent())
    step = _step("boom", retries=0)
    outcome = await executor.execute_step(step, _event(), plan_id="p")

    assert outcome.success is False
    assert "kaboom" in outcome.error


@pytest.mark.asyncio
async def test_executor_returns_failed_outcome_when_agent_missing():
    reg = AgentRegistry()
    executor = AgentExecutor(registry=reg, logger=StructuredLogger())
    step = _step("missing")
    outcome = await executor.execute_step(step, _event(), plan_id="p")
    assert outcome.success is False
    assert "agent_not_registered" in outcome.error


@pytest.mark.asyncio
async def test_executor_stops_retrying_once_breaker_opens():
    """When the breaker trips mid-retry chain, the executor exits early
    rather than burning through every retry against a known-bad agent."""
    agent = _FlakyAgent(fail_first_n=99)
    reg = AgentRegistry()
    breaker = CircuitBreaker(
        name="flaky",
        config=BreakerConfig(
            window_seconds=60.0,
            min_samples=2,
            failure_ratio_threshold=0.5,
            cooldown_seconds=60.0,
        ),
    )
    reg.register(agent, breaker=breaker)
    executor = AgentExecutor(registry=reg, logger=StructuredLogger())

    step = _step("flaky", retries=10)
    outcome = await executor.execute_step(step, _event(), plan_id="p")

    assert outcome.success is False
    # Min samples = 2 + threshold 0.5 → breaker trips after 2 failures.
    # Executor should bail out and not exhaust all 10 retries.
    assert agent.calls < 10
