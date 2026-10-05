"""Minimal, dependency-free per-client rate limiting (P7.4).

A fixed-window request counter keyed by client IP — no new dependency is
introduced. See ``api/dependencies.py: get_predict_rate_limiter`` for how
this is wired to the compute-expensive ``/predict`` endpoint specifically
(YOLO inference + OCR + WBF post-processing), a backstop against a single
client exhausting CPU/GPU capacity, not a general API gateway feature.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock

from ..exceptions import RateLimitExceededError


class RateLimiter:
    """Fixed-window request counter per client key (typically the client IP)."""

    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._lock = Lock()
        # client_key -> (window_start_monotonic, count)
        self._windows: dict[str, tuple[float, int]] = {}

    def check(self, client_key: str) -> None:
        """Raise :class:`RateLimitExceededError` if `client_key` is over budget.

        Args:
            client_key: Identifies the caller (typically their IP address).

        Raises:
            RateLimitExceededError: The client has exceeded `max_requests`
                within the current window.
        """
        now = self._clock()
        with self._lock:
            window_start, count = self._windows.get(client_key, (now, 0))
            if now - window_start >= self._window_seconds:
                window_start, count = now, 0
            count += 1
            self._windows[client_key] = (window_start, count)
            if count > self._max_requests:
                raise RateLimitExceededError(
                    f"Rate limit exceeded: max {self._max_requests} requests "
                    f"per {self._window_seconds:.0f}s.",
                    details={
                        "limit": self._max_requests,
                        "window_seconds": self._window_seconds,
                    },
                )

    def reset(self) -> None:
        """Clear all recorded windows. Intended for test isolation."""
        with self._lock:
            self._windows.clear()
