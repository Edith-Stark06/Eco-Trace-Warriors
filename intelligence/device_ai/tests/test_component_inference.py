"""Tests for the component inference engine (milestone M1.9).

The inference engine is deterministic arithmetic over a resolved
:class:`ComponentProfile`, a fused :class:`DeviceContext` and a
:class:`RecoverabilityReport`, so these tests feed it a small hand-built profile
and hand-built inputs and assert the fold: catalogue-prior presence confidence,
identity/hazard corroboration bonuses, the min-presence floor, and the overall
confidence blend/damping. No shipped catalogue, no images, no models.
"""

from device_ai.components.config import ComponentConfig
from device_ai.components.inference import ComponentInferenceEngine
from device_ai.components.models import ComponentCategory
from device_ai.components.profiles import ComponentProfile, ComponentSpec
from device_ai.fusion.models import (
    Conflict,
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.recoverability.models import (
    HazardLevel,
    RecommendedAction,
    RecoverabilityReport,
)

_CONFIG = ComponentConfig()


def _context(*, device_type="laptop", signals=None, confidence=0.9, conflicts=()):
    attributes = [
        ResolvedAttribute(
            attribute=FusionAttribute.DEVICE_TYPE,
            value=device_type,
            confidence=confidence,
            sources=(EvidenceKind.DETECTION,),
        )
    ]
    for attribute, value in (signals or {}).items():
        attributes.append(
            ResolvedAttribute(
                attribute=attribute,
                value=value,
                confidence=confidence,
                sources=(EvidenceKind.OCR,),
            )
        )
    return DeviceContext(
        eco_id="ET-2026-0000ABCD",
        fingerprint="f" * 64,
        attributes=tuple(attributes),
        confidence=confidence,
        evidence=(),
        conflicts=tuple(conflicts),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _recoverability(*, hazard=HazardLevel.LOW, confidence=0.9):
    return RecoverabilityReport(
        device_type="laptop",
        repairability=0.8,
        reusability=0.8,
        recyclability=0.8,
        hazard_level=hazard,
        confidence=confidence,
        recommended_action=RecommendedAction.REFURBISH,
        reasoning=(),
        warnings=(),
    )


def _profile(*specs, device_type="laptop", known=True):
    return ComponentProfile(device_type=device_type, components=specs, known=known)


def _spec(name="Part", category=ComponentCategory.OTHER, likelihood=0.5, **kw):
    return ComponentSpec(name=name, category=category, base_likelihood=likelihood, **kw)


def _infer(profile, context, recoverability, config=_CONFIG):
    engine = ComponentInferenceEngine(config)
    return engine.infer(context, recoverability, profile)


# --- Presence confidence (catalogue prior) -------------------------------


def test_presence_confidence_starts_from_base_likelihood():
    report = _infer(
        _profile(_spec(likelihood=0.6)),
        _context(),
        _recoverability(hazard=HazardLevel.NONE),
    )
    assert report.components[0].presence_confidence == 0.6


def test_presence_confidence_is_clamped_and_rounded():
    report = _infer(
        _profile(_spec(likelihood=0.99, hazardous=True)),
        _context(),
        _recoverability(hazard=HazardLevel.HIGH),  # +hazard bonus pushes over 1
    )
    assert report.components[0].presence_confidence == 1.0


# --- Identity corroboration ----------------------------------------------


def test_identity_signal_boosts_implied_component():
    profile = _profile(_spec(likelihood=0.6, implied_by=("serial_number",)))
    without = _infer(profile, _context(), _recoverability(hazard=HazardLevel.NONE))
    with_serial = _infer(
        profile,
        _context(signals={FusionAttribute.SERIAL_NUMBER: "SN1"}),
        _recoverability(hazard=HazardLevel.NONE),
    )
    assert with_serial.components[0].presence_confidence > (
        without.components[0].presence_confidence
    )


def test_non_matching_identity_signal_does_not_boost():
    profile = _profile(_spec(likelihood=0.6, implied_by=("imei",)))
    report = _infer(
        profile,
        _context(signals={FusionAttribute.SERIAL_NUMBER: "SN1"}),  # not imei
        _recoverability(hazard=HazardLevel.NONE),
    )
    assert report.components[0].presence_confidence == 0.6


# --- Hazard corroboration -------------------------------------------------


def test_hazardous_component_boosted_when_device_hazard_present():
    profile = _profile(_spec(likelihood=0.6, hazardous=True))
    none = _infer(profile, _context(), _recoverability(hazard=HazardLevel.NONE))
    high = _infer(profile, _context(), _recoverability(hazard=HazardLevel.HIGH))
    assert high.components[0].presence_confidence > (
        none.components[0].presence_confidence
    )


def test_unknown_hazard_does_not_corroborate():
    # UNKNOWN hazard is "insufficient evidence", not a positive hazard signal.
    profile = _profile(_spec(likelihood=0.6, hazardous=True))
    report = _infer(profile, _context(), _recoverability(hazard=HazardLevel.UNKNOWN))
    assert report.components[0].presence_confidence == 0.6


# --- Min-presence floor ---------------------------------------------------


def test_components_at_or_below_floor_are_dropped():
    config = ComponentConfig(min_presence_confidence=0.5)
    report = _infer(
        _profile(
            _spec(name="Keep", likelihood=0.6), _spec(name="Drop", likelihood=0.5)
        ),
        _context(),
        _recoverability(hazard=HazardLevel.NONE),
        config=config,
    )
    names = [component.name for component in report.components]
    assert names == ["Keep"]


# --- Overall confidence ---------------------------------------------------


def test_overall_confidence_blends_recoverability():
    # weight 0.5 blends context 0.8 with recoverability 0.4 → 0.6.
    report = _infer(
        _profile(_spec()),
        _context(confidence=0.8),
        _recoverability(hazard=HazardLevel.NONE, confidence=0.4),
    )
    assert report.overall_confidence == 0.6


def test_unknown_device_type_damps_overall_confidence():
    known = _infer(
        _profile(_spec(), known=True),
        _context(confidence=0.9),
        _recoverability(hazard=HazardLevel.NONE, confidence=0.9),
    )
    unknown = _infer(
        _profile(_spec(), known=False, device_type="ghost"),
        _context(device_type="ghost", confidence=0.9),
        _recoverability(hazard=HazardLevel.NONE, confidence=0.9),
    )
    assert unknown.overall_confidence < known.overall_confidence


def test_conflicts_damp_overall_confidence():
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    clean = _infer(
        _profile(_spec()),
        _context(confidence=0.9),
        _recoverability(hazard=HazardLevel.NONE, confidence=0.9),
    )
    conflicted = _infer(
        _profile(_spec()),
        _context(confidence=0.9, conflicts=(conflict,)),
        _recoverability(hazard=HazardLevel.NONE, confidence=0.9),
    )
    assert conflicted.overall_confidence < clean.overall_confidence


# --- Reasoning & warnings -------------------------------------------------


def test_unknown_device_type_warns():
    report = _infer(
        _profile(_spec(), known=False, device_type="ghost"),
        _context(device_type="ghost"),
        _recoverability(hazard=HazardLevel.NONE),
    )
    assert any("Unrecognized" in w for w in report.warnings)


def test_conflict_warns():
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    report = _infer(
        _profile(_spec()),
        _context(conflicts=(conflict,)),
        _recoverability(hazard=HazardLevel.NONE),
    )
    assert any("conflict" in w.lower() for w in report.warnings)


def test_reasoning_is_populated_and_ordered():
    report = _infer(
        _profile(_spec(implied_by=("serial_number",))),
        _context(signals={FusionAttribute.SERIAL_NUMBER: "SN1"}),
        _recoverability(hazard=HazardLevel.NONE),
    )
    assert report.reasoning
    assert any("profile" in r.lower() for r in report.reasoning)
