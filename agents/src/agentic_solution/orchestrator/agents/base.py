"""
Base class and registration decorator for remediation agents.

The base class enforces three invariants that the supervisor relies on:

1. **Outcome uniformity** — every code path returns an `AgentOutcome`; no
   exception is allowed to escape `execute()`. The executor wraps each
   call in a defensive boundary anyway, but enforcing the contract here
   means the *agent author* is responsible for translating failure modes
   into structured outputs, which improves diagnosability.

2. **Compensating-action discipline** — any agent that performs an
   effectful action MUST return a `compensating_handle`. The recovery
   layer uses the handle to invoke the inverse intent without
   re-deriving side-effect state from logs.

3. **Idempotency contract** — every effectful intent is keyed on
   `(correlation_id, step_id)`. Re-invoking the same step is required to
   be observably indistinguishable from invoking it once, which lets the
   supervisor retry freely without amplifying blast radius.
"""

from __future__ import annotations

import abc
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from ..contracts import AgentCapability, AgentOutcome, NormalizedEvent, RemediationStep


@dataclass
class ExecutionContext:
    """Per-invocation context passed to every agent.

    Carries the structured logger (already bound to correlation_id), a
    shared scratchpad for cross-step state within a single plan, and a
    monotonic deadline derived from the step's timeout. Agents should
    treat `deadline_at` as authoritative — the executor will cancel them
    if they overrun, but cooperative checks produce cleaner shutdown."""

    correlation_id: str
    plan_id: str
    deadline_at: datetime
    logger: Any
    scratchpad: dict[str, Any] = field(default_factory=dict)


class BaseRemediationAgent(abc.ABC):
    """Abstract base for every remediation agent in the platform."""

    #: The capability manifest. MUST be defined as a class attribute so
    #: the registry can introspect it without instantiating the agent.
    capability: AgentCapability

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "_abstract", False):
            if not hasattr(cls, "capability"):
                raise TypeError(
                    f"{cls.__name__} must declare a class-level `capability` "
                    "of type AgentCapability"
                )
            if not isinstance(cls.capability, AgentCapability):
                raise TypeError(
                    f"{cls.__name__}.capability must be an AgentCapability instance"
                )

    _abstract = True

    @abc.abstractmethod
    async def execute(
        self,
        step: RemediationStep,
        event: NormalizedEvent,
        ctx: ExecutionContext,
    ) -> AgentOutcome:
        """Perform the agent's remediation step.

        Implementations MUST return an `AgentOutcome` for both the happy
        path and every recoverable failure mode. Unrecoverable failures
        (programmer errors, OOM, etc.) are caught by the executor and
        converted into a structured outcome, but the agent should still
        prefer to handle expected failures itself so it can attach
        diagnostic state in `output`."""

    async def compensate(
        self,
        handle: str,
        event: NormalizedEvent,
        ctx: ExecutionContext,
    ) -> AgentOutcome:
        """Invoke the inverse of a previously executed effectful step.

        Default implementation is a no-op success — agents that perform
        effectful work MUST override. The recovery layer replays
        compensations in LIFO order across the plan's executed steps."""
        now = datetime.now(UTC)
        return AgentOutcome(
            agent=self.capability.name,
            step_id=handle,
            success=True,
            started_at=now,
            finished_at=now,
            output={"note": "no-op compensation (non-effectful agent)"},
        )


# ---------------------------------------------------------------------------
# Plugin registration.
#
# We collect agent *classes* (not instances) so the registry can defer
# instantiation until orchestrator boot, which makes agents trivially
# unit-testable without spinning up the runtime.
# ---------------------------------------------------------------------------


_REGISTERED_AGENT_CLASSES: list[type[BaseRemediationAgent]] = []
T = TypeVar("T", bound=BaseRemediationAgent)


def register_agent(cls: type[T]) -> type[T]:
    """Class decorator that adds an agent to the bootstrap manifest."""
    if not issubclass(cls, BaseRemediationAgent):
        raise TypeError(
            f"@register_agent expected a BaseRemediationAgent subclass, got {cls!r}"
        )
    _REGISTERED_AGENT_CLASSES.append(cls)
    return cls


def iter_registered_agent_classes() -> tuple[type[BaseRemediationAgent], ...]:
    """Return all agent classes registered so far. Used by `bootstrap`."""
    return tuple(_REGISTERED_AGENT_CLASSES)


def _reset_registered_agent_classes_for_tests() -> None:
    """Test-only helper; not part of the public API."""
    _REGISTERED_AGENT_CLASSES.clear()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def make_outcome(
    *,
    agent: str,
    step_id: str,
    success: bool,
    started_at: datetime,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    compensating_handle: str | None = None,
    metrics: dict[str, float] | None = None,
) -> AgentOutcome:
    """Helper for agents to construct an outcome without restating boilerplate."""
    return AgentOutcome(
        agent=agent,
        step_id=step_id,
        success=success,
        started_at=started_at,
        finished_at=_utcnow(),
        output=output or {},
        error=error,
        compensating_handle=compensating_handle,
        metrics=metrics or {},
    )


# Convenience handle for agents that want to call `now()` consistently.
utcnow: Callable[[], datetime] = _utcnow
