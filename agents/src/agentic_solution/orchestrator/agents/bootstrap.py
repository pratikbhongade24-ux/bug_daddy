"""
Agent bootstrap.

Importing this module triggers the ``@register_agent`` side effects in
every default agent module, then instantiates and registers each one
against the supplied registry under its declared circuit breaker.

Plugin-style extension: third-party packages can ``@register_agent``
their own subclasses and call ``bootstrap_default_agents`` with their
modules already imported — the registration list is global within the
process so any class decorated before bootstrap will be registered."""

from __future__ import annotations

from ..runtime.circuit_breaker import BreakerConfig, CircuitBreaker
from ..routing.registry import AgentRegistry

# Importing the agent modules registers their classes via the decorator.
from . import availability  # noqa: F401
from . import capacity  # noqa: F401
from . import hygiene  # noqa: F401
from . import security  # noqa: F401
from .base import iter_registered_agent_classes


def bootstrap_default_agents(
    registry: AgentRegistry,
    *,
    breaker_config: BreakerConfig | None = None,
) -> tuple[str, ...]:
    """Instantiate every registered agent class and register it.

    Returns the tuple of agent names registered, for log emission at
    runtime startup."""
    names: list[str] = []
    for cls in iter_registered_agent_classes():
        agent = cls()
        breaker = CircuitBreaker(
            name=agent.capability.name,
            config=breaker_config,
        )
        registry.register(agent, breaker=breaker)
        names.append(agent.capability.name)
    return tuple(names)
