"""
Append-only audit journal.

The audit journal is the orchestrator's system of record. Every
transition that crosses a layer boundary writes one ``AuditRecord``.
Post-mortems, compliance attestations, and replay-based tests all read
from this journal — agents and the supervisor never read from it, so the
journal can be backed by any append-only sink (in-memory for tests,
SQLite for single-node, DynamoDB / Kinesis for distributed deploys)
without changing the runtime contract.

The default implementation keeps records in memory with bounded
retention. Replace ``AuditJournal`` with a subclass to ship to an
external sink while preserving the same async append contract.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AuditRecord:
    record_id: str
    kind: str
    timestamp: datetime
    payload: dict[str, Any]


class AuditJournal:
    """In-memory bounded journal. Subclass to ship to a durable sink."""

    def __init__(self, *, max_records: int = 10_000) -> None:
        self._records: deque[AuditRecord] = deque(maxlen=max_records)
        self._lock = asyncio.Lock()

    async def append(self, *, kind: str, payload: dict[str, Any]) -> AuditRecord:
        record = AuditRecord(
            record_id=str(uuid.uuid4()),
            kind=kind,
            timestamp=datetime.now(timezone.utc),
            payload=payload,
        )
        async with self._lock:
            self._records.append(record)
        return record

    async def snapshot(self) -> tuple[AuditRecord, ...]:
        async with self._lock:
            return tuple(self._records)

    async def by_correlation(self, correlation_id: str) -> tuple[AuditRecord, ...]:
        async with self._lock:
            return tuple(
                r
                for r in self._records
                if r.payload.get("correlation_id") == correlation_id
            )
