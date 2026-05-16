"""
Lightweight metrics collector.

Counter / gauge / histogram primitives. The collector ships nothing on
its own — production deploys would attach an exporter (Prometheus,
OpenTelemetry). Keeping the collector dependency-free keeps the
orchestrator portable; the export surface is one function (`snapshot`).
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class HistogramSnapshot:
    count: int
    sum: float
    p50: float | None
    p95: float | None
    p99: float | None


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, frozenset], float] = defaultdict(float)
        self._gauges: dict[tuple[str, frozenset], float] = {}
        self._histograms: dict[tuple[str, frozenset], list[float]] = defaultdict(list)

    def incr(self, name: str, value: float = 1.0, **labels: str) -> None:
        with self._lock:
            self._counters[(name, frozenset(labels.items()))] += value

    def gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[(name, frozenset(labels.items()))] = value

    def observe(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._histograms[(name, frozenset(labels.items()))].append(value)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": {
                    self._format_key(name, labels): value
                    for (name, labels), value in self._counters.items()
                },
                "gauges": {
                    self._format_key(name, labels): value
                    for (name, labels), value in self._gauges.items()
                },
                "histograms": {
                    self._format_key(name, labels): self._summarize(values)
                    for (name, labels), values in self._histograms.items()
                },
            }

    @staticmethod
    def _format_key(name: str, labels: frozenset) -> str:
        if not labels:
            return name
        formatted = ",".join(f"{k}={v}" for k, v in sorted(labels))
        return f"{name}{{{formatted}}}"

    @staticmethod
    def _summarize(values: list[float]) -> HistogramSnapshot:
        if not values:
            return HistogramSnapshot(count=0, sum=0.0, p50=None, p95=None, p99=None)
        sorted_values = sorted(values)
        n = len(sorted_values)

        def pct(p: float) -> float:
            idx = max(0, min(n - 1, int(p * (n - 1))))
            return sorted_values[idx]

        return HistogramSnapshot(
            count=n,
            sum=float(sum(sorted_values)),
            p50=pct(0.5),
            p95=pct(0.95),
            p99=pct(0.99),
        )
