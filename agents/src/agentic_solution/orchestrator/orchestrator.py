"""
Top-level orchestrator facade.

This file wires the ten architectural layers into one cohesive runtime:

    Trigger -> Ingestion -> Normalization -> Scheduler -> Supervisor
            -> Router -> Executor -> Recovery -> Audit

A single ``RemediationOrchestrator`` instance owns the queues, the
registry, and the workers. It exposes a small public surface:

* ``submit(raw_trigger)``   — accept work
* ``start()`` / ``stop()``  — lifecycle
* ``run_until_idle()``      — useful for batch tests and the demo runner
* ``audit_records()``       — read the journal

The orchestrator is fully async and runs N concurrent supervisor workers
that pull from the priority scheduler. Each worker is a fault-isolated
goroutine-shaped task: a worker crash does not corrupt the queue, and
the supervisor's outcome is durable in the audit journal before the
worker returns to the pool.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .agents.bootstrap import bootstrap_default_agents
from .contracts import RawTrigger
from .observability.audit import AuditJournal
from .observability.logging import StructuredLogger
from .observability.metrics import MetricsCollector
from .routing.registry import AgentRegistry
from .routing.router import RoutingEngine
from .runtime.circuit_breaker import BreakerConfig
from .runtime.executor import AgentExecutor
from .runtime.ingestion import IngestionGate
from .runtime.normalization import EventNormalizer
from .runtime.recovery import RecoveryCoordinator
from .runtime.scheduler import PriorityScheduler
from .runtime.supervisor import IncidentTrace, RemediationSupervisor


@dataclass
class OrchestratorConfig:
    worker_count: int = 4
    ingestion_queue_size: int = 1024
    dedup_window_seconds: float = 30.0
    breaker: BreakerConfig | None = None


class RemediationOrchestrator:
    def __init__(
        self,
        *,
        config: OrchestratorConfig | None = None,
        registry: AgentRegistry | None = None,
        logger: StructuredLogger | None = None,
        journal: AuditJournal | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self.config = config or OrchestratorConfig()
        self.logger = logger or StructuredLogger()
        self.journal = journal or AuditJournal()
        self.metrics = metrics or MetricsCollector()
        self.registry = registry or AgentRegistry()
        self.normalizer = EventNormalizer()
        self.scheduler = PriorityScheduler()
        self.ingestion = IngestionGate(
            journal=self.journal,
            logger=self.logger,
            max_queue=self.config.ingestion_queue_size,
            dedup_window_seconds=self.config.dedup_window_seconds,
        )
        self.executor = AgentExecutor(registry=self.registry, logger=self.logger)
        self.router = RoutingEngine()
        self.recovery = RecoveryCoordinator(registry=self.registry, logger=self.logger)
        self.supervisor = RemediationSupervisor(
            registry=self.registry,
            executor=self.executor,
            router=self.router,
            recovery=self.recovery,
            journal=self.journal,
            logger=self.logger,
        )
        self._workers: list[asyncio.Task] = []
        self._normalizer_task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._idle = asyncio.Event()
        self._inflight = 0
        self._inflight_lock = asyncio.Lock()
        self._traces: list[IncidentTrace] = []
        self._traces_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public surface.
    # ------------------------------------------------------------------

    async def submit(self, raw: RawTrigger) -> bool:
        return await self.ingestion.submit(raw)

    async def start(self) -> None:
        if self._workers:
            return
        self.logger.info(
            "orchestrator.start",
            worker_count=self.config.worker_count,
            registered_agents=list(self.registry.names()),
        )
        self._normalizer_task = asyncio.create_task(self._normalize_loop())
        for i in range(self.config.worker_count):
            self._workers.append(asyncio.create_task(self._worker_loop(i)))
        self._idle.set()

    async def stop(self) -> None:
        self._stop.set()
        for w in self._workers:
            w.cancel()
        if self._normalizer_task is not None:
            self._normalizer_task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        if self._normalizer_task is not None:
            await asyncio.gather(self._normalizer_task, return_exceptions=True)
        self._workers.clear()
        self._normalizer_task = None
        self.logger.info("orchestrator.stop")

    async def run_until_idle(self, timeout: float = 10.0) -> None:
        """Block until the ingestion queue and scheduler drain and all
        workers report idle. Primarily for tests / demo runs."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError("orchestrator did not drain in time")
            await asyncio.sleep(0.05)
            async with self._inflight_lock:
                inflight = self._inflight
            if (
                self.ingestion.queue.empty()
                and self.scheduler.depth() == 0
                and inflight == 0
            ):
                return

    async def traces(self) -> tuple[IncidentTrace, ...]:
        async with self._traces_lock:
            return tuple(self._traces)

    async def audit_records(self):
        return await self.journal.snapshot()

    # ------------------------------------------------------------------
    # Internal loops.
    # ------------------------------------------------------------------

    async def _normalize_loop(self) -> None:
        """Single-consumer loop that turns raw triggers into normalized
        events and pushes them onto the priority scheduler. Kept single-
        consumer on purpose so the audit ordering matches the wall-clock
        order of acceptance, which simplifies post-mortem replay."""
        while not self._stop.is_set():
            try:
                trigger = await self.ingestion.queue.get()
            except asyncio.CancelledError:
                return
            try:
                event = self.normalizer.normalize(trigger)
                self.metrics.incr(
                    "events.normalized",
                    1.0,
                    incident_class=event.incident_class.value,
                    severity=event.severity.value,
                )
                await self.scheduler.submit(event)
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                self.logger.error(
                    "orchestrator.normalize.error",
                    error=f"{type(exc).__name__}: {exc}",
                )

    async def _worker_loop(self, worker_id: int) -> None:
        while not self._stop.is_set():
            try:
                event = await self.scheduler.next()
            except asyncio.CancelledError:
                return
            async with self._inflight_lock:
                self._inflight += 1
            try:
                self.logger.info(
                    "orchestrator.worker.pick",
                    worker_id=worker_id,
                    correlation_id=event.correlation_id,
                    severity=event.severity.value,
                )
                trace = await self.supervisor.handle(event)
                async with self._traces_lock:
                    self._traces.append(trace)
                self.metrics.incr(
                    "incidents.terminal",
                    1.0,
                    status=trace.terminal_status,
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.error(
                    "orchestrator.worker.error",
                    worker_id=worker_id,
                    error=f"{type(exc).__name__}: {exc}",
                )
            finally:
                async with self._inflight_lock:
                    self._inflight -= 1


def build_default_orchestrator(
    *,
    config: OrchestratorConfig | None = None,
    breaker_config: BreakerConfig | None = None,
) -> RemediationOrchestrator:
    """Construct an orchestrator with every default agent registered.

    This is the entrypoint demo/test code should prefer. Production
    callers may want a thinner construction path so they can register
    bespoke agents — see ``RemediationOrchestrator`` directly."""
    orch = RemediationOrchestrator(config=config)
    bootstrap_default_agents(orch.registry, breaker_config=breaker_config)
    return orch
