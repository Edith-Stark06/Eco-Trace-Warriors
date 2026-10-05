"""P8.7 — service-to-service authentication (ServiceApiKeyMiddleware).

Proves both halves of the contract: unset (default) behaves identically to
every pre-P8.7 test/demo/dev caller, and when configured, every non-public
route genuinely requires the header while the public allowlist stays open.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from device_ai.api import dependencies
from device_ai.api.service_auth import SERVICE_API_KEY_HEADER
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings

from .conftest import make_image_bytes

_KEY = "p87-test-service-key"


@pytest.fixture()
def open_client() -> Iterator[TestClient]:
    """No service_api_key configured — must behave exactly as before P8.7."""
    settings = Settings(environment="development", log_level="WARNING", json_logs=False)
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        yield test_client
    dependencies.reset_dependency_caches()


@pytest.fixture()
def guarded_client() -> Iterator[TestClient]:
    """service_api_key configured — every non-public route must require it."""
    settings = Settings(
        environment="development", log_level="WARNING", json_logs=False, service_api_key=_KEY
    )
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        yield test_client
    dependencies.reset_dependency_caches()


# --- Unset service_api_key: unchanged pre-P8.7 behavior ---------------------


def test_open_client_reaches_health_with_no_header(open_client: TestClient) -> None:
    response = open_client.get("/health")
    assert response.status_code == 200


def test_open_client_reaches_a_sensitive_route_with_no_header(open_client: TestClient) -> None:
    """Registration is a mutating, otherwise-unauthenticated route — with no
    key configured it must remain reachable exactly as before P8.7, so local
    dev, the demo script, and the rest of the test suite need no changes."""
    response = open_client.post(
        "/devices/register",
        files=[("images", ("demo.png", make_image_bytes(), "image/png"))],
        data={"capture_id": "p87-open-client"},
    )
    assert response.status_code == 200


# --- Configured service_api_key: enforced on non-public routes --------------


def test_guarded_client_still_reaches_public_health_with_no_header(
    guarded_client: TestClient,
) -> None:
    response = guarded_client.get("/health")
    assert response.status_code == 200


def test_guarded_client_still_reaches_blockchain_health_with_no_header(
    guarded_client: TestClient,
) -> None:
    """The one route the backend's own read-only proxy calls — must stay
    reachable with no key, matching its public treatment on the backend
    side (`blockchain.routes.ts`)."""
    response = guarded_client.get("/system/blockchain/health")
    assert response.status_code == 200


def test_guarded_client_rejects_a_sensitive_route_with_no_header(
    guarded_client: TestClient,
) -> None:
    response = guarded_client.post(
        "/devices/register",
        files=[("images", ("demo.png", make_image_bytes(), "image/png"))],
        data={"capture_id": "p87-no-header"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_guarded_client_rejects_a_sensitive_route_with_the_wrong_key(
    guarded_client: TestClient,
) -> None:
    response = guarded_client.post(
        "/devices/register",
        files=[("images", ("demo.png", make_image_bytes(), "image/png"))],
        data={"capture_id": "p87-wrong-key"},
        headers={SERVICE_API_KEY_HEADER: "not-the-real-key"},
    )
    assert response.status_code == 401


def test_guarded_client_accepts_a_sensitive_route_with_the_correct_key(
    guarded_client: TestClient,
) -> None:
    response = guarded_client.post(
        "/devices/register",
        files=[("images", ("demo.png", make_image_bytes(), "image/png"))],
        data={"capture_id": "p87-correct-key"},
        headers={SERVICE_API_KEY_HEADER: _KEY},
    )
    assert response.status_code == 200


def test_guarded_client_rejects_a_read_route_with_no_header(guarded_client: TestClient) -> None:
    """Not just mutating routes — device reads are gated too."""
    response = guarded_client.get("/devices/DEV-NONEXISTENT-00")
    assert response.status_code == 401
