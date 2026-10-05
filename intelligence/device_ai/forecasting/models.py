"""Domain value objects for e-waste demand forecasting (P10.1).

Pure data — no torch, no I/O, no FastAPI. Kept import-light so
:mod:`api.forecast_schemas` and the service layer can share one vocabulary
without pulling in the (optional) torch dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any


@dataclass(frozen=True, slots=True)
class DailyObservation:
    """One real, caller-supplied historical data point.

    Attributes:
        date: Calendar date (UTC) the observation belongs to.
        weight_kg: Total recycled e-waste weight recorded for that date.
            Callers may supply more than one observation for the same date
            (e.g. one per submission); the preprocessing layer sums them.
    """

    date: date
    weight_kg: float


class ForecastStatus(str, Enum):
    """Outcome of a forecast request — never fabricated, always truthful."""

    #: A model was trained (or a cached one reused) and produced real predictions.
    TRAINED = "TRAINED"
    #: Too little real history exists to train a meaningful model.
    INSUFFICIENT_HISTORICAL_DATA = "INSUFFICIENT_HISTORICAL_DATA"
    #: The optional torch backend is not installed on this deployment.
    MODEL_BACKEND_UNAVAILABLE = "MODEL_BACKEND_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """Real chronological-holdout regression metrics — never fabricated.

    Attributes:
        rmse: Root-mean-squared error, in kilograms.
        mae: Mean absolute error, in kilograms.
        mape: Mean absolute percentage error (0-100), or ``None`` when every
            validation-window actual value is zero (MAPE is undefined then —
            reported honestly as ``None`` rather than a divide-by-zero value).
        train_samples: Number of sliding-window training samples used.
        val_samples: Number of sliding-window validation samples used.
    """

    rmse: float
    mae: float
    mape: float | None
    train_samples: int
    val_samples: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serialisable mapping."""
        return {
            "rmse": self.rmse,
            "mae": self.mae,
            "mape": self.mape,
            "train_samples": self.train_samples,
            "val_samples": self.val_samples,
        }


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """One predicted future day."""

    date: date
    predicted_weight_kg: float


@dataclass(frozen=True, slots=True)
class HistoryPoint:
    """One real (zero-filled) historical day, returned for display context."""

    date: date
    actual_weight_kg: float


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Provenance of the model that produced a forecast."""

    name: str
    version: str
    trained_at: str
    framework: str = "pytorch-lstm"


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """The complete, honest outcome of a forecast request.

    Attributes:
        status: See :class:`ForecastStatus`.
        points: Predicted future days (empty unless ``status`` is ``TRAINED``).
        history: Real recent daily observations, for ACTUAL-vs-FORECAST display.
        evaluation: Real chronological holdout metrics (``None`` unless trained).
        model: Provenance of the model used (``None`` unless trained).
        history_days: Number of zero-filled calendar days actually observed.
        min_history_days_required: The threshold that was applied.
        lookback: LSTM lookback window (days) used or required.
        horizon: Requested forecast horizon (days).
        reason: Human-readable explanation when ``status`` is not ``TRAINED``.
    """

    status: ForecastStatus
    points: tuple[ForecastPoint, ...] = ()
    history: tuple[HistoryPoint, ...] = ()
    evaluation: EvaluationMetrics | None = None
    model: ModelInfo | None = None
    history_days: int = 0
    min_history_days_required: int = 0
    lookback: int = 0
    horizon: int = 0
    reason: str | None = None
