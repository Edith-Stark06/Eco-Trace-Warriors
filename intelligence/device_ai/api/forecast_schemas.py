"""Pydantic v2 schemas for the e-waste forecasting endpoint (P10.1).

Mirrors the flat, ``success``-flagged response convention used across the
rest of this API (see ``api/schemas.py``'s module docstring).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ObservationInput(BaseModel):
    """One real historical daily observation supplied by the caller.

    The Node backend is the source of truth for Submission data (Prisma) —
    this service receives already-aggregated real observations rather than
    querying the backend's database directly, keeping the two systems'
    schemas decoupled (docs/engineering/03_ARCHITECTURE.md).
    """

    date: str = Field(description="Calendar date (YYYY-MM-DD, UTC) of the observation.")
    weight_kg: float = Field(
        ge=0.0, description="Recycled e-waste weight recorded for this date."
    )

    @field_validator("date")
    @classmethod
    def _valid_iso_date(cls, value: str) -> str:
        date.fromisoformat(value)  # raises ValueError -> clean 422 via validation
        return value


class ForecastRequest(BaseModel):
    """Request body for ``POST /forecast/ewaste``."""

    observations: list[ObservationInput] = Field(
        default_factory=list,
        description=(
            "Real historical daily observations (any order; duplicate dates summed)."
        ),
    )
    horizon: int = Field(
        default=30, ge=1, le=90, description="Number of future days to predict."
    )
    lookback: int | None = Field(
        default=None,
        ge=3,
        le=180,
        description="LSTM lookback window (days); server default when omitted.",
    )
    epochs: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Training epochs; server default when omitted.",
    )
    batch_size: int | None = Field(
        default=None,
        ge=1,
        le=256,
        description="Mini-batch size; server default when omitted.",
    )
    force_retrain: bool = Field(
        default=False, description="Bypass the cache and retrain unconditionally."
    )


class ForecastPointPayload(BaseModel):
    """One predicted future day."""

    date: str = Field(description="Calendar date (YYYY-MM-DD) being predicted.")
    predicted_weight_kg: float = Field(
        description="Predicted recycled e-waste weight for this date."
    )


class HistoryPointPayload(BaseModel):
    """One real historical day, returned for ACTUAL-vs-FORECAST display context."""

    date: str = Field(description="Calendar date (YYYY-MM-DD) of the real observation.")
    actual_weight_kg: float = Field(
        description="Real (zero-filled) recycled e-waste weight for this date."
    )


class EvaluationPayload(BaseModel):
    """Real chronological-holdout regression metrics."""

    rmse: float = Field(description="Root-mean-squared error, in kilograms.")
    mae: float = Field(description="Mean absolute error, kilograms.")
    mape: float | None = Field(
        description="Mean absolute percentage error (0-100), or null when undefined."
    )
    train_samples: int = Field(description="Sliding-window samples used for training.")
    val_samples: int = Field(
        description="Sliding-window samples held out for validation."
    )


class ModelInfoPayload(BaseModel):
    """Provenance of the model that produced the forecast."""

    name: str = Field(description="Logical model / registry name.")
    version: str = Field(description="Artifact version (registry key).")
    trained_at: str = Field(
        description="ISO-8601 UTC timestamp the model was trained/registered."
    )
    framework: str = Field(
        default="pytorch-lstm", description="Training framework identifier."
    )


class ForecastResponse(BaseModel):
    """Response body for ``POST /forecast/ewaste``.

    ``status`` is always one of the three real outcomes — a forecast is never
    fabricated for ``INSUFFICIENT_HISTORICAL_DATA`` or
    ``MODEL_BACKEND_UNAVAILABLE``; ``points``/``evaluation``/``model`` are
    empty/null in those cases rather than populated with placeholder values.
    """

    success: bool = True
    status: Literal[
        "TRAINED", "INSUFFICIENT_HISTORICAL_DATA", "MODEL_BACKEND_UNAVAILABLE"
    ]
    points: list[ForecastPointPayload] = Field(default_factory=list)
    history: list[HistoryPointPayload] = Field(default_factory=list)
    evaluation: EvaluationPayload | None = None
    model: ModelInfoPayload | None = None
    history_days: int
    min_history_days_required: int
    lookback: int
    horizon: int
    reason: str | None = None
    request_id: str | None = None
