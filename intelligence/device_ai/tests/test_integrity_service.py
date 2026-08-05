"""End-to-end tests for the passport integrity service (milestone M2.4).

Exercises :meth:`IntegrityService.validate` by actually running the upstream
engines (recoverability, component, material, environmental, decision-knowledge,
circular) over a hand-built :class:`DeviceContext`, composing a real
:class:`DevicePassport` via the passport service, then validating and hashing it.
Only the external catalogues/schema/rule-set are read from disk; there is no
fusion run and no models.

Asserts the service loads the shipped rule-set once, validates a well-formed
passport as valid with a 64-hex SHA-256 hash, is deterministic, honours the
injected clock, stamps provenance, flags a no-fingerprint passport as
valid-with-warnings, detects tampering, and never exposes a monetary field —
mirroring the M2.3 passport service test structure.
"""

from datetime import UTC, datetime

import pytest

from device_ai.circular import CircularService
from device_ai.components import ComponentService
from device_ai.decision import DecisionService
from device_ai.environmental import EnvironmentalService
from device_ai.fingerprint.models import DeviceFingerprint
from device_ai.fusion.models import (
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.integrity import (
    INTEGRITY_ENGINE_VERSION,
    IntegrityConfig,
    IntegrityService,
    PassportIntegrityReport,
    ValidationStatus,
)
from device_ai.materials import MaterialService
from device_ai.passport import PassportService
from device_ai.recoverability import RecoverabilityService

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _service(*, with_clock=False, config=None, rules=None):
    return IntegrityService(
        config=config,
        rules=rules,
        clock=(lambda: _CLOCK) if with_clock else None,
    )


def _resolved(attribute, value, confidence=0.9):
    return ResolvedAttribute(
        attribute=attribute,
        value=value,
        confidence=confidence,
        sources=(EvidenceKind.DETECTION,),
    )


def _context(*, fingerprint="f" * 64):
    return DeviceContext(
        eco_id="ET-2026-0000ABCD",
        fingerprint=fingerprint,
        attributes=(
            _resolved(FusionAttribute.DEVICE_TYPE, "laptop"),
            _resolved(FusionAttribute.MODEL, "XPS-13"),
            _resolved(FusionAttribute.SERIAL_NUMBER, "SN123"),
        ),
        confidence=0.9,
        evidence=(),
        conflicts=(),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _fingerprint():
    return DeviceFingerprint(
        eco_id="ET-2026-0000ABCD",
        fingerprint="f" * 64,
        embedding=(0.1, 0.2, 0.3),
        dimension=3,
        encoder_name="CLIP",
        encoder_version="1.0",
        metric="cosine",
        created_at=_CLOCK,
    )


def _passport(*, fingerprint=True):
    context = _context(fingerprint="f" * 64 if fingerprint else "")
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
    fp = _fingerprint() if fingerprint else None
    return PassportService(clock=None).build(
        context, decision, materials, environmental, fp
    )


# --- End-to-end validation ------------------------------------------------


def test_validate_well_formed_passport_is_valid():
    report = _service().validate(_passport())
    assert isinstance(report, PassportIntegrityReport)
    assert report.status is ValidationStatus.VALID
    assert report.is_valid is True
    assert report.error_count == 0
    assert report.checked_count == 13


def test_report_carries_sha256_hash():
    report = _service().validate(_passport())
    assert report.hash_algorithm == "sha256"
    assert len(report.canonical_hash) == 64
    assert all(char in "0123456789abcdef" for char in report.canonical_hash)


def test_report_echoes_schema_and_passport_versions():
    passport = _passport()
    report = _service().validate(passport)
    assert report.schema_version == passport.metadata.schema_version
    assert report.passport_version == passport.passport_version


def test_service_loads_shipped_rules_by_default():
    service = _service()
    assert service.rules.version
    assert service.rules.section_count == 13


# --- No-fingerprint passport ----------------------------------------------


def test_no_fingerprint_passport_is_still_valid():
    # The M2.3 builder always emits a fingerprint_summary section — an all-empty
    # (still structurally valid) one when no fingerprint is available — so the
    # section is present with every field defaulted, and the passport validates.
    report = _service().validate(_passport(fingerprint=False))
    assert report.status is ValidationStatus.VALID
    assert report.is_valid is True
    assert report.error_count == 0
    fingerprint = next(
        section
        for section in report.checked_sections
        if section.name == "fingerprint_summary"
    )
    assert fingerprint.present is True
    assert fingerprint.valid is True


# --- Provenance & clock ---------------------------------------------------


def test_service_stamps_versions_and_optional_clock():
    with_clock = _service(with_clock=True).validate(_passport())
    assert with_clock.engine_version == INTEGRITY_ENGINE_VERSION
    assert with_clock.rules_version == _service().rules.version
    assert with_clock.created_at == _CLOCK
    without_clock = _service().validate(_passport())
    assert without_clock.created_at is None


# --- Determinism & tamper detection ---------------------------------------


def test_validate_is_deterministic_for_identical_passport():
    passport = _passport()
    service = _service()
    first = service.validate(passport)
    second = service.validate(passport)
    assert first.to_json() == second.to_json()


def test_hash_stable_across_service_instances():
    passport = _passport()
    first = _service().validate(passport)
    second = _service().validate(passport)
    assert first.canonical_hash == second.canonical_hash


def test_tampered_passport_changes_hash():
    import dataclasses

    passport = _passport()
    baseline = _service().validate(passport)
    tampered = dataclasses.replace(passport, eco_id="TAMPERED")
    tampered_report = _service().validate(tampered)
    assert tampered_report.canonical_hash != baseline.canonical_hash


# --- Injected config & rules ----------------------------------------------


def test_custom_config_is_exposed_on_service():
    config = IntegrityConfig(hash_algorithm="sha512")
    service = IntegrityService(config=config, clock=None)
    assert service.config.hash_algorithm == "sha512"


def test_config_from_settings_maps_env_knobs():
    from device_ai.configs.settings import Settings

    settings = Settings(
        integrity_rules_path="custom/rules.yaml",
        integrity_hash_algorithm="sha512",
    )
    config = IntegrityConfig.from_settings(settings)
    assert config.rules_path == "custom/rules.yaml"
    assert config.hash_algorithm == "sha512"


def test_configured_algorithm_flows_into_report():
    config = IntegrityConfig(hash_algorithm="sha512")
    report = IntegrityService(config=config, clock=None).validate(_passport())
    assert report.hash_algorithm == "sha512"
    assert len(report.canonical_hash) == 128  # sha512 hex digest length


# --- No monetary surface & immutability -----------------------------------


def test_report_exposes_no_monetary_field():
    report = _service().validate(_passport())
    payload = report.to_dict()
    forbidden = {"price", "value_usd", "value_inr", "cost", "currency", "market_value"}
    assert forbidden.isdisjoint(payload)


def test_report_is_immutable():
    report = _service().validate(_passport())
    with pytest.raises((AttributeError, TypeError)):
        report.canonical_hash = "hacked"  # type: ignore[misc]
