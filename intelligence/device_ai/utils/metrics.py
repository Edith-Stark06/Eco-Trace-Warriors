"""Minimal, dependency-free in-process metrics registry (P7.3).

Mirrors ``backend/src/shared/metrics/metrics.ts``: no Prometheus client is
introduced here either, for the same reason — no scrape target exists
anywhere in this repository or environment, so a text-exposition format
nothing consumes would be an unused dependency. ``GET /metrics`` exposes the
same underlying counts as a small JSON summary instead.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _RouteStats:
    count: int = 0
    total_duration_ms: float = 0.0
    status_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class _FabricStats:
    transactions: int = 0
    succeeded: int = 0
    failed: int = 0


class MetricsRegistry:
    """Process-local metrics registry. Not persisted, not shared across processes."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started_at = clock()
        self._lock = Lock()
        self._routes: dict[tuple[str, str], _RouteStats] = {}
        self._fabric = _FabricStats()

    def record_request(
        self, method: str, path: str, status_code: int, duration_ms: float
    ) -> None:
        """Record one completed HTTP request against its matched route."""
        key = (method, path)
        with self._lock:
            stats = self._routes.setdefault(key, _RouteStats())
            stats.count += 1
            stats.total_duration_ms += duration_ms
            status_key = str(status_code)
            stats.status_counts[status_key] = stats.status_counts.get(status_key, 0) + 1

    def record_fabric_transaction(self, *, succeeded: bool) -> None:
        """Record one completed Fabric Gateway transaction attempt."""
        with self._lock:
            self._fabric.transactions += 1
            if succeeded:
                self._fabric.succeeded += 1
            else:
                self._fabric.failed += 1

    def snapshot(self) -> dict:
        """Return a point-in-time JSON-serializable copy of all recorded metrics."""
        with self._lock:
            by_route = [
                {
                    "method": method,
                    "route": path,
                    "count": stats.count,
                    "avg_duration_ms": (
                        stats.total_duration_ms / stats.count
                        if stats.count > 0
                        else 0.0
                    ),
                    "status_counts": dict(stats.status_counts),
                }
                for (method, path), stats in self._routes.items()
            ]
            total = sum(stats.count for stats in self._routes.values())
            fabric = {
                "transactions": self._fabric.transactions,
                "succeeded": self._fabric.succeeded,
                "failed": self._fabric.failed,
            }

        return {
            "uptime_seconds": self._clock() - self._started_at,
            "requests": {"total": total, "by_route": by_route},
            "fabric": fabric,
        }

    def reset(self) -> None:
        """Clear all recorded data. Intended for test isolation."""
        with self._lock:
            self._routes.clear()
            self._fabric = _FabricStats()


_registry = MetricsRegistry()


def get_metrics_registry() -> MetricsRegistry:
    """Return the process-wide metrics registry singleton."""
    return _registry
