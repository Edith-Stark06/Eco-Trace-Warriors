"""Forecasting orchestration service (P10.1).

Wires together preprocessing, the LSTM trainer, and the existing training
artifact infrastructure
(:class:`~device_ai.training.registry.artifact_manager.ArtifactManager`,
:class:`~device_ai.training.registry.model_registry.ModelRegistry` — reused
as-is, not duplicated) into one entry point: :meth:`ForecastingService.forecast`.

Training strategy ("clean separation: training -> saved artifact -> inference
-> API", never retraining on every request): a model is retrained only when
no cached artifact exists yet, the caller explicitly asks for a retrain, or
the underlying daily series has actually changed (detected via a content
hash of the dates+values, stored as a registry tag). Since the target
granularity is *daily*, the series can change at most once per day in
practice — so this content-hash cache naturally caps retraining frequency to
"at most once per new day's data", without needing a separate scheduler.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
from loguru import logger

from ..configs.settings import Settings
from ..training.registry.artifact_manager import ArtifactManager
from ..training.registry.model_registry import ModelRecord, ModelRegistry
from ..training.utils.git_utils import git_commit_hash
from ..utils.hashing import hash_bytes
from .model import torch_available
from .models import (
    DailyObservation,
    EvaluationMetrics,
    ForecastPoint,
    ForecastResult,
    ForecastStatus,
    HistoryPoint,
    ModelInfo,
)
from .preprocessing import MinMaxScaler, build_daily_series
from .trainer import (
    MIN_TRAIN_SAMPLES,
    MIN_VAL_SAMPLES,
    TrainedForecastArtifact,
    predict_horizon,
    train_lstm_forecaster,
)

#: Logical model name — the registry key under which every trained version
#: of the forecasting LSTM is recorded.
FORECAST_MODEL_NAME = "ewaste-forecast-lstm"


def _series_hash(dates: Sequence[date], values: np.ndarray) -> str:
    """Deterministic content hash of a daily series, used for retrain caching."""
    payload = json.dumps(
        {
            "dates": [d.isoformat() for d in dates],
            "values": [round(v, 6) for v in values.tolist()],
        },
        sort_keys=True,
    ).encode("utf-8")
    return hash_bytes(payload)


@dataclass(frozen=True, slots=True)
class _CachedArtifact:
    state_dict: dict[str, object]
    scaler: MinMaxScaler
    hidden_size: int
    lookback: int
    last_window: np.ndarray
    evaluation: EvaluationMetrics
    record: ModelRecord


class ForecastingService:
    """Produces real, honest e-waste weight forecasts from real history.

    Never fabricates a prediction: when history is insufficient or the torch
    backend is unavailable, :meth:`forecast` returns a :class:`ForecastResult`
    describing exactly why, with empty ``points``.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        artifacts: ArtifactManager | None = None,
        registry: ModelRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._artifacts = (
            artifacts or ArtifactManager.from_settings(settings)
        ).ensure()
        self._registry = registry or ModelRegistry.from_settings(settings)

    def forecast(
        self,
        observations: Sequence[DailyObservation],
        *,
        horizon: int,
        lookback: int | None = None,
        epochs: int | None = None,
        batch_size: int | None = None,
        force_retrain: bool = False,
    ) -> ForecastResult:
        """Produce a forecast, training or reusing a cached model as needed.

        Args:
            observations: Real historical daily observations (see
                :func:`~.preprocessing.build_daily_series` for how duplicates
                on the same date are handled).
            horizon: Number of future days to predict.
            lookback: LSTM lookback window; defaults to
                ``settings.forecast_default_lookback``.
            epochs: Training epochs; defaults to
                ``settings.forecast_default_epochs``.
            batch_size: Mini-batch size; defaults to
                ``settings.forecast_default_batch_size``.
            force_retrain: Bypass the content-hash cache and retrain
                unconditionally.

        Returns:
            A :class:`ForecastResult` — always a valid, truthful outcome,
            never a fabricated one.
        """
        lookback = lookback or self._settings.forecast_default_lookback
        epochs = epochs or self._settings.forecast_default_epochs
        batch_size = batch_size or self._settings.forecast_default_batch_size

        dates, series = build_daily_series(observations)
        history_days = len(series)
        active_days = len({obs.date for obs in observations})
        min_required = max(
            self._settings.forecast_min_history_days,
            lookback + MIN_TRAIN_SAMPLES + MIN_VAL_SAMPLES,
        )
        # The zero-filled calendar span alone is not sufficient: a wide date
        # range with almost entirely padded zero-days (e.g. two real
        # recycling events three months apart) satisfies `history_days` while
        # containing almost no real signal — exactly the "insufficient data
        # dressed up as sufficient" case a naive span-only check would miss.
        # Require a minimum count of days that actually had real recorded
        # activity too, independent of how they're distributed in time.
        min_active_days_required = MIN_TRAIN_SAMPLES + MIN_VAL_SAMPLES

        # Data-sufficiency is checked before backend availability: whether
        # there is *enough real history* is a fact about EcoTrace's data,
        # independent of which compute backend happens to be installed, and
        # is almost always the more actionable/informative answer for a
        # freshly-deployed instance (very little data yet) regardless of
        # infra state.
        if history_days < min_required:
            return ForecastResult(
                status=ForecastStatus.INSUFFICIENT_HISTORICAL_DATA,
                history=_history_points(dates, series, cap=min(history_days, 90)),
                history_days=history_days,
                min_history_days_required=min_required,
                lookback=lookback,
                horizon=horizon,
                reason=(
                    f"Only {history_days} day(s) of historical recycling-weight "
                    f"data are available; at least {min_required} are required "
                    f"(lookback={lookback} days plus a minimum of "
                    f"{MIN_TRAIN_SAMPLES} training and {MIN_VAL_SAMPLES} "
                    "validation windows) before a forecast can be trained "
                    "reliably. No values were fabricated."
                ),
            )

        if active_days < min_active_days_required:
            return ForecastResult(
                status=ForecastStatus.INSUFFICIENT_HISTORICAL_DATA,
                history=_history_points(dates, series, cap=min(history_days, 90)),
                history_days=history_days,
                min_history_days_required=min_required,
                lookback=lookback,
                horizon=horizon,
                reason=(
                    f"The observed date range spans {history_days} days, but "
                    f"only {active_days} of them have any recorded recycling "
                    f"activity; at least {min_active_days_required} active "
                    "days are required so the model trains on real signal "
                    "rather than mostly zero-padding. No values were "
                    "fabricated."
                ),
            )

        if not torch_available():
            logger.warning("Forecast requested but torch is not installed.")
            return ForecastResult(
                status=ForecastStatus.MODEL_BACKEND_UNAVAILABLE,
                history=_history_points(dates, series, cap=min(history_days, 90)),
                history_days=history_days,
                min_history_days_required=min_required,
                lookback=lookback,
                horizon=horizon,
                reason=(
                    "The forecasting engine's PyTorch backend is not "
                    "installed on this deployment. No forecast was computed "
                    "or fabricated."
                ),
            )

        series_hash = _series_hash(dates, series)
        cached = None if force_retrain else self._load_cached(series_hash, lookback)

        if cached is not None:
            logger.info(
                "Reusing cached forecasting model version={} (series unchanged).",
                cached.record.version,
            )
            state_dict = cached.state_dict
            scaler = cached.scaler
            hidden_size = cached.hidden_size
            evaluation = cached.evaluation
            record = cached.record
        else:
            artifact = train_lstm_forecaster(
                series,
                lookback=lookback,
                epochs=epochs,
                batch_size=batch_size,
                hidden_size=self._settings.forecast_lstm_units,
                seed=self._settings.training_seed,
            )
            record = self._persist(
                artifact,
                series_hash=series_hash,
                history_days=history_days,
                dataset_start=dates[0],
                dataset_end=dates[-1],
            )
            state_dict = artifact.state_dict
            scaler = artifact.scaler
            hidden_size = artifact.hidden_size
            evaluation = artifact.evaluation

        last_window = series[-lookback:]
        predicted = predict_horizon(
            state_dict=state_dict,
            hidden_size=hidden_size,
            scaler=scaler,
            last_window=last_window,
            horizon=horizon,
        )

        last_date = dates[-1]
        points = tuple(
            ForecastPoint(
                date=last_date + timedelta(days=i + 1),
                predicted_weight_kg=float(predicted[i]),
            )
            for i in range(horizon)
        )

        return ForecastResult(
            status=ForecastStatus.TRAINED,
            points=points,
            history=_history_points(dates, series, cap=lookback),
            evaluation=evaluation,
            model=ModelInfo(
                name=FORECAST_MODEL_NAME,
                version=record.version,
                trained_at=record.created_at,
            ),
            history_days=history_days,
            min_history_days_required=min_required,
            lookback=lookback,
            horizon=horizon,
            reason=None,
        )

    # -- Artifact cache / persistence ---------------------------------------

    def _load_cached(self, series_hash: str, lookback: int) -> _CachedArtifact | None:
        """Return the cached artifact when the series/lookback are unchanged."""
        record = self._registry.latest(FORECAST_MODEL_NAME)
        if record is None:
            return None
        if record.tags.get("series_hash") != series_hash:
            return None
        if record.tags.get("lookback") != str(lookback):
            return None

        checkpoint_path = Path(record.artifact_location)
        companion_path = self._artifacts.export_path(
            FORECAST_MODEL_NAME, record.version, ".json"
        )
        if not checkpoint_path.is_file() or not companion_path.is_file():
            logger.warning(
                "Forecast model registry record '{}' points at a missing "
                "artifact; retraining.",
                record.key,
            )
            return None

        import torch  # guarded above by torch_available() at the call site

        try:
            state_dict = torch.load(checkpoint_path, weights_only=True)
            companion = json.loads(companion_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - any corrupt artifact just retrains
            logger.warning(
                "Failed to load cached forecast artifact '{}'; retraining.",
                record.key,
            )
            return None

        return _CachedArtifact(
            state_dict=state_dict,
            scaler=MinMaxScaler.from_dict(companion["scaler"]),
            hidden_size=int(companion["hidden_size"]),
            lookback=int(companion["lookback"]),
            last_window=np.asarray(companion["last_window"], dtype=np.float64),
            evaluation=EvaluationMetrics(**record.metrics),  # type: ignore[arg-type]
            record=record,
        )

    def _persist(
        self,
        artifact: TrainedForecastArtifact,
        *,
        series_hash: str,
        history_days: int,
        dataset_start: date,
        dataset_end: date,
    ) -> ModelRecord:
        """Save weights + scaler/window metadata + eval report; register provenance."""
        import torch

        # Microsecond precision avoids version collisions between successive
        # trainings within the same wall-clock second (e.g. back-to-back
        # force_retrain calls, or automated retrains firing close together).
        version = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        checkpoint_path = self._artifacts.checkpoint_path(FORECAST_MODEL_NAME, version)
        torch.save(artifact.state_dict, checkpoint_path)

        companion_path = self._artifacts.export_path(
            FORECAST_MODEL_NAME, version, ".json"
        )
        companion_path.write_text(
            json.dumps(
                {
                    "scaler": artifact.scaler.to_dict(),
                    "hidden_size": artifact.hidden_size,
                    "lookback": artifact.lookback,
                    "last_window": artifact.last_window.tolist(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        report_path = self._artifacts.report_path(FORECAST_MODEL_NAME, version, ".json")
        report_path.write_text(
            json.dumps(
                {
                    "evaluation": artifact.evaluation.to_dict(),
                    "history_days": history_days,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        record = ModelRecord(
            name=FORECAST_MODEL_NAME,
            version=version,
            dataset_version=(
                f"daily-series-{dataset_start.isoformat()}-to-{dataset_end.isoformat()}"
            ),
            created_at=datetime.now(UTC).isoformat(),
            git_commit=git_commit_hash(),
            framework="pytorch-lstm",
            metrics=artifact.evaluation.to_dict(),
            export_formats=("pytorch",),
            artifact_location=checkpoint_path.as_posix(),
            tags={
                "series_hash": series_hash,
                "lookback": str(artifact.lookback),
                "history_days": str(history_days),
            },
        )
        self._registry.register(record)
        logger.info("Trained and registered forecasting model version={}.", version)
        return record


def _history_points(
    dates: list[date], values: np.ndarray, *, cap: int
) -> tuple[HistoryPoint, ...]:
    """Return the trailing ``cap`` real (zero-filled) days, for display context."""
    if not dates or cap <= 0:
        return ()
    tail = min(cap, len(dates))
    return tuple(
        HistoryPoint(date=dates[i], actual_weight_kg=float(values[i]))
        for i in range(len(dates) - tail, len(dates))
    )
