"""P7.3 — observability: /metrics endpoint, database health, Fabric tx counters."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.database.database import ping_engine
from device_ai.utils.metrics import MetricsRegistry, get_metrics_registry

# --- MetricsRegistry (unit-level) ------------------------------------------


def test_registry_starts_empty() -> None:
    registry = MetricsRegistry()
    snapshot = registry.snapshot()

    assert snapshot["requests"]["total"] == 0
    assert snapshot["requests"]["by_route"] == []
    assert snapshot["fabric"] == {"transactions": 0, "succeeded": 0, "failed": 0}


def test_registry_aggregates_requests_per_route() -> None:
    registry = MetricsRegistry()
    registry.record_request("GET", "/health", 200, 10.0)
    registry.record_request("GET", "/health", 200, 20.0)
    registry.record_request("GET", "/health", 500, 30.0)

    snapshot = registry.snapshot()
    assert snapshot["requests"]["total"] == 3
    entry = snapshot["requests"]["by_route"][0]
    assert entry["method"] == "GET"
    assert entry["route"] == "/health"
    assert entry["count"] == 3
    assert entry["avg_duration_ms"] == 20.0
    assert entry["status_counts"] == {"200": 2, "500": 1}


def test_registry_records_fabric_transaction_outcomes() -> None:
    registry = MetricsRegistry()
    registry.record_fabric_transaction(succeeded=True)
    registry.record_fabric_transaction(succeeded=False)
    registry.record_fabric_transaction(succeeded=True)

    snapshot = registry.snapshot()
    assert snapshot["fabric"] == {"transactions": 3, "succeeded": 2, "failed": 1}


def test_registry_reset_clears_everything() -> None:
    registry = MetricsRegistry()
    registry.record_request("GET", "/health", 200, 10.0)
    registry.record_fabric_transaction(succeeded=True)

    registry.reset()

    snapshot = registry.snapshot()
    assert snapshot["requests"]["total"] == 0
    assert snapshot["fabric"]["transactions"] == 0


# --- ping_engine (unit-level) -----------------------------------------------


def test_ping_engine_succeeds_against_a_reachable_sqlite_database(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ping_ok.db'}")
    assert ping_engine(engine) is True


def test_ping_engine_returns_false_without_raising_on_an_unreachable_database() -> None:
    # 10.255.255.1 is a non-routable address that drops packets rather than
    # actively refusing the connection, so an explicit short connect_timeout
    # is required — otherwise the OS/driver default (tens of seconds) makes
    # this test slow or effectively hang. Deterministic and fast either way.
    engine = create_engine(
        "postgresql+psycopg://nouser:nopass@10.255.255.1:5432/nodb",
        connect_args={"connect_timeout": 1},
    )
    assert ping_engine(engine) is False


# --- GET /metrics (integration) ---------------------------------------------


@pytest.fixture()
def observability_client() -> Iterator[TestClient]:
    settings = Settings(environment="development", log_level="WARNING", json_logs=False)
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    get_metrics_registry().reset()
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()
    get_metrics_registry().reset()


def test_metrics_endpoint_returns_the_documented_envelope(
    observability_client: TestClient,
) -> None:
    response = observability_client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "requests" in body["metrics"]
    assert "fabric" in body["metrics"]
    assert "uptime_seconds" in body["metrics"]


def test_metrics_endpoint_reflects_prior_requests_by_matched_route(
    observability_client: TestClient,
) -> None:
    observability_client.get("/health")
    observability_client.get("/health")

    response = observability_client.get("/metrics")
    by_route = response.json()["metrics"]["requests"]["by_route"]
    health_entry = next(
        (r for r in by_route if r["method"] == "GET" and r["route"] == "/health"), None
    )

    assert health_entry is not None
    assert health_entry["count"] >= 2


# --- GET /health database component -----------------------------------------


def test_health_omits_database_component_when_no_backend_uses_postgres(
    observability_client: TestClient,
) -> None:
    response = observability_client.get("/health")
    names = [c["name"] for c in response.json()["components"]]
    assert "database" not in names


def test_health_reports_database_ready_when_postgres_backend_is_reachable(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="development",
        log_level="WARNING",
        json_logs=False,
        device_backend="postgres",
        database_url=f"sqlite:///{tmp_path / 'health_ok.db'}",
    )
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        response = client.get("/health")

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()

    body = response.json()
    db_component = next(c for c in body["components"] if c["name"] == "database")
    assert db_component["ready"] is True
    assert body["status"] == "healthy"


def test_health_reports_degraded_when_postgres_backend_is_unreachable() -> None:
    settings = Settings(
        environment="development",
        log_level="WARNING",
        json_logs=False,
        device_backend="postgres",
        # A non-routable address with an explicit connect_timeout query
        # param (embedded in the URL since get_engine() doesn't expose
        # connect_args) keeps this deterministic and fast rather than
        # relying on OS-specific connection-refused timing.
        database_url="postgresql+psycopg://nouser:nopass@10.255.255.1:5432/nodb?connect_timeout=1",
    )
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        response = client.get("/health")

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()

    body = response.json()
    db_component = next(c for c in body["components"] if c["name"] == "database")
    assert db_component["ready"] is False
    assert body["status"] == "degraded"
