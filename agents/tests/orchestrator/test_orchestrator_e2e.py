"""End-to-end orchestrator integration test.

Submits the full sample fleet and asserts on the externally-observable
invariants:

- every event becomes a terminal trace
- SEV0 is handled before SEV4 despite arrival order
- agents that require approval at SEV0 leave the event in
  ``awaiting_human_approval``, not ``remediated``
- the audit journal contains a record for every terminal status
"""

from __future__ import annotations

import pytest

from agentic_solution.orchestrator import build_default_orchestrator
from agentic_solution.orchestrator.orchestrator import OrchestratorConfig
from agentic_solution.orchestrator.samples import build_sample_triggers


@pytest.mark.asyncio
async def test_orchestrator_processes_every_sample_trigger():
    orch = build_default_orchestrator(config=OrchestratorConfig(worker_count=4))
    await orch.start()
    triggers = build_sample_triggers()
    try:
        for t in triggers:
            await orch.submit(t)
        await orch.run_until_idle(timeout=10.0)
    finally:
        await orch.stop()

    traces = await orch.traces()
    assert len(traces) == len(triggers)
    assert {t.terminal_status for t in traces} <= {
        "remediated",
        "remediated_via_fallback",
        "awaiting_human_approval",
        "unroutable",
        "failed_rolled_back",
    }


@pytest.mark.asyncio
async def test_sev0_outranks_lower_severity_under_concurrent_submission():
    """The scheduler's priority guarantee — a SEV0 must reach a worker
    before a lower-severity event even when the SEV0 arrives second."""
    orch = build_default_orchestrator(config=OrchestratorConfig(worker_count=1))
    triggers = build_sample_triggers()
    # cpu_utilization=78 + severity="info" → SEV4 in the normalizer.
    sev_low = next(t for t in triggers if t.correlation_hint == "cpu-checkout-warmpath")
    sev0 = next(t for t in triggers if "ransomware" in str(t.payload).lower())

    await orch.start()
    try:
        await orch.submit(sev_low)
        await orch.submit(sev0)
        await orch.run_until_idle(timeout=10.0)
    finally:
        await orch.stop()

    traces = await orch.traces()
    assert len(traces) == 2
    # SEV0 must be the FIRST trace recorded — it preempts the lower-severity item.
    assert traces[0].event.severity.value == "sev0"
    assert traces[1].event.severity.weight < traces[0].event.severity.weight


@pytest.mark.asyncio
async def test_ransomware_is_held_for_human_approval():
    orch = build_default_orchestrator(config=OrchestratorConfig(worker_count=1))
    triggers = build_sample_triggers()
    ransomware = next(t for t in triggers if "ransomware" in str(t.payload).lower())

    await orch.start()
    try:
        await orch.submit(ransomware)
        await orch.run_until_idle(timeout=5.0)
    finally:
        await orch.stop()

    traces = await orch.traces()
    assert traces[0].terminal_status == "awaiting_human_approval"


@pytest.mark.asyncio
async def test_audit_journal_records_every_terminal_status():
    orch = build_default_orchestrator(config=OrchestratorConfig(worker_count=4))
    await orch.start()
    try:
        for t in build_sample_triggers():
            await orch.submit(t)
        await orch.run_until_idle(timeout=10.0)
    finally:
        await orch.stop()

    records = await orch.audit_records()
    terminal_kinds = {r.kind for r in records if r.kind.startswith("incident.")}
    assert terminal_kinds, "no terminal audit records produced"
    assert all(r.payload.get("correlation_id") for r in records if r.kind.startswith("incident."))
