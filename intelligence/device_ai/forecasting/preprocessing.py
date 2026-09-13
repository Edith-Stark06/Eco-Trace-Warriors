"""Time-series preprocessing for e-waste demand forecasting (P10.1).

Pure NumPy — no torch, no sklearn. Three responsibilities:

1. :func:`build_daily_series` — collapse raw (possibly duplicate/out-of-order)
   daily observations into a dense, chronologically ordered, zero-filled
   daily series. A calendar day with no recycling activity is a real ``0.0``
   fact, not missing data, so it is filled rather than dropped — required for
   an LSTM, which needs equally-spaced time steps.
2. :class:`MinMaxScaler` — a tiny, dependency-free min-max scaler (avoids
   adding scikit-learn as a new dependency for one formula).
3. :func:`make_sliding_windows` — turn a 1-D series into supervised
   ``(X, y)`` pairs for next-step prediction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from .models import DailyObservation


def build_daily_series(
    observations: Sequence[DailyObservation],
) -> tuple[list[date], np.ndarray]:
    """Aggregate observations into a dense, zero-filled daily series.

    Multiple observations on the same calendar date are summed (this is how
    duplicate submissions recycled on the same day are handled — each
    contributes its own weight to that day's total, exactly once). The
    returned series spans every calendar day from the earliest to the latest
    observed date inclusive; days with no activity are ``0.0``.

    Args:
        observations: Real historical observations, any order, duplicates allowed.

    Returns:
        A tuple of ``(dates, values)`` where ``dates[i]`` is the calendar date
        for ``values[i]``, in ascending order. Empty when ``observations`` is
        empty.
    """
    if not observations:
        return [], np.array([], dtype=np.float64)

    totals: dict[date, float] = {}
    for obs in observations:
        totals[obs.date] = totals.get(obs.date, 0.0) + obs.weight_kg

    start = min(totals)
    end = max(totals)

    dates: list[date] = []
    values: list[float] = []
    current = start
    while current <= end:
        dates.append(current)
        values.append(totals.get(current, 0.0))
        current += timedelta(days=1)

    return dates, np.asarray(values, dtype=np.float64)


@dataclass
class MinMaxScaler:
    """Dependency-free min-max scaler to ``[0, 1]``.

    Attributes:
        min_: Fitted minimum value, or ``None`` before :meth:`fit`.
        max_: Fitted maximum value, or ``None`` before :meth:`fit`.
    """

    min_: float | None = None
    max_: float | None = None

    def fit(self, values: np.ndarray) -> MinMaxScaler:
        """Fit ``min_``/``max_`` from ``values``. Returns ``self`` for chaining."""
        self.min_ = float(np.min(values))
        self.max_ = float(np.max(values))
        return self

    def _bounds(self) -> tuple[float, float]:
        if self.min_ is None or self.max_ is None:
            raise RuntimeError("MinMaxScaler.fit() must be called before use.")
        return self.min_, self.max_

    def transform(self, values: np.ndarray) -> np.ndarray:
        """Scale ``values`` into ``[0, 1]`` using the fitted range.

        A degenerate (constant, zero-span) series scales to all zeros rather
        than dividing by zero — a flat series has no relative variation to
        express in ``[0, 1]`` regardless.
        """
        low, high = self._bounds()
        span = high - low
        if span <= 1e-9:
            return np.zeros_like(values, dtype=np.float64)
        return (values - low) / span

    def inverse_transform(self, values: np.ndarray) -> np.ndarray:
        """Map scaled values back to the original (kilogram) units."""
        low, high = self._bounds()
        span = high - low
        if span <= 1e-9:
            return np.full_like(values, low, dtype=np.float64)
        return values * span + low

    def to_dict(self) -> dict[str, Any]:
        """Serialise fitted parameters for artifact persistence."""
        return {"min": self.min_, "max": self.max_}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MinMaxScaler:
        """Reconstruct a fitted scaler from :meth:`to_dict` output."""
        return cls(min_=float(data["min"]), max_=float(data["max"]))


def make_sliding_windows(
    series: np.ndarray, lookback: int
) -> tuple[np.ndarray, np.ndarray]:
    """Build supervised next-step-prediction samples from a 1-D series.

    Args:
        series: A dense 1-D array (typically scaled).
        lookback: Number of prior time steps used to predict the next one.

    Returns:
        ``(X, y)`` where ``X`` has shape ``(n_samples, lookback)`` and ``y``
        has shape ``(n_samples,)``, ``y[i]`` being the value immediately
        after window ``X[i]``. Empty arrays when fewer than ``lookback + 1``
        points are available.
    """
    n_samples = len(series) - lookback
    if n_samples <= 0:
        return (
            np.empty((0, lookback), dtype=np.float64),
            np.empty((0,), dtype=np.float64),
        )
    x = np.stack([series[i : i + lookback] for i in range(n_samples)])
    y = series[lookback : lookback + n_samples]
    return x, y
