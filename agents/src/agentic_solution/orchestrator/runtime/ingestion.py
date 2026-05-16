"""
Trigger Ingestion Layer.

Decoupled ingestion guarantees telemetry durability even during downstream
execution degradation. The ingestion gate is the *only* component allowed
to accept raw upstream data, and it commits every accepted trigger to the
durable journal *before* releasing it to normalization.

Two responsibilities
--------------------
1. **Admission control** — reject malformed payloads loudly, deduplicate
   by ``correlation_hint`` within the configured window, and back-pressure
   when the downstream queue saturates.
2. **Durable journaling** — every accepted ``RawTrigger`` is appended to
   the audit journal so post-mortems can replay history.

The dedup window is intentionally short (default 30s). The deduplicator
here folds *signal storms* — a CloudWatch alarm firing 14 times in 5
seconds — not duplicate incidents. The latter is handled by the
normalization-layer fingerprint.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from ..contracts import RawTrigger
from ..observability.audit import AuditJournal
from ..observability.logging import StructuredLogger


@dataclass
class IngestionStats:
    accepted: int = 0
    rejected: int = 0
    deduplicated: int = 0
    backpressured: int = 0


class IngestionGate:
    """Async, bounded, deduplicating ingestion gate."""

    def __init__(
        self,
        *,
        journal: AuditJournal,
        logger: StructuredLogger,
        max_queue: int = 1024,
        dedup_window_seconds: float = 30.0,
    ) -> None:
        self._journal = journal
        self._logger = logger
        self._queue: asyncio.Queue[RawTrigger] = asyncio.Queue(maxsize=max_queue)
        self._dedup_window = dedup_window_seconds
        # correlation_hint -> last-seen monotonic timestamp
        self._dedup: dict[str, float] = {}
        self._stats = IngestionStats()
        self._lock = asyncio.Lock()

    @property
    def stats(self) -> IngestionStats:
        return self._stats

    @property
    def queue(self) -> asyncio.Queue[RawTrigger]:
        return self._queue

    async def submit(self, trigger: RawTrigger, *, block: bool = True) -> bool:
        """Submit a raw trigger. Returns True if accepted, False if dropped.

        ``block=False`` makes the gate non-blocking — useful for synchronous
        webhook handlers that prefer to shed load rather than stall."""
        async with self._lock:
            self._sweep_dedup()
            if trigger.correlation_hint:
                last = self._dedup.get(trigger.correlation_hint)
                now = time.monotonic()
                if last is not None and (now - last) < self._dedup_window:
                    self._stats.deduplicated += 1
                    self._logger.debug(
                        "ingestion.dedup",
                        source=trigger.source.value,
                        correlation_hint=trigger.correlation_hint,
                    )
                    return False
                self._dedup[trigger.correlation_hint] = now

        await self._journal.append(
            kind="trigger.received",
            payload={
                "source": trigger.source.value,
                "received_at": trigger.received_at.isoformat(),
                "correlation_hint": trigger.correlation_hint,
                "payload": trigger.payload,
            },
        )

        try:
            if block:
                await self._queue.put(trigger)
            else:
                self._queue.put_nowait(trigger)
        except asyncio.QueueFull:
            self._stats.backpressured += 1
            self._logger.warn(
                "ingestion.backpressure",
                source=trigger.source.value,
                queue_size=self._queue.qsize(),
            )
            return False

        self._stats.accepted += 1
        self._logger.info(
            "ingestion.accepted",
            source=trigger.source.value,
            correlation_hint=trigger.correlation_hint,
            queue_depth=self._queue.qsize(),
        )
        return True

    def _sweep_dedup(self) -> None:
        """Drop expired dedup entries. O(n) but n is bounded by the rate of
        unique correlation hints within the window, which is small in
        practice."""
        cutoff = time.monotonic() - self._dedup_window
        expired = [k for k, t in self._dedup.items() if t < cutoff]
        for k in expired:
            del self._dedup[k]
