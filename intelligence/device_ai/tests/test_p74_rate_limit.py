"""P7.4 — /predict rate limiting."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.exceptions import RateLimitExceededError
from device_ai.utils.rate_limit import RateLimiter

from .conftest import make_image_bytes


def _valid_upload() -> list:
    """A single well-formed image upload for the ``images`` multipart field."""
    return [("images", ("device.png", make_image_bytes(), "image/png"))]


# --- RateLimiter (unit-level) ------------------------------------------


def test_allows_requests_within_the_limit() -> None:
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)
    limiter.check("client-a")
    limiter.check("client-a")
    limiter.check("client-a")  # exactly at the limit — must not raise


def test_raises_once_the_limit_is_exceeded() -> None:
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)
    limiter.check("client-a")
    limiter.check("client-a")
    with pytest.raises(RateLimitExceededError):
        limiter.check("client-a")


def test_tracks_each_client_key_independently() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)
    limiter.check("client-a")
    limiter.check("client-b")  # different client — its own budget


def test_resets_the_window_after_it_elapses() -> None:
    clock = {"t": 0.0}
    limiter = RateLimiter(max_requests=1, window_seconds=10.0, clock=lambda: clock["t"])

    limiter.check("client-a")
    with pytest.raises(RateLimitExceededError):
        limiter.check("client-a")
    clock["t"] += 11.0  # past the window
    limiter.check("client-a")  # must not raise — new window


def test_reset_clears_all_recorded_windows() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)
    limiter.check("client-a")
    limiter.reset()
    limiter.check("client-a")  # must not raise — state was cleared


# --- GET /predict rate limiting (integration) ---------------------------


@pytest.fixture()
def rate_limited_client() -> Iterator[TestClient]:
    settings = Settings(
        environment="development",
        log_level="WARNING",
        json_logs=False,
        predict_rate_limit_max_requests=2,
        predict_rate_limit_window_seconds=60.0,
    )
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    # get_predict_rate_limiter() calls get_settings() directly (not via
    # FastAPI's Depends resolution), so overriding get_settings above does
    # not reach it — override the limiter itself instead, matching the
    # existing dataset_client fixture's pattern for settings-dependent
    # singletons (conftest.py). Build the instance ONCE here — a lambda
    # that constructs a fresh RateLimiter per call would reset the count
    # on every request, since FastAPI invokes an override callable fresh
    # per request unless it is itself cached.
    limiter = RateLimiter(
        max_requests=settings.predict_rate_limit_max_requests,
        window_seconds=settings.predict_rate_limit_window_seconds,
    )
    app.dependency_overrides[dependencies.get_predict_rate_limiter] = lambda: limiter

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_predict_returns_429_once_the_client_exceeds_the_limit(
    rate_limited_client: TestClient,
) -> None:
    first = rate_limited_client.post("/predict", files=_valid_upload())
    second = rate_limited_client.post("/predict", files=_valid_upload())
    third = rate_limited_client.post("/predict", files=_valid_upload())

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    body = third.json()
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_other_endpoints_are_never_rate_limited_by_the_predict_limiter(
    rate_limited_client: TestClient,
) -> None:
    for _ in range(5):
        response = rate_limited_client.get("/health")
        assert response.status_code == 200
