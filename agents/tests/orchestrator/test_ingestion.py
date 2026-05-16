"""Ingestion-gate tests: durable journaling, dedup, backpressure."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from agentic_solution.orchestrator.contracts import RawTrigger, TriggerSource
from agentic_solution.orchestrator.observability.audit import AuditJournal
from agentic_solution.orchestrator.observability.logging import StructuredLogger
from agentic_solution.orchestrator.runtime.ingestion import IngestionGate


def _trigger(hint=None):
    return RawTrigger(
        source=TriggerSource.MANUAL,
        received_at=datetime.now(UTC),
        payload={"foo": "bar"},
        correlation_hint=hint,
    )


@pytest.fixture
def gate(silent_logger):
    journal = AuditJournal()
    return IngestionGate(
        journal=journal,
        logger=silent_logger,
        max_queue=4,
        dedup_window_seconds=0.5,
    )


@pytest.mark.asyncio
async def test_accepts_unique_triggers(gate):
    assert await gate.submit(_trigger(hint="a"))
    assert await gate.submit(_trigger(hint="b"))
    assert gate.stats.accepted == 2
    assert gate.stats.deduplicated == 0


@pytest.mark.asyncio
async def test_dedups_within_window(gate):
    assert await gate.submit(_trigger(hint="same"))
    assert not await gate.submit(_trigger(hint="same"))
    assert gate.stats.deduplicated == 1


@pytest.mark.asyncio
async def test_dedup_expires_after_window(gate):
    assert await gate.submit(_trigger(hint="same"))
    await asyncio.sleep(0.6)
    assert await gate.submit(_trigger(hint="same"))
    assert gate.stats.accepted == 2


@pytest.mark.asyncio
async def test_backpressure_rejects_when_queue_full(gate):
    """`block=False` is the non-blocking webhook path — must shed load
    rather than stall the caller."""
    for i in range(4):
        await gate.submit(_trigger(hint=f"k-{i}"))
    accepted = await gate.submit(_trigger(hint="overflow"), block=False)
    assert accepted is False
    assert gate.stats.backpressured == 1


@pytest.mark.asyncio
async def test_journal_records_every_accepted_trigger():
    journal = AuditJournal()
    gate = IngestionGate(
        journal=journal,
        logger=StructuredLogger(),
        max_queue=10,
        dedup_window_seconds=10.0,
    )
    await gate.submit(_trigger(hint="x"))
    records = await journal.snapshot()
    assert any(r.kind == "trigger.received" for r in records)
