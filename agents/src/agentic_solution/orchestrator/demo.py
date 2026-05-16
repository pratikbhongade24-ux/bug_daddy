"""
Demo runner — exercises every layer of the orchestrator end-to-end.

Run with::

    python -m agentic_solution.orchestrator.demo

Emits a structured-JSON log stream to stdout. The final block prints a
human-readable summary of incident traces so a reviewer can see, at a
glance, that priority scheduling did its job and the routing decisions
matched the declared capability manifests."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter

from .orchestrator import OrchestratorConfig, build_default_orchestrator
from .samples import build_sample_triggers


async def _run() -> int:
    orch = build_default_orchestrator(config=OrchestratorConfig(worker_count=4))
    await orch.start()
    try:
        for trigger in build_sample_triggers():
            await orch.submit(trigger)
        await orch.run_until_idle(timeout=10.0)
    finally:
        await orch.stop()

    traces = await orch.traces()
    summary = _summarize(traces)
    sys.stdout.write("\n=== Orchestrator demo summary ===\n")
    sys.stdout.write(json.dumps(summary, indent=2, default=str))
    sys.stdout.write("\n")
    return 0


def _summarize(traces) -> dict:
    by_status = Counter(t.terminal_status for t in traces)
    by_class = Counter(t.event.incident_class.value for t in traces)
    by_severity = Counter(t.event.severity.value for t in traces)
    by_agent: Counter = Counter()
    for t in traces:
        for o in t.outcomes:
            by_agent[o.agent] += 1
    return {
        "incidents_handled": len(traces),
        "by_terminal_status": dict(by_status),
        "by_incident_class": dict(by_class),
        "by_severity": dict(by_severity),
        "by_agent_dispatch_count": dict(by_agent),
        "first_handled": traces[0].event.incident_class.value if traces else None,
        "ordered_severities": [t.event.severity.value for t in traces],
    }


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
