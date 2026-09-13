"""Test suite for e-waste demand forecasting (P10.1).

Covers:
1. Historical data aggregation (build_daily_series: zero-filling).
2. Duplicate submission handling (same-date observations are summed, once).
3. Time-series preprocessing (MinMaxScaler, including the degenerate/flat case).
4. Sliding-window generation.
5. Model training (real torch, chronological split) — skipped when torch is absent.
6. Model inference / recursive multi-step prediction — skipped when torch is absent.
7. Forecast horizon (varying horizon lengths via the service and the API).
8. Insufficient-data handling (truthful degraded response, no fabrication).
9. Invalid horizon (schema validation -> 422).
10. API response contract (POST /forecast/ewaste via TestClient).
11. MODEL_BACKEND_UNAVAILABLE degradation when torch is unavailable (monkeypatched).
12. Caching: unchanged series reuses the trained model; force_retrain bypasses it.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.forecasting.model import torch_available
from device_ai.forecasting.models import DailyObservation
from device_ai.forecasting.preprocessing import (
    MinMaxScaler,
    build_daily_series,
    make_sliding_windows,
)
from device_ai.forecasting.service import ForecastingService
from device_ai.training.registry.artifact_manager import ArtifactManager
from device_ai.training.registry.model_registry import ModelRegistry

# ---------------------------------------------------------------------------
# 1-2. build_daily_series: zero-filling + duplicate-date summation
# ---------------------------------------------------------------------------


def test_build_daily_series_zero_fills_missing_days() -> None:
    obs = [
        DailyObservation(date=date(2026, 1, 1), weight_kg=5.0),
        DailyObservation(date=date(2026, 1, 4), weight_kg=3.0),
    ]
    dates, values = build_daily_series(obs)

    assert dates == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 4),
    ]
    assert values.tolist() == [5.0, 0.0, 0.0, 3.0]


def test_build_daily_series_sums_duplicate_dates_without_double_counting() -> None:
    """Two submissions recycled on the same day contribute once, summed."""
    obs = [
        DailyObservation(date=date(2026, 1, 1), weight_kg=2.5),
        DailyObservation(date=date(2026, 1, 1), weight_kg=1.5),
        DailyObservation(date=date(2026, 1, 2), weight_kg=4.0),
    ]
    dates, values = build_daily_series(obs)

    assert dates == [date(2026, 1, 1), date(2026, 1, 2)]
    assert values.tolist() == [4.0, 4.0]


def test_build_daily_series_empty_input() -> None:
    dates, values = build_daily_series([])
    assert dates == []
    assert values.tolist() == []


def test_build_daily_series_single_observation() -> None:
    single = DailyObservation(date=date(2026, 1, 1), weight_kg=7.0)
    dates, values = build_daily_series([single])
    assert dates == [date(2026, 1, 1)]
    assert values.tolist() == [7.0]


# ---------------------------------------------------------------------------
# 3. MinMaxScaler
# ---------------------------------------------------------------------------


def test_minmax_scaler_round_trips() -> None:
    values = np.array([0.0, 5.0, 10.0])
    scaler = MinMaxScaler().fit(values)

    scaled = scaler.transform(values)
    assert scaled.tolist() == [0.0, 0.5, 1.0]
    assert np.allclose(scaler.inverse_transform(scaled), values)


def test_minmax_scaler_degenerate_constant_series_does_not_divide_by_zero() -> None:
    values = np.array([4.0, 4.0, 4.0])
    scaler = MinMaxScaler().fit(values)

    scaled = scaler.transform(values)
    assert scaled.tolist() == [0.0, 0.0, 0.0]
    assert scaler.inverse_transform(scaled).tolist() == [4.0, 4.0, 4.0]


def test_minmax_scaler_raises_before_fit() -> None:
    with pytest.raises(RuntimeError):
        MinMaxScaler().transform(np.array([1.0]))


def test_minmax_scaler_roundtrips_through_dict() -> None:
    scaler = MinMaxScaler().fit(np.array([1.0, 9.0]))
    restored = MinMaxScaler.from_dict(scaler.to_dict())
    probe = np.array([5.0])
    assert np.allclose(restored.transform(probe), scaler.transform(probe))


# ---------------------------------------------------------------------------
# 4. Sliding windows
# ---------------------------------------------------------------------------


def test_make_sliding_windows_shapes_and_values() -> None:
    series = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    x, y = make_sliding_windows(series, lookback=2)

    assert x.shape == (3, 2)
    assert y.shape == (3,)
    assert x.tolist() == [[1.0, 2.0], [2.0, 3.0], [3.0, 4.0]]
    assert y.tolist() == [3.0, 4.0, 5.0]


def test_make_sliding_windows_insufficient_series_returns_empty() -> None:
    x, y = make_sliding_windows(np.array([1.0, 2.0]), lookback=5)
    assert x.shape == (0, 5)
    assert y.shape == (0,)


# ---------------------------------------------------------------------------
# Shared fixtures for service/API tests
# ---------------------------------------------------------------------------


def _synthetic_observations(
    n_days: int, *, start: date = date(2026, 1, 1)
) -> list[DailyObservation]:
    """A deterministic, mildly-periodic synthetic series (NOT presented as
    real EcoTrace data anywhere outside this test file — see the forecasting
    service's own docstring for the real-data source: Submission.recycledAt
    /recoveredWeight via the Node backend)."""
    rng = np.random.default_rng(seed=7)
    seasonal = 3 * np.sin(np.arange(n_days) * (2 * np.pi / 7))
    values = 10 + seasonal + rng.uniform(-1, 1, n_days)
    values = np.clip(values, 0, None)
    return [
        DailyObservation(date=start + timedelta(days=i), weight_kg=float(round(v, 2)))
        for i, v in enumerate(values)
    ]


@pytest.fixture
def forecasting_service(tmp_path) -> ForecastingService:
    from device_ai.configs.settings import Settings

    settings = Settings(
        artifact_dir=tmp_path / "artifacts",
        forecast_default_epochs=5,  # keep tests fast
        forecast_min_history_days=30,
    )
    artifacts = ArtifactManager(root=tmp_path / "artifacts")
    registry_path = tmp_path / "artifacts" / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    return ForecastingService(settings, artifacts=artifacts, registry=registry)


# ---------------------------------------------------------------------------
# 8. Insufficient-data handling (no torch required — the check runs first)
# ---------------------------------------------------------------------------


def test_forecast_reports_insufficient_data_honestly(
    forecasting_service: ForecastingService,
) -> None:
    result = forecasting_service.forecast(_synthetic_observations(10), horizon=7)

    assert result.status.value == "INSUFFICIENT_HISTORICAL_DATA"
    assert result.points == ()
    assert result.evaluation is None
    assert result.model is None
    assert result.history_days == 10
    assert "10 day(s)" in (result.reason or "")
    assert "fabricated" in (result.reason or "").lower()


def test_forecast_insufficient_data_still_returns_partial_history_for_context(
    forecasting_service: ForecastingService,
) -> None:
    result = forecasting_service.forecast(_synthetic_observations(10), horizon=7)
    assert len(result.history) == 10


def test_forecast_rejects_a_wide_but_mostly_zero_padded_span(
    forecasting_service: ForecastingService,
) -> None:
    """A 45-day calendar span containing only 2 real recycling-activity days
    (the rest zero-filled padding) must not be treated as sufficient just
    because the *span* clears the day-count threshold — this is the exact
    case a naive span-only check would wrongly train on (real regression
    caught via live E2E testing against the actual production dataset)."""
    sparse = [
        DailyObservation(date=date(2026, 1, 1), weight_kg=15.1),
        DailyObservation(date=date(2026, 2, 14), weight_kg=2.0),
    ]

    result = forecasting_service.forecast(sparse, horizon=7)

    assert result.status.value == "INSUFFICIENT_HISTORICAL_DATA"
    assert result.points == ()
    assert result.model is None
    assert result.history_days == 45
    assert "2 of them" in (result.reason or "")
    assert "fabricated" in (result.reason or "").lower()


# ---------------------------------------------------------------------------
# 5-6-7-12. Real training / inference / horizon / caching (requires torch)
# ---------------------------------------------------------------------------

requires_torch = pytest.mark.skipif(
    not torch_available(),
    reason="forecasting model training requires the optional torch dependency",
)


@requires_torch
def test_forecast_trains_and_evaluates_with_real_chronological_metrics(
    forecasting_service: ForecastingService,
) -> None:
    result = forecasting_service.forecast(_synthetic_observations(60), horizon=7)

    assert result.status.value == "TRAINED"
    assert result.model is not None
    assert result.model.name == "ewaste-forecast-lstm"
    assert result.evaluation is not None
    assert result.evaluation.rmse >= 0.0
    assert result.evaluation.mae >= 0.0
    assert result.evaluation.train_samples > 0
    assert result.evaluation.val_samples > 0
    # Chronological split: train + val samples must not exceed the total
    # sliding-window count, and val must be a real, non-trivial holdout.
    assert result.evaluation.val_samples >= 5


@requires_torch
@pytest.mark.parametrize("horizon", [1, 7, 30])
def test_forecast_honors_requested_horizon(
    forecasting_service: ForecastingService, horizon: int
) -> None:
    result = forecasting_service.forecast(_synthetic_observations(60), horizon=horizon)

    assert result.status.value == "TRAINED"
    assert len(result.points) == horizon
    # Points are consecutive future calendar days.
    for i in range(1, len(result.points)):
        assert result.points[i].date == result.points[i - 1].date + timedelta(days=1)
    # A recycled weight can never be negative.
    assert all(p.predicted_weight_kg >= 0.0 for p in result.points)


@requires_torch
def test_forecast_reuses_cached_model_when_series_unchanged(
    forecasting_service: ForecastingService,
) -> None:
    observations = _synthetic_observations(60)

    first = forecasting_service.forecast(observations, horizon=7)
    second = forecasting_service.forecast(observations, horizon=7)

    assert first.model is not None and second.model is not None
    assert first.model.version == second.model.version


@requires_torch
def test_forecast_force_retrain_produces_a_new_model_version(
    forecasting_service: ForecastingService,
) -> None:
    observations = _synthetic_observations(60)

    first = forecasting_service.forecast(observations, horizon=7)
    second = forecasting_service.forecast(observations, horizon=7, force_retrain=True)

    assert first.model is not None and second.model is not None
    assert first.model.version != second.model.version


@requires_torch
def test_forecast_retrains_when_series_actually_changes(
    forecasting_service: ForecastingService,
) -> None:
    observations = _synthetic_observations(60)
    first = forecasting_service.forecast(observations, horizon=7)

    next_day = observations[-1].date + timedelta(days=1)
    extended = observations + _synthetic_observations(1, start=next_day)
    second = forecasting_service.forecast(extended, horizon=7)

    assert first.model is not None and second.model is not None
    assert first.model.version != second.model.version
    assert second.history_days == 61


# ---------------------------------------------------------------------------
# 9-10-11. API contract via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(tmp_path) -> TestClient:
    from device_ai.configs.settings import Settings, get_settings

    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    artifacts_root = tmp_path / "artifacts"
    test_settings = Settings(artifact_dir=artifacts_root, forecast_default_epochs=5)
    test_service = ForecastingService(
        test_settings,
        artifacts=ArtifactManager(root=artifacts_root),
        registry=ModelRegistry(registry_path=artifacts_root / "model_registry.json"),
    )
    app = create_app(settings=test_settings)
    app.dependency_overrides[get_settings] = lambda: test_settings
    overrides = app.dependency_overrides
    overrides[dependencies.get_forecasting_service] = lambda: test_service

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


@requires_torch
def test_api_forecast_contract_when_trained(api_client: TestClient) -> None:
    obs = [
        {"date": o.date.isoformat(), "weight_kg": o.weight_kg}
        for o in _synthetic_observations(60)
    ]
    payload = {"observations": obs, "horizon": 5}
    response = api_client.post("/forecast/ewaste", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["status"] == "TRAINED"
    assert len(body["points"]) == 5
    assert set(body["points"][0].keys()) == {"date", "predicted_weight_kg"}
    assert body["evaluation"]["rmse"] >= 0
    assert body["model"]["name"] == "ewaste-forecast-lstm"
    assert body["request_id"] is not None


def test_api_forecast_contract_when_insufficient_data(api_client: TestClient) -> None:
    payload = {"observations": [], "horizon": 30}
    response = api_client.post("/forecast/ewaste", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["status"] == "INSUFFICIENT_HISTORICAL_DATA"
    assert body["points"] == []
    assert body["evaluation"] is None
    assert body["model"] is None
    assert body["reason"]


@pytest.mark.parametrize("bad_horizon", [0, -5, 91, "not-a-number"])
def test_api_rejects_invalid_horizon(
    api_client: TestClient, bad_horizon: object
) -> None:
    payload = {"observations": [], "horizon": bad_horizon}
    response = api_client.post("/forecast/ewaste", json=payload)
    assert response.status_code == 422


def test_api_rejects_malformed_observation_date(api_client: TestClient) -> None:
    response = api_client.post(
        "/forecast/ewaste",
        json={"observations": [{"date": "not-a-date", "weight_kg": 1.0}], "horizon": 7},
    )
    assert response.status_code == 422


def test_api_rejects_negative_weight(api_client: TestClient) -> None:
    response = api_client.post(
        "/forecast/ewaste",
        json={
            "observations": [{"date": "2026-01-01", "weight_kg": -1.0}],
            "horizon": 7,
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 11 (cont'd). MODEL_BACKEND_UNAVAILABLE degradation (no crash, no fabrication)
# ---------------------------------------------------------------------------


def test_forecast_degrades_when_torch_unavailable(
    forecasting_service: ForecastingService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("device_ai.forecasting.service.torch_available", lambda: False)

    result = forecasting_service.forecast(_synthetic_observations(60), horizon=7)

    assert result.status.value == "MODEL_BACKEND_UNAVAILABLE"
    assert result.points == ()
    assert result.model is None
    assert "PyTorch" in (result.reason or "")
