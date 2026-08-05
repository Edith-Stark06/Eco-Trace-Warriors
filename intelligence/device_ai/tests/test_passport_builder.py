"""Unit tests for the deterministic passport builder (milestone M2.3).

Exercises :meth:`PassportBuilder.build` against hand-built upstream reports (no
engine runs, no I/O), asserting the builder is a *pure composition*: every value
on the passport is copied or plainly summarized from an input, the composed
confidence is the plain arithmetic mean of the four upstream confidences, the
passport id is a deterministic content-addressed hash, and the same inputs always
yield byte-identical output. The builder must derive no new score.
"""

from datetime import UTC, datetime

from device_ai.circular.models import (
    DecisionReport,
    Priority,
    RecommendedAction,
    TriggeredRule,
)
from device_ai.environmental.models import EnvironmentalImpactReport
from device_ai.fingerprint.models import DeviceFingerprint
from device_ai.fusion.models import (
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.materials.models import (
    MaterialCategory,
    MaterialReport,
    RecoveredMaterial,
)
from device_ai.passport.builder import PassportBuilder
from device_ai.passport.config import PassportConfig
from device_ai.passport.models import DevicePassport

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


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
    brand="Dell",
    model="XPS-13",
    serial="SN123",
    confidence=0.9,
    conflicts=(),
    eco_id="ET-2026-0000ABCD",
    fingerprint="f" * 64,
):
    attributes = [
        _resolved(FusionAttribute.DEVICE_TYPE, device_type),
        _resolved(FusionAttribute.BRAND, brand),
        _resolved(FusionAttribute.MODEL, model),
        _resolved(FusionAttribute.SERIAL_NUMBER, serial),
    ]
    return DeviceContext(
        eco_id=eco_id,
        fingerprint=fingerprint,
        attributes=tuple(attributes),
        confidence=confidence,
        evidence=(),
        conflicts=tuple(conflicts),
        source_hashes=("a" * 64, "b" * 64),
        engine_version="fusion-1.0",
    )


def _decision(
    *,
    action=RecommendedAction.REFURBISH,
    priority=Priority.MEDIUM,
    confidence=0.85,
    with_winner=True,
):
    rules = (
        (
            TriggeredRule(
                rule_id="refurbish_high_value",
                action=action,
                priority=priority,
                precedence=1,
                reason="high recovery value",
                won=True,
            ),
        )
        if with_winner
        else ()
    )
    return DecisionReport(
        device_type="laptop",
        recommended_action=action,
        priority=priority,
        confidence=confidence,
        triggered_rules=rules,
        reasoning=("The device is a repairable laptop.",),
        warnings=("Battery health unknown.",),
        eco_id="ET-2026-0000ABCD",
        engine_version="circular-1.0",
        rules_version="rules-1.0",
    )


def _materials(*, confidence=0.8):
    material = RecoveredMaterial(
        name="Aluminium chassis",
        category=MaterialCategory.NON_FERROUS_METAL,
        mass_g=800.0,
        confidence=0.9,
        recoverable=True,
        hazardous=False,
        source_components=("chassis",),
        reason="structural aluminium",
    )
    return MaterialReport(
        device_type="laptop",
        materials=(material,),
        total_mass_g=1200.0,
        recoverable_mass_g=1000.0,
        hazardous_mass_g=50.0,
        overall_confidence=confidence,
        reasoning=("Derived from a familiar laptop profile.",),
        warnings=("Mass estimates are nominal.",),
        eco_id="ET-2026-0000ABCD",
        engine_version="material-1.0",
        profile_version="profiles-1.0",
    )


