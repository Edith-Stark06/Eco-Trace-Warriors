"""P7.2 — production-safety validation for Settings.

Mirrors backend/tests/unit/config.test.ts: proves that a `production`
environment combined with a configuration that would otherwise only fail
later, at first use, is instead rejected eagerly at startup.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from device_ai.configs.settings import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg,arg-type]


def test_development_defaults_accept_memory_backends() -> None:
    settings = _settings()
    assert settings.environment == "development"
    assert settings.device_backend == "memory"
    assert settings.database_url is None


def test_production_rejects_postgres_device_backend_without_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL is required in production"):
        _settings(environment="production", device_backend="postgres")


def test_production_rejects_postgres_trust_anchor_backend_without_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL is required in production"):
        _settings(environment="production", trust_anchor_backend="postgres")


def test_production_accepts_postgres_backends_with_database_url() -> None:
    settings = _settings(
        environment="production",
        device_backend="postgres",
        trust_anchor_backend="postgres",
        database_url="postgresql+psycopg://user:pass@host:5432/db",
    )
    assert settings.database_url is not None


def test_production_rejects_fabric_enabled_without_identity_material() -> None:
    with pytest.raises(ValidationError, match="FABRIC_ENABLED=true requires"):
        _settings(environment="production", fabric_enabled=True)


def test_production_rejects_fabric_enabled_with_partial_identity_material() -> None:
    with pytest.raises(ValidationError, match="FABRIC_TLS_CERT_PATH"):
        _settings(
            environment="production",
            fabric_enabled=True,
            fabric_identity_cert_path="/certs/id.pem",
            fabric_identity_key_path="/certs/id.key",
        )


def test_production_accepts_fabric_enabled_with_full_identity_material() -> None:
    settings = _settings(
        environment="production",
        fabric_enabled=True,
        fabric_tls_cert_path="/certs/ca.pem",
        fabric_identity_cert_path="/certs/id.pem",
        fabric_identity_key_path="/certs/id.key",
    )
    assert settings.fabric_enabled is True


def test_staging_environment_is_not_held_to_production_safety_rules() -> None:
    """`staging` deliberately does not trigger the production refinement —
    it is a distinct, less strict deployment tier (matches the Literal's
    three-way split: development | staging | production)."""
    settings = _settings(environment="staging", device_backend="postgres")
    assert settings.database_url is None
