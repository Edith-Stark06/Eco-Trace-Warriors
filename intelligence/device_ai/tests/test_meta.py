"""Tests for the meta endpoints: /, /health, /version."""

from device_ai import __version__


def test_root(client):
    """GET / returns service metadata and liveness."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "EcoTrace Device Intelligence Engine"
    assert data["status"] == "ok"
    assert data["version"] == __version__
    assert data["docs"] == "/docs"


def test_health(client):
    """GET /health returns readiness including per-component status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["version"] == __version__
    assert "components" in data
    assert isinstance(data["components"], list)
    # Mock components are always ready.
    for component in data["components"]:
        assert component["ready"] is True
    assert "model_dir_available" in data


def test_version(client):
    """GET /version returns service and model-contract version."""
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "EcoTrace Device Intelligence Engine"
    assert data["version"] == __version__
    assert data["model_version"] == "1.0.0"
    assert data["api"] == "v1"
