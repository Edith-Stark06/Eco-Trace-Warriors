"""End-to-end tests for the trust & provenance service (milestone M2.5).

Exercises :meth:`TrustService.assess` by actually running the upstream engines
(recoverability, component, material, environmental, decision-knowledge,
circular), composing a real :class:`DevicePassport` via the passport service,
validating it via the integrity service, then scoring its trustworthiness. Only
the external catalogues/schema/rule-sets are read from disk; there is no fusion
run and no models.

Asserts the service loads the shipped catalogue once, scores a well-formed
passport into a valid trust report, is deterministic, honours the injected clock,
stamps provenance, exposes no monetary surface, and produces an immutable report —
mirroring the M2.4 integrity service test structure.
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
from device_ai.integrity import IntegrityService
from device_ai.materials import MaterialService
from device_ai.passport import PassportService
from device_ai.recoverability import RecoverabilityService
from device_ai.trust import (
    TRUST_ENGINE_VERSION,
    PassportTrustReport,
    TrustConfig,
    TrustLevel,
    TrustService,
)

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _service(*, with_clock=False, config=None, rules=None):
    return TrustService(
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


def _inputs(*, fingerprint=True):
    """Run the real upstream engines and return the four trust inputs."""
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
    passport = PassportService(clock=None).build(
        context, decision, materials, environmental, fp
    )
    integrity = IntegrityService(clock=None).validate(passport)
    return passport, integrity, knowledge, decision


def _assess(service=None, *, fingerprint=True):
    service = service or _service()
    passport, integrity, knowledge, decision = _inputs(fingerprint=fingerprint)
    return service.assess(passport, integrity, knowledge, decision)


# --- End-to-end scoring ----------------------------------------------------


def test_assess_well_formed_passport_returns_report():
    report = _assess()
    assert isinstance(report, PassportTrustReport)
    assert report.passport_id.startswith("ET-PP-")
    assert 0.0 <= report.trust_score <= 1.0
    assert report.trust_level in set(TrustLevel)
    assert report.axis_count == 4


def test_report_carries_four_axes_in_order():
    report = _assess()
    assert tuple(axis.name for axis in report.axes) == (
        "identity_confidence",
        "evidence_consistency",
        "decision_confidence",
        "integrity_confidence",
    )


def test_report_axis_values_normalized():
    report = _assess()
    for axis in report.axes:
        assert 0.0 <= axis.value <= 1.0
        assert axis.weight >= 0.0
        assert axis.reason


def test_well_formed_passport_scores_reasonably():
    # A well-identified, valid, agreeing device should not be untrusted.
    report = _assess()
    assert report.trust_level is not TrustLevel.UNTRUSTED
    assert report.trust_score > 0.4


def test_service_loads_shipped_catalogue_by_default():
    service = _service()
    assert service.rules.version
    assert service.rules.level_count == 4


# --- Provenance & clock ----------------------------------------------------


def test_service_stamps_versions_and_optional_clock():
    with_clock = _assess(_service(with_clock=True))
    assert with_clock.engine_version == TRUST_ENGINE_VERSION
    assert with_clock.rules_version == _service().rules.version
    assert with_clock.created_at == _CLOCK
    without_clock = _assess(_service())
    assert without_clock.created_at is None


# --- Determinism -----------------------------------------------------------


def test_assess_is_deterministic_for_identical_inputs():
    passport, integrity, knowledge, decision = _inputs()
    service = _service()
    first = service.assess(passport, integrity, knowledge, decision)
    second = service.assess(passport, integrity, knowledge, decision)
    assert first.to_json() == second.to_json()


def test_score_stable_across_service_instances():
    passport, integrity, knowledge, decision = _inputs()
    first = _service().assess(passport, integrity, knowledge, decision)
    second = _service().assess(passport, integrity, knowledge, decision)
    assert first.trust_score == second.trust_score
    assert first.trust_level == second.trust_level


# --- Injected config & rules ----------------------------------------------


def test_custom_config_is_exposed_on_service():
    config = TrustConfig(min_trust_score=0.6)
    service = TrustService(config=config, clock=None)
    assert service.config.min_trust_score == 0.6


def test_config_from_settings_maps_env_knobs():
    from device_ai.configs.settings import Settings

    settings = Settings(
        trust_rules_path="custom/rules.yaml",
        trust_min_score=0.55,
    )
    config = TrustConfig.from_settings(settings)
    assert config.rules_path == "custom/rules.yaml"
    assert config.min_trust_score == 0.55


def test_higher_floor_flags_low_trust_warning():
    # A floor of 1.0 makes every real score "low-trust", so a warning appears.
    config = TrustConfig(min_trust_score=1.0)
    report = _assess(TrustService(config=config, clock=None))
    assert any("low-trust" in warning for warning in report.warnings)


# --- No monetary surface & immutability -----------------------------------


def test_report_exposes_no_monetary_field():
    report = _assess()
    payload = report.to_dict()
    forbidden = {"price", "value_usd", "value_inr", "cost", "currency", "market_value"}
    assert forbidden.isdisjoint(payload)


def test_report_is_immutable():
    report = _assess()
    with pytest.raises((AttributeError, TypeError)):
        report.trust_score = 1.0  # type: ignore[misc]


def test_report_json_round_trips_keys():
    import json

    report = _assess()
    payload = json.loads(report.to_json())
    assert payload["passport_id"] == report.passport_id
    assert payload["trust_level"] == report.trust_level.value
    assert payload["axis_count"] == 4
    assert len(payload["axes"]) == 4
