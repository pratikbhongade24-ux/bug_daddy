"""
Async Agent Execution Runtime.

The executor is the only component that may directly invoke an agent. It
enforces the full safety envelope:

* **Concurrency** — gated by the agent's per-registry semaphore.
* **Timeouts** — `asyncio.wait_for` bounds every call; overrun is
  recorded as a structured ``StepStatus.TIMED_OUT``.
* **Retries** — exponential backoff with jitter, bounded by manifest.
* **Breaker integration** — every attempt is registered against the
  per-agent ``CircuitBreaker`` so repeated failures trip the circuit.
* **Outcome uniformity** — any exception escaping the agent is caught
  and translated into a structured ``AgentOutcome(success=False, ...)``
  with the exception class and message preserved.
* **Compensating handles** — successful effectful steps return a
  ``compensating_handle`` that the recovery layer pairs with the
  agent's ``compensate`` method.

Crucially, the executor does *not* know about plans or DAGs. The
supervisor composes plans; the executor runs one step at a time. This
separation keeps each layer small and independently testable.
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime

from ..agents.base import ExecutionContext
from ..contracts import AgentOutcome, NormalizedEvent, RemediationStep, StepStatus
from ..observability.logging import StructuredLogger
from ..routing.registry import AgentRegistry
from .circuit_breaker import CircuitOpenError


class AgentExecutor:
    """Executes a single ``RemediationStep`` against the registered agent
    while enforcing the full reliability envelope."""

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        logger: StructuredLogger,
    ) -> None:
        self._registry = registry
        self._logger = logger

    async def execute_step(
        self,
        step: RemediationStep,
        event: NormalizedEvent,
        *,
        plan_id: str,
    ) -> AgentOutcome:
        entry = self._registry.get(step.agent)
        if entry is None:
            return self._unknown_agent_outcome(step)

        timeout = step.timeout_seconds or entry.capability.timeout_seconds
        max_retries = step.max_retries if step.max_retries is not None else entry.capability.max_retries

        last_error: str | None = None
        started_overall = datetime.now(UTC)

        for attempt in range(max_retries + 1):
            step.attempts = attempt + 1
            step.status = StepStatus.RUNNING
            step.started_at = step.started_at or started_overall

            try:
                async with entry.breaker:
                    async with entry.semaphore:
                        outcome = await self._run_once(
                            entry_agent=entry.agent,
                            step=step,
                            event=event,
                            plan_id=plan_id,
                            timeout=timeout,
                        )
                if outcome.success:
                    await entry.breaker.record_success()
                    step.status = StepStatus.SUCCEEDED
                    step.finished_at = outcome.finished_at
                    step.output = outcome.output
                    self._logger.info(
                        "executor.step.success",
                        agent=step.agent,
                        step_id=step.step_id,
                        correlation_id=event.correlation_id,
                        attempts=step.attempts,
                    )
                    return outcome
                # Agent reported a structured failure. Count it against the
                # breaker but distinguish from infra failures in the log.
                await entry.breaker.record_failure()
                last_error = outcome.error or "agent reported success=False"
                self._logger.warn(
                    "executor.step.failure",
                    agent=step.agent,
                    step_id=step.step_id,
                    correlation_id=event.correlation_id,
                    attempts=step.attempts,
                    error=last_error,
                )

            except CircuitOpenError as exc:
                last_error = str(exc)
                self._logger.warn(
                    "executor.step.circuit_open",
                    agent=step.agent,
                    step_id=step.step_id,
                    correlation_id=event.correlation_id,
                )
                # Breaker is open — no point retrying this agent. Caller
                # (supervisor) will rotate to a fallback.
                break
            except TimeoutError:
                await entry.breaker.record_failure()
                last_error = f"timeout after {timeout}s"
                step.status = StepStatus.TIMED_OUT
                self._logger.warn(
                    "executor.step.timeout",
                    agent=step.agent,
                    step_id=step.step_id,
                    correlation_id=event.correlation_id,
                    attempts=step.attempts,
                )
            except Exception as exc:  # noqa: BLE001 — uniformity is the point
                await entry.breaker.record_failure()
                last_error = f"{type(exc).__name__}: {exc}"
                self._logger.error(
                    "executor.step.exception",
                    agent=step.agent,
                    step_id=step.step_id,
                    correlation_id=event.correlation_id,
                    attempts=step.attempts,
                    error=last_error,
                )

            if attempt < max_retries:
                await asyncio.sleep(self._backoff_delay(attempt))

        step.status = StepStatus.FAILED if step.status is not StepStatus.TIMED_OUT else StepStatus.TIMED_OUT
        step.finished_at = datetime.now(UTC)
        step.error = last_error
        return AgentOutcome(
            agent=step.agent,
            step_id=step.step_id,
            success=False,
            started_at=started_overall,
            finished_at=step.finished_at,
            output={"attempts": step.attempts},
            error=last_error,
        )

    async def _run_once(
        self,
        *,
        entry_agent,
        step: RemediationStep,
        event: NormalizedEvent,
        plan_id: str,
        timeout: float,
    ) -> AgentOutcome:
        deadline_at = datetime.fromtimestamp(time.time() + timeout, tz=UTC)
        ctx = ExecutionContext(
            correlation_id=event.correlation_id,
            plan_id=plan_id,
            deadline_at=deadline_at,
            logger=self._logger.bind(
                agent=step.agent,
                step_id=step.step_id,
                correlation_id=event.correlation_id,
            ),
        )
        return await asyncio.wait_for(
            entry_agent.execute(step, event, ctx),
            timeout=timeout,
        )

    def _unknown_agent_outcome(self, step: RemediationStep) -> AgentOutcome:
        now = datetime.now(UTC)
        step.status = StepStatus.FAILED
        step.finished_at = now
        step.error = f"agent_not_registered:{step.agent}"
        return AgentOutcome(
            agent=step.agent,
            step_id=step.step_id,
            success=False,
            started_at=now,
            finished_at=now,
            output={},
            error=f"agent_not_registered:{step.agent}",
        )

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Exponential backoff with full jitter. Cap at 8 seconds — beyond
        that we'd rather rotate to a fallback agent than keep waiting."""
        base = min(8.0, 0.25 * (2 ** attempt))
        return random.uniform(0.0, base)
