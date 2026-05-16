"""
Structured logger with correlation-id propagation.

All orchestrator components log through this single facade. The logger
emits one JSON object per line so downstream log shippers (CloudWatch
Insights, Loki, Splunk, OpenSearch) can filter on any field — most
importantly ``correlation_id``, which threads through ingestion ->
normalization -> routing -> execution -> recovery for a single incident.

Design choices:

* No third-party dep. The stdlib's ``logging`` is configurable enough
  for this layer; using a richer framework here would couple deployments
  to a dependency we don't otherwise need.
* Context binding returns a *new* logger object so callers can attach
  per-task fields without mutating the shared instance.
* Levels mirror stdlib semantics but are exposed as instance methods to
  keep the call site terse.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _stdlib_logger(name: str = "orchestrator") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    return log


@dataclass
class StructuredLogger:
    """Immutable structured logger. ``bind`` returns a new instance with
    extra context — the original is unchanged so concurrent tasks cannot
    pollute each other's logging fields."""

    name: str = "orchestrator"
    context: dict[str, Any] = field(default_factory=dict)
    _stdlib: logging.Logger = field(default_factory=lambda: _stdlib_logger())

    def bind(self, **fields: Any) -> "StructuredLogger":
        merged = {**self.context, **fields}
        return StructuredLogger(name=self.name, context=merged, _stdlib=self._stdlib)

    def _emit(self, level: int, event: str, fields: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": logging.getLevelName(level),
            "logger": self.name,
            "event": event,
            **self.context,
            **fields,
        }
        try:
            self._stdlib.log(level, json.dumps(record, default=str))
        except Exception:  # pragma: no cover — defensive only
            self._stdlib.log(level, str(record))

    def debug(self, event: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, event, fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, fields)

    def warn(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, fields)

    def set_level(self, level: int | str) -> None:
        if isinstance(level, str):
            level = logging._nameToLevel.get(level.upper(), logging.INFO)
        self._stdlib.setLevel(level)
