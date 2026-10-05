"""FastAPI routes for e-waste demand forecasting (P10.1).

Exposes:
- ``POST /forecast/ewaste``: Train (or reuse a cached model for) and predict
  future daily recycled e-waste weight from real historical observations.

This is an internal endpoint consumed by the Node backend's
``GET /analytics/forecast`` (docs/engineering/05_API.md — Internal AI Service
API), mirroring how ``blockchain_routes.py`` is proxied by
``blockchain.service.ts`` rather than called directly by the frontend.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ..forecasting.models import DailyObservation
from ..forecasting.service import ForecastingService
from .dependencies import get_forecasting_service
from .forecast_schemas import (
    EvaluationPayload,
    ForecastPointPayload,
    ForecastRequest,
    ForecastResponse,
    HistoryPointPayload,
    ModelInfoPayload,
)

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.post("/ewaste", response_model=ForecastResponse)
def forecast_ewaste(
    request: Request,
    body: ForecastRequest,
    service: Annotated[ForecastingService, Depends(get_forecasting_service)],
) -> ForecastResponse:
    """Forecast future daily e-waste recycling weight from real history.

    Args:
        request: Active HTTP request.
        body: Historical observations plus forecast configuration.
        service: Injected :class:`ForecastingService`.

    Returns:
        A :class:`ForecastResponse`. ``status`` is always a real outcome —
        never a fabricated prediction when data or the model backend is
        unavailable (see :class:`~device_ai.forecasting.models.ForecastStatus`).
    """
    req_id = request.headers.get("X-Request-ID")

    observations = [
        DailyObservation(date=date.fromisoformat(o.date), weight_kg=o.weight_kg)
        for o in body.observations
    ]

    result = service.forecast(
        observations,
        horizon=body.horizon,
        lookback=body.lookback,
        epochs=body.epochs,
        batch_size=body.batch_size,
        force_retrain=body.force_retrain,
    )

    return ForecastResponse(
        status=result.status.value,
        points=[
            ForecastPointPayload(
                date=p.date.isoformat(), predicted_weight_kg=p.predicted_weight_kg
            )
            for p in result.points
        ],
        history=[
            HistoryPointPayload(
                date=h.date.isoformat(), actual_weight_kg=h.actual_weight_kg
            )
            for h in result.history
        ],
        evaluation=(
            EvaluationPayload(
                rmse=result.evaluation.rmse,
                mae=result.evaluation.mae,
                mape=result.evaluation.mape,
                train_samples=result.evaluation.train_samples,
                val_samples=result.evaluation.val_samples,
            )
            if result.evaluation is not None
            else None
        ),
        model=(
            ModelInfoPayload(
                name=result.model.name,
                version=result.model.version,
                trained_at=result.model.trained_at,
                framework=result.model.framework,
            )
            if result.model is not None
            else None
        ),
        history_days=result.history_days,
        min_history_days_required=result.min_history_days_required,
        lookback=result.lookback,
        horizon=result.horizon,
        reason=result.reason,
        request_id=req_id,
    )
