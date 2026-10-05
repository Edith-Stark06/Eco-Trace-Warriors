"""End-to-end tests for the recoverability service (milestone M1.8).

Exercises :meth:`RecoverabilityService.assess` across the required scenarios —
a healthy identifiable device, a hazardous class, a conflicted context, a
low-confidence context, partial identity and an unknown device — plus
determinism, provenance carry-over, the injected clock and report immutability.
All contexts are hand-built (no fusion run, no models, no filesystem).
"""

from datetime import UTC, datetime

import pytest

from device_ai.fusion.models import (
    Conflict,
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.recoverability import (
    RECOVERABILITY_ENGINE_VERSION,
    HazardLevel,
    RecommendedAction,
    RecoverabilityReport,
    RecoverabilityService,
)

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _service(*, with_clock=False):
    return RecoverabilityService(clock=(lambda: _CLOCK) if with_clock else None)


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
    model="",
    serial="",
    imei="",
    confidence=0.9,
    conflicts=(),
    eco_id="ET-2026-0000ABCD",
):
    attributes = [_resolved(FusionAttribute.DEVICE_TYPE, device_type)]
    if model:
        attributes.append(_resolved(FusionAttribute.MODEL, model))
    if serial:
        attributes.append(_resolved(FusionAttribute.SERIAL_NUMBER, serial))
    if imei:
        attributes.append(_resolved(FusionAttribute.IMEI, imei))
    return DeviceContext(
        eco_id=eco_id,
        fingerprint="f" * 64,
        attributes=tuple(attributes),
        confidence=confidence,
        evidence=(),
        conflicts=tuple(conflicts),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


# --- Healthy, identifiable device ----------------------------------------


def test_assess_identifiable_laptop_recommends_reuse():
    context = _context(model="XPS-13", serial="SN123", confidence=0.9)
    report = _service().assess(context)
    assert isinstance(report, RecoverabilityReport)
    assert report.device_type == "laptop"
    assert report.recommended_action is RecommendedAction.REFURBISH
    # Battery-bearing class → at least MEDIUM hazard floor.
    assert report.hazard_level is HazardLevel.MEDIUM
    assert report.reasoning  # explanations are populated
    assert report.eco_id == "ET-2026-0000ABCD"


# --- Hazardous class ------------------------------------------------------


def test_assess_crt_forces_hazardous_disposal():
    report = _service().assess(_context(device_type="CRT monitor", confidence=0.9))
    assert report.hazard_level is HazardLevel.HIGH
    assert report.recommended_action is RecommendedAction.HAZARDOUS_DISPOSAL


def test_assess_standalone_battery_is_hazardous():
    report = _service().assess(_context(device_type="battery", confidence=0.9))
    assert report.recommended_action is RecommendedAction.HAZARDOUS_DISPOSAL


# --- Conflicted context ---------------------------------------------------


def test_assess_conflicted_context_damps_confidence_and_warns():
    clean = _service().assess(_context(model="XPS-13", confidence=0.9))
    conflict = Conflict(
        attribute=FusionAttribute.BRAND,
        resolved_value="Dell",
        claims=(),
    )
    conflicted = _service().assess(
        _context(model="XPS-13", confidence=0.9, conflicts=(conflict,))
    )
    assert conflicted.confidence < clean.confidence
    assert any("conflict" in w.lower() for w in conflicted.warnings)


# --- Low-confidence context ----------------------------------------------


def test_assess_low_confidence_forces_manual_review():
    report = _service().assess(_context(model="XPS-13", confidence=0.20))
    assert report.recommended_action is RecommendedAction.MANUAL_REVIEW
    assert any("review" in w.lower() for w in report.warnings)


# --- Partial identity -----------------------------------------------------


def test_assess_missing_identity_warns():
    report = _service().assess(_context(confidence=0.9))
    assert any("identity" in w.lower() for w in report.warnings)


# --- Unknown device -------------------------------------------------------


def test_assess_unknown_device_forces_manual_review():
    report = _service().assess(_context(device_type="teleporter", confidence=0.9))
    assert report.recommended_action is RecommendedAction.MANUAL_REVIEW
    assert report.hazard_level is HazardLevel.UNKNOWN
    assert any("unrecognized" in w.lower() for w in report.warnings)


# --- Determinism & provenance --------------------------------------------


def test_assess_is_deterministic_for_identical_input():
    context = _context(model="XPS-13", serial="SN123", confidence=0.9)
    first = _service().assess(context)
    second = _service().assess(context)
    assert first.to_dict() == second.to_dict()


def test_service_stamps_version_and_optional_clock():
    with_clock = _service(with_clock=True).assess(_context())
    assert with_clock.engine_version == RECOVERABILITY_ENGINE_VERSION
    assert with_clock.created_at == _CLOCK
    without_clock = _service().assess(_context())
    assert without_clock.created_at is None


def test_report_is_json_serializable_shape():
    report = _service(with_clock=True).assess(_context(model="XPS-13", serial="SN123"))
    payload = report.to_dict()
    assert payload["device_type"] == "laptop"
    assert payload["recommended_action"] == "refurbish"
    assert payload["hazard_level"] == "medium"
    assert payload["created_at"] == _CLOCK.isoformat()
    assert isinstance(payload["reasoning"], list)
    assert isinstance(payload["warnings"], list)


def test_report_is_immutable():
    report = _service().assess(_context())
    with pytest.raises((AttributeError, TypeError)):
        report.confidence = 1.0  # type: ignore[misc]


def test_custom_config_is_exposed_on_service():
    from device_ai.recoverability import RecoverabilityConfig

    config = RecoverabilityConfig(refurbish_min_reusability=0.99)
    service = RecoverabilityService(config=config)
    assert service.config.refurbish_min_reusability == 0.99
