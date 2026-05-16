"""
Priority & Severity Scheduler.

Weighted-fair priority queue keyed on ``SeverityTier``. The scheduler
prevents two classes of operational pathology:

1. **Inversion** — a SEV3 capacity warning blocking a SEV0 outage because
   it happened to arrive first. The priority key alone fixes this.

2. **Starvation** — a sustained SEV0 storm blocking SEV3/SEV4 work
   indefinitely. We bound this with weighted-fair admission: each tier
   has a *minimum service share* per scheduling cycle, so even under
   sustained high-severity load some lower-severity capacity continues
   to drain. This is what we mean by "priority-aware scheduling reduces
   cascading infrastructure instability under multi-vector failure."

Implementation detail: we use a min-heap keyed on
``(-severity_weight, fifo_seq)`` so equal-severity items drain in arrival
order. The fairness layer sits in front of that heap and periodically
forces a low-severity drain.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from dataclasses import dataclass, field

from ..contracts import NormalizedEvent, SeverityTier


@dataclass(order=True)
class ScheduledItem:
    """Heap entry. ``priority`` is a 2-tuple so equal-weight items sort by
    arrival order. ``event`` carries the payload."""

    priority: tuple[int, int]
    event: NormalizedEvent = field(compare=False)


class PriorityScheduler:
    """Async weighted-fair priority scheduler."""

    # Minimum share guaranteed to each tier per fairness cycle. Tuned so
    # that SEV4 hygiene work is never starved indefinitely even when SEV0
    # incidents are continuously arriving.
    _FAIRNESS_QUOTA: dict[SeverityTier, int] = {
        SeverityTier.SEV0: 100,
        SeverityTier.SEV1: 50,
        SeverityTier.SEV2: 20,
        SeverityTier.SEV3: 5,
        SeverityTier.SEV4: 1,
    }
    _CYCLE_LENGTH = 176  # sum of quotas — picks one item per slot.

    def __init__(self) -> None:
        self._heap: list[ScheduledItem] = []
        self._fifo = itertools.count()
        self._cv = asyncio.Condition()
        self._cycle_position = 0
        self._slot_table = self._build_slot_table()

    @classmethod
    def _build_slot_table(cls) -> list[SeverityTier]:
        """Pre-compute a length-CYCLE_LENGTH list of severity tiers, where
        each tier appears ``quota`` times, interleaved so equal-rate slots
        are spread evenly rather than bunched."""
        slots: list[SeverityTier] = []
        remaining = dict(cls._FAIRNESS_QUOTA)
        while sum(remaining.values()) > 0:
            for tier in (
                SeverityTier.SEV0,
                SeverityTier.SEV1,
                SeverityTier.SEV2,
                SeverityTier.SEV3,
                SeverityTier.SEV4,
            ):
                if remaining[tier] > 0:
                    slots.append(tier)
                    remaining[tier] -= 1
        return slots

    async def submit(self, event: NormalizedEvent) -> None:
        async with self._cv:
            item = ScheduledItem(
                priority=(-event.severity.weight, next(self._fifo)),
                event=event,
            )
            heapq.heappush(self._heap, item)
            self._cv.notify()

    async def next(self) -> NormalizedEvent:
        """Block until an event is available, honoring fairness slots."""
        async with self._cv:
            while not self._heap:
                await self._cv.wait()
            target_tier = self._slot_table[self._cycle_position % self._CYCLE_LENGTH]
            self._cycle_position += 1

            # Try to pull the target tier first; fall back to highest-priority.
            target_item = self._pop_tier(target_tier)
            if target_item is not None:
                return target_item.event
            return heapq.heappop(self._heap).event

    def _pop_tier(self, tier: SeverityTier) -> ScheduledItem | None:
        """Linear scan for an item of *exactly* the desired tier. The heap
        is small in practice (bounded by inflight incidents); we accept the
        O(n) scan in exchange for fairness correctness."""
        for idx, item in enumerate(self._heap):
            if item.event.severity is tier:
                # Remove without breaking heap invariant by swapping in last
                # and sifting.
                last = self._heap.pop()
                if idx < len(self._heap):
                    self._heap[idx] = last
                    heapq._siftup(self._heap, idx)  # type: ignore[attr-defined]
                    heapq._siftdown(self._heap, 0, idx)  # type: ignore[attr-defined]
                return item
        return None

    def depth(self) -> int:
        return len(self._heap)
