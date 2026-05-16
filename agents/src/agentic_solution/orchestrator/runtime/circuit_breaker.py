"""
Per-agent circuit breaker.

A three-state breaker (CLOSED / OPEN / HALF_OPEN) wraps every agent
dispatch. The breaker is the *only* mechanism that can mark an agent
``CIRCUIT_OPEN`` at the registry layer, which means the router cannot be
fooled into hammering a broken downstream — the routing decision and the
breaker state are read from the same snapshot.

The breaker uses a sliding-window failure ratio with a configurable
minimum sample size, so a single failure on a low-traffic agent does not
trip the circuit. When OPEN, the breaker transitions to HALF_OPEN after a
cooldown and admits a single probe; the probe outcome determines whether
we close or re-open.
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections import deque
from dataclasses import dataclass

from ..contracts import AgentStatus


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerConfig:
    window_seconds: float = 60.0
    min_samples: int = 10
    failure_ratio_threshold: float = 0.5
    cooldown_seconds: float = 30.0
    degraded_ratio_threshold: float = 0.2


class CircuitBreaker:
    """Sliding-window circuit breaker with HALF_OPEN probe semantics."""

    def __init__(self, *, name: str, config: BreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or BreakerConfig()
        self._events: deque[tuple[float, bool]] = deque()
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    def derived_status(self) -> AgentStatus:
        if self._state is CircuitState.OPEN:
            return AgentStatus.CIRCUIT_OPEN
        ratio = self._current_failure_ratio()
        if ratio >= self.config.degraded_ratio_threshold:
            return AgentStatus.DEGRADED
        return AgentStatus.HEALTHY

    async def __aenter__(self) -> "CircuitBreaker":
        await self._before_call()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Outcome recording is explicit via record_success/record_failure so
        # the executor can decide whether a timeout, a domain error, etc.
        # should count against the breaker. The context manager just guards
        # admission.
        pass

    async def _before_call(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._state is CircuitState.OPEN:
                if (
                    self._opened_at is not None
                    and (now - self._opened_at) >= self.config.cooldown_seconds
                    and not self._half_open_probe_in_flight
                ):
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_probe_in_flight = True
                    return
                raise CircuitOpenError(self.name)
            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    raise CircuitOpenError(self.name)
                self._half_open_probe_in_flight = True

    async def record_success(self) -> None:
        async with self._lock:
            self._events.append((time.monotonic(), True))
            self._trim()
            if self._state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
                self._state = CircuitState.CLOSED
                self._opened_at = None
            self._half_open_probe_in_flight = False

    async def record_failure(self) -> None:
        async with self._lock:
            self._events.append((time.monotonic(), False))
            self._trim()
            self._half_open_probe_in_flight = False
            if self._state is CircuitState.HALF_OPEN:
                # Probe failed — re-open with a fresh cooldown.
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                return
            if self._should_trip():
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def _trim(self) -> None:
        cutoff = time.monotonic() - self.config.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def _should_trip(self) -> bool:
        if len(self._events) < self.config.min_samples:
            return False
        return self._current_failure_ratio() >= self.config.failure_ratio_threshold

    def _current_failure_ratio(self) -> float:
        if not self._events:
            return 0.0
        failures = sum(1 for _, ok in self._events if not ok)
        return failures / len(self._events)


class CircuitOpenError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"circuit_open:{name}")
        self.name = name
