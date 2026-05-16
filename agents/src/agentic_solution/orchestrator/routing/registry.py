"""
Agent Registry & Capability Discovery.

The registry is the source of truth for *which* agents the runtime can
dispatch and *how healthy* each one is. It is concurrency-safe, supports
hot registration / draining without restart, and exposes a snapshot
abstraction so the router can make a routing decision against an
immutable view of the world — concurrent capability changes cannot race
into the middle of a dispatch.

Health is a derived view of the circuit breaker over each agent. Capacity
is tracked with per-agent semaphores so that a misbehaving agent cannot
saturate the global executor.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..contracts import AgentCapability, AgentStatus, IncidentClass

if TYPE_CHECKING:  # pragma: no cover
    from ..agents.base import BaseRemediationAgent
    from ..runtime.circuit_breaker import CircuitBreaker


@dataclass
class RegistryEntry:
    """Single registration. Holds the live agent, its declared capability,
    a per-agent concurrency semaphore, and the breaker that gates its
    dispatchability."""

    agent: BaseRemediationAgent
    capability: AgentCapability
    semaphore: asyncio.Semaphore
    breaker: CircuitBreaker
    status_override: AgentStatus | None = None

    @property
    def status(self) -> AgentStatus:
        if self.status_override is not None:
            return self.status_override
        return self.breaker.derived_status()


@dataclass(frozen=True)
class RegistrySnapshot:
    """Immutable view of the registry at a point in time. Routing
    decisions read this; the registry itself can mutate concurrently."""

    entries: tuple[RegistryEntry, ...] = field(default_factory=tuple)

    def candidates_for(self, incident_class: IncidentClass) -> tuple[RegistryEntry, ...]:
        return tuple(
            e
            for e in self.entries
            if incident_class in e.capability.handles
            and e.status not in (AgentStatus.DISABLED, AgentStatus.DRAINING)
        )


class AgentRegistry:
    """Thread-safe agent registry. Synchronous API on purpose: registration
    is rare and the cost of a coarse lock is negligible compared to the
    safety of fully consistent snapshots."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, RegistryEntry] = {}

    # ------------------------------------------------------------------
    # Mutation API.
    # ------------------------------------------------------------------

    def register(
        self,
        agent: BaseRemediationAgent,
        *,
        breaker: CircuitBreaker,
    ) -> RegistryEntry:
        """Register an agent. Re-registering under the same name replaces
        the prior entry; the old entry's semaphore is *not* reused so any
        in-flight calls finish under the prior accounting."""
        capability = agent.capability
        entry = RegistryEntry(
            agent=agent,
            capability=capability,
            semaphore=asyncio.Semaphore(capability.concurrency),
            breaker=breaker,
        )
        with self._lock:
            self._entries[capability.name] = entry
        return entry

    def drain(self, name: str) -> None:
        """Mark an agent draining — no new dispatches, in-flight work
        continues. Useful for safe rolling deploys of an individual agent."""
        with self._lock:
            entry = self._entries.get(name)
            if entry is not None:
                entry.status_override = AgentStatus.DRAINING

    def disable(self, name: str) -> None:
        """Hard-disable an agent. Use for emergency takeout."""
        with self._lock:
            entry = self._entries.get(name)
            if entry is not None:
                entry.status_override = AgentStatus.DISABLED

    def restore(self, name: str) -> None:
        """Clear any status override, returning the agent to breaker-derived health."""
        with self._lock:
            entry = self._entries.get(name)
            if entry is not None:
                entry.status_override = None

    # ------------------------------------------------------------------
    # Read API.
    # ------------------------------------------------------------------

    def get(self, name: str) -> RegistryEntry | None:
        with self._lock:
            return self._entries.get(name)

    def snapshot(self) -> RegistrySnapshot:
        """Capture an immutable snapshot. Routing always reads this."""
        with self._lock:
            return RegistrySnapshot(entries=tuple(self._entries.values()))

    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._entries.keys())
