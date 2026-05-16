"""Priority + fairness tests for the scheduler.

The scheduler is asserted against two pathologies it exists to prevent:
inversion (low-severity blocking high) and starvation (sustained high
locking out low). Both get explicit assertions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentic_solution.orchestrator.contracts import (
    IncidentClass,
    NormalizedEvent,
    SeverityTier,
    TriggerSource,
)
from agentic_solution.orchestrator.runtime.scheduler import PriorityScheduler


def _event(severity: SeverityTier, label: str) -> NormalizedEvent:
    return NormalizedEvent(
        correlation_id=label,
        fingerprint=label,
        source=TriggerSource.MANUAL,
        incident_class=IncidentClass.CPU_SPIKE,
        severity=severity,
        received_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_higher_severity_drains_first():
    s = PriorityScheduler()
    await s.submit(_event(SeverityTier.SEV4, "hygiene"))
    await s.submit(_event(SeverityTier.SEV3, "warn"))
    await s.submit(_event(SeverityTier.SEV0, "fire"))
    first = await s.next()
    assert first.correlation_id == "fire"


@pytest.mark.asyncio
async def test_equal_severity_drains_in_fifo_order():
    s = PriorityScheduler()
    await s.submit(_event(SeverityTier.SEV2, "first"))
    await s.submit(_event(SeverityTier.SEV2, "second"))
    a = await s.next()
    b = await s.next()
    assert (a.correlation_id, b.correlation_id) == ("first", "second")


@pytest.mark.asyncio
async def test_fairness_slots_eventually_serve_low_severity_under_sev0_storm():
    """The starvation guarantee — even with a deluge of SEV0s, a SEV4
    must drain inside one fairness cycle."""
    s = PriorityScheduler()
    # Pre-stage one SEV4 hygiene item and a steady stream of SEV0s.
    await s.submit(_event(SeverityTier.SEV4, "hygiene"))
    for i in range(200):
        await s.submit(_event(SeverityTier.SEV0, f"fire-{i}"))

    drained = []
    for _ in range(180):
        ev = await s.next()
        drained.append(ev.correlation_id)
        if ev.correlation_id == "hygiene":
            break

    assert "hygiene" in drained, (
        "SEV4 hygiene item must drain within a fairness cycle even under SEV0 pressure"
    )


@pytest.mark.asyncio
async def test_depth_reports_queue_length():
    s = PriorityScheduler()
    assert s.depth() == 0
    await s.submit(_event(SeverityTier.SEV2, "x"))
    assert s.depth() == 1
    await s.next()
    assert s.depth() == 0


@pytest.mark.asyncio
async def test_blocks_until_event_available():
    """`next()` blocks rather than spinning — verified by checking that
    the awaitable does not complete before a submit happens."""
    import asyncio

    s = PriorityScheduler()
    task = asyncio.create_task(s.next())
    await asyncio.sleep(0.05)
    assert not task.done()
    await s.submit(_event(SeverityTier.SEV2, "x"))
    result = await asyncio.wait_for(task, timeout=1.0)
    assert result.correlation_id == "x"
