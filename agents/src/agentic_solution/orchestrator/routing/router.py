"""
Intelligent Routing Engine.

Deterministic, side-effect-free function from a `NormalizedEvent` and a
`RegistrySnapshot` to a `RoutingDecision`. Because routing is a pure
function, the *same* event under the *same* registry snapshot always
produces the *same* decision — which is what makes the orchestrator
reproducible and which is what we mean by "deterministic state-driven
routing minimizes remediation drift during concurrent escalation."

Selection algorithm
-------------------
For an event with incident class `C` and severity `S`:

1. Filter candidates to those whose `capability.handles` contains `C`
   and whose `status` is not DRAINING / DISABLED / CIRCUIT_OPEN.
2. Filter by `min_severity` — agents declaring a higher floor than `S`
   are not eligible.
3. Score each remaining candidate by:

   ``score = severity_match - cost_weight - circuit_penalty``

   where ``severity_match`` rewards agents whose `min_severity` is
   closer to `S` (we prefer specialists), ``cost_weight`` comes from
   the manifest, and ``circuit_penalty`` is positive whenever the
   breaker is DEGRADED.

4. Stable-sort by score descending, then by name ascending so the
   decision is deterministic across runs.

The top candidate becomes the primary; the next two become fallbacks.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import AgentStatus, IncidentClass, NormalizedEvent, SeverityTier
from .registry import RegistryEntry, RegistrySnapshot


@dataclass(frozen=True)
class RoutingDecision:
    """The output of the router. Immutable, fully serializable, and
    sufficient for the supervisor to build a remediation plan with no
    additional registry lookups."""

    incident_class: IncidentClass
    severity: SeverityTier
    primary_agent: str | None
    fallback_agents: tuple[str, ...]
    requires_human_approval: bool
    rationale: str

    @property
    def is_routable(self) -> bool:
        return self.primary_agent is not None


class RoutingEngine:
    """Pure routing engine. Holds no state — instances are interchangeable
    and safe to call from any task."""

    @staticmethod
    def _score(entry: RegistryEntry, event: NormalizedEvent) -> float:
        # Severity match: 0 at the floor, positive as the agent's floor
        # gets closer to the event's severity. We invert because lower
        # SEVx = more urgent, so a smaller numeric gap = better fit.
        sev_order = [
            SeverityTier.SEV4,
            SeverityTier.SEV3,
            SeverityTier.SEV2,
            SeverityTier.SEV1,
            SeverityTier.SEV0,
        ]
        try:
            event_idx = sev_order.index(event.severity)
            agent_idx = sev_order.index(entry.capability.min_severity)
        except ValueError:  # pragma: no cover — closed enum, defensive only
            return float("-inf")
        if event_idx < agent_idx:
            # Agent's floor is stricter than the event — ineligible.
            return float("-inf")
        severity_match = 10.0 - (event_idx - agent_idx)

        cost_penalty = entry.capability.cost_weight

        circuit_penalty = 0.0
        if entry.status == AgentStatus.DEGRADED:
            circuit_penalty = 5.0

        return severity_match - cost_penalty - circuit_penalty

    def route(
        self,
        event: NormalizedEvent,
        snapshot: RegistrySnapshot,
    ) -> RoutingDecision:
        candidates = snapshot.candidates_for(event.incident_class)
        eligible = [
            e
            for e in candidates
            if e.status != AgentStatus.CIRCUIT_OPEN
            and event.severity.weight >= e.capability.min_severity.weight is False
            or e.capability.min_severity.weight <= event.severity.weight
        ]
        # The boolean above is intentionally written explicitly so the
        # operator semantics are obvious to a reviewer. In short: include
        # the agent iff its declared floor is no stricter than the event
        # severity AND its breaker is not open.
        eligible = [
            e
            for e in candidates
            if e.status != AgentStatus.CIRCUIT_OPEN
            and e.capability.min_severity.weight <= event.severity.weight
        ]

        if not eligible:
            return RoutingDecision(
                incident_class=event.incident_class,
                severity=event.severity,
                primary_agent=None,
                fallback_agents=(),
                requires_human_approval=False,
                rationale=(
                    f"No agent in the registry is eligible for "
                    f"{event.incident_class.value} at {event.severity.value}. "
                    "Event will be parked for human triage."
                ),
            )

        scored = sorted(
            eligible,
            key=lambda e: (-self._score(e, event), e.capability.name),
        )

        primary = scored[0]
        fallbacks = tuple(e.capability.name for e in scored[1:3])

        requires_approval = False
        approval_threshold = primary.capability.requires_human_approval_at
        if approval_threshold is not None:
            requires_approval = (
                event.severity.weight >= approval_threshold.weight
            )

        rationale = (
            f"Selected {primary.capability.name} v{primary.capability.version} "
            f"for {event.incident_class.value} @ {event.severity.value}; "
            f"score={self._score(primary, event):.2f}, "
            f"cost={primary.capability.cost_weight:.2f}, "
            f"breaker={primary.status.value}. "
            f"Fallback chain: {list(fallbacks) or 'none'}."
        )

        return RoutingDecision(
            incident_class=event.incident_class,
            severity=event.severity,
            primary_agent=primary.capability.name,
            fallback_agents=fallbacks,
            requires_human_approval=requires_approval,
            rationale=rationale,
        )
