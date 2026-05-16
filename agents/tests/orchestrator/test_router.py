"""Routing engine tests.

The router is the determinism backbone of the orchestrator — every score
input gets a dedicated test so a future refactor can't silently shift
routing decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_solution.orchestrator.contracts import (
    AgentCapability,
    AgentStatus,
    IncidentClass,
    NormalizedEvent,
    SeverityTier,
    TriggerSource,
)
from agentic_solution.orchestrator.routing.registry import (
    RegistryEntry,
    RegistrySnapshot,
)
from agentic_solution.orchestrator.routing.router import RoutingEngine
from agentic_solution.orchestrator.runtime.circuit_breaker import CircuitBreaker


def _event(severity=SeverityTier.SEV2, cls=IncidentClass.CPU_SPIKE):
    return NormalizedEvent(
        correlation_id="c",
        fingerprint="f",
        source=TriggerSource.MANUAL,
        incident_class=cls,
        severity=severity,
        received_at=datetime.now(UTC),
    )


def _entry(
    name="a",
    handles=(IncidentClass.CPU_SPIKE,),
    *,
    min_sev=SeverityTier.SEV4,
    cost=1.0,
    status_override=None,
    approval_at=None,
):
    import asyncio

    cap = AgentCapability(
        name=name,
        description="x",
        handles=handles,
        min_severity=min_sev,
        cost_weight=cost,
        requires_human_approval_at=approval_at,
    )
    return RegistryEntry(
        agent=None,
        capability=cap,
        semaphore=asyncio.Semaphore(1),
        breaker=CircuitBreaker(name=name),
        status_override=status_override,
    )


class TestRoutingEngine:
    def setup_method(self):
        self.r = RoutingEngine()

    def test_no_candidates_returns_unroutable(self):
        decision = self.r.route(_event(), RegistrySnapshot(entries=()))
        assert decision.primary_agent is None
        assert decision.is_routable is False

    def test_disabled_agent_is_filtered_out(self):
        entry = _entry(status_override=AgentStatus.DISABLED)
        decision = self.r.route(_event(), RegistrySnapshot(entries=(entry,)))
        assert decision.primary_agent is None

    def test_draining_agent_is_filtered_out(self):
        entry = _entry(status_override=AgentStatus.DRAINING)
        decision = self.r.route(_event(), RegistrySnapshot(entries=(entry,)))
        assert decision.primary_agent is None

    def test_agent_with_stricter_floor_is_ineligible(self):
        """An agent declaring min_severity=SEV1 must not handle a SEV3 event."""
        entry = _entry(min_sev=SeverityTier.SEV1)
        decision = self.r.route(_event(severity=SeverityTier.SEV3),
                                RegistrySnapshot(entries=(entry,)))
        assert decision.primary_agent is None

    def test_lower_cost_wins_when_capabilities_tie(self):
        a = _entry(name="cheap", cost=0.5)
        b = _entry(name="expensive", cost=2.5)
        decision = self.r.route(_event(), RegistrySnapshot(entries=(a, b)))
        assert decision.primary_agent == "cheap"
        assert decision.fallback_agents == ("expensive",)

    def test_specialist_outranks_generalist(self):
        """When two agents handle the class, the one whose min_severity is
        *closer* to the event's severity scores higher — i.e. specialists
        outrank catch-all agents."""
        generalist = _entry(name="generalist", min_sev=SeverityTier.SEV4, cost=1.0)
        specialist = _entry(name="specialist", min_sev=SeverityTier.SEV2, cost=1.0)
        decision = self.r.route(_event(severity=SeverityTier.SEV2),
                                RegistrySnapshot(entries=(generalist, specialist)))
        assert decision.primary_agent == "specialist"

    def test_human_approval_required_at_high_severity(self):
        entry = _entry(approval_at=SeverityTier.SEV1)
        decision = self.r.route(_event(severity=SeverityTier.SEV0),
                                RegistrySnapshot(entries=(entry,)))
        assert decision.requires_human_approval is True

    def test_human_approval_not_required_below_threshold(self):
        entry = _entry(approval_at=SeverityTier.SEV0)
        decision = self.r.route(_event(severity=SeverityTier.SEV2),
                                RegistrySnapshot(entries=(entry,)))
        assert decision.requires_human_approval is False

    def test_circuit_open_agent_is_filtered_out(self):
        entry = _entry(status_override=AgentStatus.CIRCUIT_OPEN)
        decision = self.r.route(_event(), RegistrySnapshot(entries=(entry,)))
        assert decision.primary_agent is None

    def test_deterministic_tie_break_by_name(self):
        """When scores tie exactly, the router falls back to name ordering
        — this is what makes the function reproducible across runs."""
        a = _entry(name="aaa")
        b = _entry(name="bbb")
        decision = self.r.route(_event(), RegistrySnapshot(entries=(b, a)))
        assert decision.primary_agent == "aaa"

    def test_rationale_is_human_readable(self):
        entry = _entry()
        decision = self.r.route(_event(), RegistrySnapshot(entries=(entry,)))
        assert "Selected" in decision.rationale
        assert "score=" in decision.rationale
