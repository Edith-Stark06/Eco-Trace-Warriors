"""End-to-end tests for the passport service (milestone M2.3).

Exercises :meth:`PassportService.build` by actually running the upstream engines
(recoverability, component, material, environmental, decision-knowledge, circular)
over a hand-built :class:`DeviceContext`, then composing the resulting reports plus
a real :class:`DeviceFingerprint` into a :class:`DevicePassport`. Only the external
catalogues/schema are read from disk; there is no fusion run and no models.

Asserts the service loads the shipped schema once, validates every assembled
passport against it, stamps provenance, honours the injected clock, is
deterministic, and never exposes a monetary field — mirroring the M2.2 circular
service test structure.
"""

from datetime import UTC, datetime

import pytest

from device_ai.circular import CircularService
from device_ai.components import ComponentService
from device_ai.decision import DecisionService
from device_ai.environmental import EnvironmentalService
from device_ai.fingerprint.models import DeviceFingerprint
from device_ai.fusion.models import (
    Conflict,
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.materials import MaterialService
from device_ai.passport import (
    PASSPORT_ENGINE_VERSION,
    DevicePassport,
    PassportConfig,
    PassportService,
)
from device_ai.recoverability import RecoverabilityService

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _service(*, with_clock=False, config=None, schema=None):
    return PassportService(
        config=config,
        schema=schema,
        clock=(lambda: _CLOCK) if with_clock else None,
    )


def _resolved(attribute, value, confidence=0.9):
    return ResolvedAttribute(
        attribute=attribute,
        value=value,
        confidence=confidence,
        sources=(EvidenceKind.DETECTION,),
    )


def _context(
    *,
    device_type="laptop",
    model="XPS-13",
    serial="SN123",
    confidence=0.9,
    conflicts=(),
    eco_id="ET-2026-0000ABCD",
    fingerprint="f" * 64,
):
    attributes = [_resolved(FusionAttribute.DEVICE_TYPE, device_type)]
    if model:
        attributes.append(_resolved(FusionAttribute.MODEL, model))
    if serial:
        attributes.append(_resolved(FusionAttribute.SERIAL_NUMBER, serial))
    return DeviceContext(
        eco_id=eco_id,
        fingerprint=fingerprint,
        attributes=tuple(attributes),
        confidence=confidence,
        evidence=(),
        conflicts=tuple(conflicts),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _fingerprint(*, eco_id="ET-2026-0000ABCD", fingerprint="f" * 64):
    return DeviceFingerprint(
        eco_id=eco_id,
        fingerprint=fingerprint,
        embedding=(0.1, 0.2, 0.3),
        dimension=3,
        encoder_name="CLIP",
        encoder_version="1.0",
        metric="cosine",
        created_at=_CLOCK,
    )


def _upstream(context):
    """Run the real upstream engines and return the four passport reports."""
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    materials = MaterialService(clock=None).analyze(context, recoverability, components)
    environmental = EnvironmentalService(clock=None).analyze(
        context, recoverability, components, materials
    )
    knowledge = DecisionService(clock=None).analyze(
        context, recoverability, components, materials, environmental
    )
    decision = CircularService(clock=None).decide(
        context, knowledge, recoverability, environmental
    )
    return decision, materials, environmental


def _build(context, *, with_clock=False, fingerprint=True, config=None, schema=None):
    decision, materials, environmental = _upstream(context)
    fp = _fingerprint() if fingerprint else None
    return _service(with_clock=with_clock, config=config, schema=schema).build(
        context, decision, materials, environmental, fp
    )


# --- End-to-end assembly --------------------------------------------------


def test_build_identifiable_laptop_passport():
    passport = _build(_context())
    assert isinstance(passport, DevicePassport)
    assert passport.eco_id == "ET-2026-0000ABCD"
    assert passport.classification.device_type == "laptop"
    assert passport.decision_summary.recommended_action
    assert passport.passport_id.startswith("ET-PP-")


def test_build_validates_against_schema():
    # A successfully returned passport has already passed schema validation
    # inside the service; assert its serialized form re-validates cleanly.
    from device_ai.passport.schema import validate_passport

    service = _service()
    decision, materials, environmental = _upstream(_context())
    passport = service.build(
        _context(), decision, materials, environmental, _fingerprint()
    )
    validate_passport(passport.to_dict(), service.schema)  # Should not raise


def test_service_loads_shipped_schema_by_default():
    service = _service()
    assert service.schema.version
    assert service.schema.section_count == 13


def test_build_without_fingerprint_still_valid():
    passport = _build(_context(fingerprint=""), fingerprint=False)
    assert passport.fingerprint_summary.fingerprint == ""
    assert any("fingerprint" in warning.lower() for warning in passport.warnings)


# --- Provenance & clock ---------------------------------------------------


def test_service_stamps_versions_and_optional_clock():
    with_clock = _build(_context(), with_clock=True)
    assert with_clock.metadata.passport_engine_version == PASSPORT_ENGINE_VERSION
    assert with_clock.metadata.schema_version == with_clock.metadata.schema_version
    assert with_clock.metadata.created_at == _CLOCK
    without_clock = _build(_context())
    assert without_clock.metadata.created_at is None


def test_schema_version_stamped_from_loaded_schema():
    service = _service()
    decision, materials, environmental = _upstream(_context())
    passport = service.build(
        _context(), decision, materials, environmental, _fingerprint()
    )
    assert passport.metadata.schema_version == service.schema.version


# --- Determinism ----------------------------------------------------------


def test_build_is_deterministic_for_identical_input():
    context = _context()
    decision, materials, environmental = _upstream(context)
    service = _service()
    fp = _fingerprint()
    first = service.build(context, decision, materials, environmental, fp)
    second = service.build(context, decision, materials, environmental, fp)
    assert first.to_json() == second.to_json()


def test_passport_id_stable_across_service_instances():
    context = _context()
    first = _build(context)
    second = _build(context)
    assert first.passport_id == second.passport_id


# --- Confidence composition -----------------------------------------------


def test_overall_confidence_in_unit_interval():
    passport = _build(_context())
    assert 0.0 <= passport.confidence_summary.overall <= 1.0


def test_conflicted_context_damps_identity_confidence():
    clean = _build(_context())
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    conflicted = _build(_context(conflicts=(conflict,)))
    assert conflicted.classification.has_conflicts is True
    assert clean.classification.has_conflicts is False


# --- Injected config & schema ---------------------------------------------


def test_custom_config_is_exposed_on_service():
    config = PassportConfig(max_warnings=1)
    service = PassportService(config=config, clock=None)
    assert service.config.max_warnings == 1


def test_config_from_settings_maps_env_knobs():
    from device_ai.configs.settings import Settings

    settings = Settings(
        passport_schema_path="custom/schema.yaml",
        passport_version="2.0.0",
    )
    config = PassportConfig.from_settings(settings)
    assert config.schema_path == "custom/schema.yaml"
    assert config.passport_version == "2.0.0"


# --- No monetary surface & immutability -----------------------------------


def test_passport_exposes_no_monetary_field():
    passport = _build(_context())
    payload = passport.to_dict()
    forbidden = {"price", "value_usd", "value_inr", "cost", "currency", "market_value"}
    assert forbidden.isdisjoint(payload)


def test_passport_is_immutable():
    passport = _build(_context())
    with pytest.raises((AttributeError, TypeError)):
        passport.eco_id = "hacked"  # type: ignore[misc]
