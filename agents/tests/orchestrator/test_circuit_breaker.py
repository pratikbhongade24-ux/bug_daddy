"""Circuit breaker state-machine tests.

The breaker is the safety boundary around every agent — every transition
gets a dedicated assertion."""

from __future__ import annotations

import asyncio

import pytest

from agentic_solution.orchestrator.contracts import AgentStatus
from agentic_solution.orchestrator.runtime.circuit_breaker import (
    BreakerConfig,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


def _breaker(**overrides):
    config = BreakerConfig(
        window_seconds=60.0,
        min_samples=4,
        failure_ratio_threshold=0.5,
        cooldown_seconds=0.05,
        degraded_ratio_threshold=0.2,
    )
    for k, v in overrides.items():
        setattr(config, k, v)
    return CircuitBreaker(name="t", config=config)


@pytest.mark.asyncio
async def test_starts_closed_and_healthy():
    b = _breaker()
    assert b.state is CircuitState.CLOSED
    assert b.derived_status() is AgentStatus.HEALTHY


@pytest.mark.asyncio
async def test_does_not_trip_under_min_samples():
    """Three failures with min_samples=4 must not trip — protects low-traffic
    agents from being declared dead off a single transient blip."""
    b = _breaker()
    for _ in range(3):
        async with b:
            pass
        await b.record_failure()
    assert b.state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_trips_when_failure_ratio_crosses_threshold():
    b = _breaker()
    for _ in range(2):
        async with b:
            pass
        await b.record_success()
    for _ in range(2):
        async with b:
            pass
        await b.record_failure()
    # 2/4 = 0.5 == threshold (>=).
    assert b.state is CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_breaker_rejects_admission():
    b = _breaker()
    for _ in range(4):
        async with b:
            pass
        await b.record_failure()
    assert b.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        async with b:
            pass


@pytest.mark.asyncio
async def test_half_open_probe_admits_one_call_then_closes_on_success():
    b = _breaker()
    for _ in range(4):
        async with b:
            pass
        await b.record_failure()
    await asyncio.sleep(0.1)  # past cooldown
    async with b:
        pass
    assert b.state is CircuitState.HALF_OPEN
    await b.record_success()
    assert b.state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_reopens_on_probe_failure():
    b = _breaker()
    for _ in range(4):
        async with b:
            pass
        await b.record_failure()
    await asyncio.sleep(0.1)
    async with b:
        pass
    await b.record_failure()
    assert b.state is CircuitState.OPEN


@pytest.mark.asyncio
async def test_derived_status_reports_degraded_below_open_threshold():
    """When the failure ratio sits between degraded and trip thresholds,
    the breaker stays closed but the registry marks the agent DEGRADED so
    the router can score-penalize it."""
    b = _breaker(failure_ratio_threshold=0.6)
    async with b:
        pass
    await b.record_success()
    async with b:
        pass
    await b.record_success()
    async with b:
        pass
    await b.record_success()
    async with b:
        pass
    await b.record_failure()  # 1/4 = 0.25 (degraded, not tripped)
    assert b.state is CircuitState.CLOSED
    assert b.derived_status() is AgentStatus.DEGRADED


@pytest.mark.asyncio
async def test_half_open_does_not_admit_concurrent_probes():
    """Only one probe is admitted while the breaker is HALF_OPEN —
    otherwise we'd flood a still-degraded downstream with retries."""
    b = _breaker()
    for _ in range(4):
        async with b:
            pass
        await b.record_failure()
    await asyncio.sleep(0.1)
    await b._before_call()  # admits the probe
    with pytest.raises(CircuitOpenError):
        await b._before_call()