def _environmental(*, confidence=0.75):
    return EnvironmentalImpactReport(
        device_type="laptop",
        contributions=(),
        carbon_saved_kg=12.5,
        energy_saved_mj=300.0,
        water_saved_l=150.0,
        landfill_diversion_kg=1.0,
        critical_material_recovery_kg=0.05,
        circularity_index=0.7,
        hazard_reduction_score=0.6,
        confidence=confidence,
        reasoning=("Avoided burden from recovering aluminium.",),
        warnings=("Factors are regional averages.",),
        eco_id="ET-2026-0000ABCD",
        engine_version="environmental-1.0",
        factors_version="factors-1.0",
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


def _builder(config=None):
    return PassportBuilder(config or PassportConfig())


def _build(*, fingerprint=True, created_at=None, **kwargs):
    return _builder().build(
        _context(**kwargs),
        _decision(),
        _materials(),
        _environmental(),
        _fingerprint() if fingerprint else None,
        schema_version="1.0.0",
        passport_version="1.0.0",
        engine_version="passport-1.0",
        created_at=created_at,
    )


# --- Composition: identity & classification -------------------------------


def test_build_returns_device_passport():
    passport = _build()
    assert isinstance(passport, DevicePassport)


def test_identity_copied_verbatim_from_context():
    passport = _build()
    assert passport.device_identity.brand == "Dell"
    assert passport.device_identity.model == "XPS-13"
    assert passport.device_identity.serial_number == "SN123"


def test_classification_copies_device_type_and_conflict_flag():
    passport = _build()
    assert passport.classification.device_type == "laptop"
    assert passport.classification.has_conflicts is False
    assert 0.0 <= passport.classification.confidence <= 1.0


def test_eco_id_carried_from_context():
    passport = _build(eco_id="ET-2026-DEADBEEF")
    assert passport.eco_id == "ET-2026-DEADBEEF"


# --- Composition: decision, material, environmental -----------------------


def test_decision_summary_copies_recommendation():
    passport = _build()
    assert passport.decision_summary.recommended_action == "refurbish"
    assert passport.decision_summary.priority == "medium"
    assert passport.decision_summary.winning_rule_id == "refurbish_high_value"
    assert passport.decision_summary.triggered_count == 1


def test_decision_summary_empty_winner_when_fallback_applies():
    passport = _builder().build(
        _context(),
        _decision(with_winner=False),
        _materials(),
        _environmental(),
        _fingerprint(),
    )
    assert passport.decision_summary.winning_rule_id == ""
    assert passport.decision_summary.triggered_count == 0


def test_material_summary_copies_totals():
    passport = _build()
    assert passport.material_summary.material_count == 1
    assert passport.material_summary.total_mass_g == 1200.0
    assert passport.material_summary.recoverable_mass_g == 1000.0
    assert passport.material_summary.hazardous_mass_g == 50.0


def test_environmental_summary_copies_headline_metrics():
    passport = _build()
    env = passport.environmental_summary
    assert env.carbon_saved_kg == 12.5
    assert env.energy_saved_mj == 300.0
    assert env.circularity_index == 0.7
    assert env.hazard_reduction_score == 0.6


# --- Composition: fingerprint ---------------------------------------------


def test_fingerprint_summary_copies_anchor():
    passport = _build()
    assert passport.fingerprint_summary.fingerprint == "f" * 64
    assert passport.fingerprint_summary.dimension == 3
    assert passport.fingerprint_summary.encoder_name == "CLIP"


def test_missing_fingerprint_yields_empty_section_and_warning():
    passport = _build(fingerprint=False)
    assert passport.fingerprint_summary.fingerprint == ""
    assert passport.fingerprint_summary.dimension == 0
    assert any("fingerprint" in warning.lower() for warning in passport.warnings)


# --- Composition: confidence is a plain mean, not a new inference ----------


def test_overall_confidence_is_arithmetic_mean():
    passport = _build()
    summary = passport.confidence_summary
    expected = (0.9 + 0.85 + 0.8 + 0.75) / 4
    assert summary.identity_confidence == 0.9
    assert summary.decision_confidence == 0.85
    assert summary.material_confidence == 0.8
    assert summary.environmental_confidence == 0.75
    assert abs(summary.overall - expected) < 1e-9


def test_overall_confidence_in_unit_interval():
    passport = _build()
    assert 0.0 <= passport.confidence_summary.overall <= 1.0


# --- Passport id: deterministic and content-addressed ---------------------


def test_passport_id_has_prefix_and_fixed_length():
    passport = _build()
    assert passport.passport_id.startswith("ET-PP-")
    assert len(passport.passport_id) == len("ET-PP-") + 12


def test_passport_id_is_deterministic_for_same_device():
    first = _build()
    second = _build()
    assert first.passport_id == second.passport_id


def test_passport_id_changes_with_device_identity():
    baseline = _build(serial="SN123")
    other = _build(serial="SN999")
    assert baseline.passport_id != other.passport_id


def test_passport_id_ignores_timestamp():
    with_time = _build(created_at=_CLOCK)
    without_time = _build(created_at=None)
    assert with_time.passport_id == without_time.passport_id


# --- Metadata: provenance carry-over --------------------------------------


def test_metadata_gathers_every_engine_version():
    passport = _build(created_at=_CLOCK)
    meta = passport.metadata
    assert meta.passport_engine_version == "passport-1.0"
    assert meta.schema_version == "1.0.0"
    assert meta.fusion_engine_version == "fusion-1.0"
    assert meta.decision_engine_version == "circular-1.0"
    assert meta.decision_rules_version == "rules-1.0"
    assert meta.material_engine_version == "material-1.0"
    assert meta.material_profile_version == "profiles-1.0"
    assert meta.environmental_engine_version == "environmental-1.0"
    assert meta.environmental_factors_version == "factors-1.0"
    assert meta.source_image_count == 2
    assert meta.created_at == _CLOCK


def test_passport_version_falls_back_to_config():
    passport = _builder(PassportConfig(passport_version="9.9.9")).build(
        _context(),
        _decision(),
        _materials(),
        _environmental(),
        _fingerprint(),
    )
    assert passport.passport_version == "9.9.9"


# --- Narrative: composed reasoning & warnings -----------------------------


def test_reasoning_leads_with_passport_summary_then_decision():
    passport = _build()
    assert passport.reasoning[0].startswith("Passport composed for laptop")
    assert "The device is a repairable laptop." in passport.reasoning


def test_warnings_union_deduplicated():
    passport = _build()
    # The decision, material and environmental warnings all appear.
    assert "Battery health unknown." in passport.warnings
    assert "Mass estimates are nominal." in passport.warnings
    assert "Factors are regional averages." in passport.warnings
    # No duplicates.
    assert len(passport.warnings) == len(set(passport.warnings))


def test_reasoning_capped_by_config():
    config = PassportConfig(max_reasoning=1)
    passport = _builder(config).build(
        _context(),
        _decision(),
        _materials(),
        _environmental(),
        _fingerprint(),
    )
    assert passport.reasoning_count == 1


def test_warnings_capped_by_config():
    config = PassportConfig(max_warnings=1)
    passport = _builder(config).build(
        _context(),
        _decision(),
        _materials(),
        _environmental(),
        _fingerprint(),
    )
    assert passport.warning_count == 1


# --- Determinism & serialization ------------------------------------------


def test_build_is_deterministic_json():
    first = _build(created_at=_CLOCK)
    second = _build(created_at=_CLOCK)
    assert first.to_json() == second.to_json()


def test_to_json_is_canonical_sorted():
    passport = _build()
    payload = passport.to_json()
    # Canonical form sorts keys, so passport_id key precedes passport_version.
    assert '"classification"' in payload
    # Compact separators (no spaces after commas/colons by default).
    assert ", " not in payload


def test_passport_exposes_no_monetary_field():
    passport = _build()
    payload = passport.to_dict()
    forbidden = {"price", "value_usd", "value_inr", "cost", "currency", "market_value"}
    assert forbidden.isdisjoint(payload)


def test_passport_is_immutable():
    import pytest

    passport = _build()
    with pytest.raises((AttributeError, TypeError)):
        passport.passport_id = "hacked"  # type: ignore[misc]
