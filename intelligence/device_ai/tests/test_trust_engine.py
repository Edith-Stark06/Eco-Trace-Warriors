"""Unit tests for the trust & provenance engine (milestone M2.5).

Exercises :meth:`TrustEngine.evaluate` against hand-built upstream reports and a
hand-built trust catalogue, isolating each of the four projection axes (identity
confidence, evidence consistency, decision confidence, integrity confidence), the
weighted-average score, the level mapping and the ordered reasoning/warnings.
There is no service, no disk I/O and no upstream engine run here — the engine is
tested as a pure function of its inputs.
"""

import pytest

from device_ai.circular.models import (
    DecisionReport,
    Priority,
    RecommendedAction,
)
from device_ai.decision.models import DecisionKnowledgeReport
from device_ai.integrity.models import PassportIntegrityReport, ValidationStatus
from device_ai.passport.models import (
    Classification,
    ConfidenceSummary,
    DecisionSummary,
    DeviceIdentity,
    DevicePassport,
    EnvironmentalSummary,
    FingerprintSummary,
    MaterialSummary,
    PassportMetadata,
)
from device_ai.trust.config import TrustConfig
from device_ai.trust.engine import TrustEngine
from device_ai.trust.models import PassportTrustReport, TrustLevel
from device_ai.trust.rules import AxisWeight, TrustLevelRule, TrustRuleSet

# --- Fixtures --------------------------------------------------------------


def _rules(*, weights=None):
    """Build a trust catalogue with equal weights and the shipped thresholds."""
    if weights is None:
        weights = (0.25, 0.25, 0.25, 0.25)
    axes = (
        "identity_confidence",
        "evidence_consistency",
        "decision_confidence",
        "integrity_confidence",
    )
    return TrustRuleSet(
        version="test-1.0",
        weights=tuple(
            AxisWeight(axis=axis, weight=weight)
            for axis, weight in zip(axes, weights, strict=True)
        ),
        levels=(
            TrustLevelRule(level=TrustLevel.HIGH, min_score=0.75),
            TrustLevelRule(level=TrustLevel.MEDIUM, min_score=0.5),
            TrustLevelRule(level=TrustLevel.LOW, min_score=0.25),
            TrustLevelRule(level=TrustLevel.UNTRUSTED, min_score=0.0),
        ),
    )


def _passport(
    *,
    device_type="laptop",
    classification_confidence=0.9,
    has_conflicts=False,
    model="XPS-13",
    serial="SN123",
    imei="356789",
    mac="AA:BB:CC:DD",
    warnings=(),
):
    return DevicePassport(
        passport_id="ET-PP-ABC123DEF456",
        passport_version="1.0.0",
        eco_id="ET-2026-0000ABCD",
        device_identity=DeviceIdentity(
            brand="Dell",
            model=model,
            serial_number=serial,
            imei=imei,
            mac_address=mac,
        ),
        classification=Classification(
            device_type=device_type,
            confidence=classification_confidence,
            has_conflicts=has_conflicts,
        ),
        decision_summary=DecisionSummary(
            recommended_action="refurbish",
            priority="high",
            confidence=0.8,
            winning_rule_id="r1",
            triggered_count=1,
        ),
        material_summary=MaterialSummary(
            material_count=3,
            total_mass_g=100.0,
            recoverable_mass_g=80.0,
            hazardous_mass_g=5.0,
            confidence=0.7,
        ),
        environmental_summary=EnvironmentalSummary(
            carbon_saved_kg=1.0,
            energy_saved_mj=2.0,
            water_saved_l=3.0,
            landfill_diversion_kg=0.1,
            critical_material_recovery_kg=0.01,
            circularity_index=0.6,
            hazard_reduction_score=0.5,
            confidence=0.7,
        ),
        fingerprint_summary=FingerprintSummary(
            fingerprint="a" * 64,
            dimension=128,
            encoder_name="CLIP",
            encoder_version="1.0",
            metric="cosine",
        ),
        confidence_summary=ConfidenceSummary(
            identity_confidence=0.9,
            decision_confidence=0.8,
            material_confidence=0.7,
            environmental_confidence=0.7,
            overall=0.775,
        ),
        metadata=PassportMetadata(
            passport_engine_version="1.0.0",
            schema_version="1.0.0",
            fusion_engine_version="1",
            decision_engine_version="1",
            decision_rules_version="1",
            material_engine_version="1",
            material_profile_version="1",
            environmental_engine_version="1",
            environmental_factors_version="1",
            source_image_count=2,
        ),
        reasoning=("assembled",),
        warnings=warnings,
    )


def _integrity(*, status=ValidationStatus.VALID, warnings=()):
    return PassportIntegrityReport(
        passport_id="ET-PP-ABC123DEF456",
        status=status,
        canonical_hash="h" * 64,
        hash_algorithm="sha256",
        schema_version="1.0.0",
        passport_version="1.0.0",
        checked_sections=(),
        warnings=warnings,
        errors=(),
    )


def _knowledge(*, device_type="laptop", overall_confidence=0.85):
    return DecisionKnowledgeReport(
        device_type=device_type,
        repairability_score=0.7,
        reusability_score=0.6,
        recycling_score=0.8,
        hazard_score=0.2,
        environmental_priority=0.5,
        material_value_score=0.6,
        overall_confidence=overall_confidence,
        dimensions=(),
        reasoning=(),
        warnings=(),
    )


def _decision(*, device_type="laptop", confidence=0.8):
    return DecisionReport(
        device_type=device_type,
        recommended_action=RecommendedAction.REFURBISH,
        priority=Priority.HIGH,
        confidence=confidence,
        triggered_rules=(),
        reasoning=(),
        warnings=(),
    )


def _evaluate(engine=None, **overrides):
    engine = engine or TrustEngine(TrustConfig())
    passport = overrides.get("passport", _passport())
    integrity = overrides.get("integrity", _integrity())
    knowledge = overrides.get("knowledge", _knowledge())
    decision = overrides.get("decision", _decision())
    rules = overrides.get("rules", _rules())
    return engine.evaluate(
        passport,
        integrity,
        knowledge,
        decision,
        rules,
        rules_version=rules.version,
        engine_version="test-engine",
    )


# --- Happy path ------------------------------------------------------------


def test_evaluate_returns_report():
    report = _evaluate()
    assert isinstance(report, PassportTrustReport)
    assert report.passport_id == "ET-PP-ABC123DEF456"
    assert report.axis_count == 4
    assert report.engine_version == "test-engine"
    assert report.rules_version == "test-1.0"
    assert report.created_at is None


def test_fully_trustworthy_device_is_high():
    report = _evaluate()
    # identity 0.95, evidence 1.0, decision 0.825, integrity 1.0 -> 0.94375
    assert report.trust_level is TrustLevel.HIGH
    assert report.trust_score >= 0.75


def test_axes_emitted_in_canonical_order():
    report = _evaluate()
    assert tuple(axis.name for axis in report.axes) == (
        "identity_confidence",
        "evidence_consistency",
        "decision_confidence",
        "integrity_confidence",
    )


def test_axis_values_match_report_fields():
    report = _evaluate()
    by_name = {axis.name: axis.value for axis in report.axes}
    assert by_name["identity_confidence"] == report.identity_confidence
    assert by_name["evidence_consistency"] == report.evidence_consistency
    assert by_name["decision_confidence"] == report.decision_confidence
    assert by_name["integrity_confidence"] == report.integrity_confidence


# --- Identity confidence axis ---------------------------------------------


def test_identity_confidence_full_when_all_fields_present():
    # All four strong fields present -> completeness 1.0; classification 1.0.
    passport = _passport(classification_confidence=1.0)
    report = _evaluate(passport=passport)
    assert report.identity_confidence == 1.0


def test_identity_confidence_drops_with_missing_fields():
    # No strong identity fields -> completeness 0.0; classification 0.6.
    passport = _passport(
        model="", serial="", imei="", mac="", classification_confidence=0.6
    )
    report = _evaluate(passport=passport)
    # (0.0 + 0.6) / 2 = 0.3
    assert report.identity_confidence == pytest.approx(0.3)


def test_identity_confidence_half_fields():
    # Two of four strong fields -> completeness 0.5; classification 0.5.
    passport = _passport(imei="", mac="", classification_confidence=0.5)
    report = _evaluate(passport=passport)
    # (0.5 + 0.5) / 2 = 0.5
    assert report.identity_confidence == pytest.approx(0.5)


# --- Evidence consistency axis --------------------------------------------


def test_evidence_consistency_full_when_all_agree():
    report = _evaluate()
    assert report.evidence_consistency == 1.0


def test_evidence_consistency_damped_by_conflict_flag():
    passport = _passport(has_conflicts=True)
    report = _evaluate(passport=passport)
    assert report.evidence_consistency == pytest.approx(0.8)


def test_evidence_consistency_low_when_types_disagree():
    report = _evaluate(
        passport=_passport(device_type="laptop"),
        knowledge=_knowledge(device_type="smartphone"),
        decision=_decision(device_type="laptop"),
    )
    assert report.evidence_consistency == pytest.approx(0.4)


def test_evidence_consistency_lowest_when_disagree_and_conflict():
    report = _evaluate(
        passport=_passport(device_type="laptop", has_conflicts=True),
        knowledge=_knowledge(device_type="tablet"),
        decision=_decision(device_type="laptop"),
    )
    assert report.evidence_consistency == pytest.approx(0.2)


def test_evidence_consistency_undefined_when_no_types():
    report = _evaluate(
        passport=_passport(device_type=""),
        knowledge=_knowledge(device_type=""),
        decision=_decision(device_type=""),
    )
    assert report.evidence_consistency == pytest.approx(0.5)


# --- Decision confidence axis ---------------------------------------------


def test_decision_confidence_is_mean_of_two_confidences():
    report = _evaluate(
        knowledge=_knowledge(overall_confidence=0.9),
        decision=_decision(confidence=0.7),
    )
    assert report.decision_confidence == pytest.approx(0.8)


# --- Integrity confidence axis --------------------------------------------


def test_integrity_confidence_full_when_valid():
    report = _evaluate(integrity=_integrity(status=ValidationStatus.VALID))
    assert report.integrity_confidence == 1.0


def test_integrity_confidence_zero_when_invalid():
    report = _evaluate(integrity=_integrity(status=ValidationStatus.INVALID))
    assert report.integrity_confidence == 0.0


def test_integrity_confidence_damped_by_warnings():
    integrity = _integrity(
        status=ValidationStatus.VALID_WITH_WARNINGS,
        warnings=("a soft caution", "another caution"),
    )
    report = _evaluate(integrity=integrity)
    # default penalty 0.1 per warning * 2 = 0.2 -> 0.8
    assert report.integrity_confidence == pytest.approx(0.8)


# --- Scoring & level mapping ----------------------------------------------


def test_score_is_weighted_average():
    # Weights all 0.25 -> plain mean of the four axes.
    report = _evaluate()
    expected = (
        report.identity_confidence
        + report.evidence_consistency
        + report.decision_confidence
        + report.integrity_confidence
    ) / 4.0
    assert report.trust_score == pytest.approx(expected)


def test_weights_bias_the_score():
    # Put all weight on integrity (which is 1.0) -> score approaches 1.0.
    rules = _rules(weights=(0.0, 0.0, 0.0, 1.0))
    report = _evaluate(rules=rules)
    assert report.trust_score == pytest.approx(1.0)


def test_invalid_passport_drives_untrusted():
    # Invalid integrity zeroes one axis and pulls the score down.
    rules = _rules(weights=(0.0, 0.0, 0.0, 1.0))
    report = _evaluate(
        rules=rules, integrity=_integrity(status=ValidationStatus.INVALID)
    )
    assert report.trust_score == 0.0
    assert report.trust_level is TrustLevel.UNTRUSTED


def test_score_is_clamped_and_rounded():
    report = _evaluate()
    assert 0.0 <= report.trust_score <= 1.0
    # Rounded to 6 decimal places.
    assert report.trust_score == round(report.trust_score, 6)


# --- Reasoning & warnings --------------------------------------------------


def test_reasoning_leads_with_level_and_covers_every_axis():
    report = _evaluate()
    assert report.trust_level.value in report.reasoning[0]
    # One reasoning line per axis, plus the two summary lines.
    assert len(report.reasoning) == 6
    for axis in report.axes:
        assert any(axis.name in line for line in report.reasoning)


def test_low_trust_warning_emitted_below_floor():
    # All-weight-on-integrity + invalid -> score 0.0, below the 0.4 floor.
    rules = _rules(weights=(0.0, 0.0, 0.0, 1.0))
    report = _evaluate(
        rules=rules, integrity=_integrity(status=ValidationStatus.INVALID)
    )
    assert any("low-trust" in warning for warning in report.warnings)


def test_invalid_integrity_warns():
    report = _evaluate(integrity=_integrity(status=ValidationStatus.INVALID))
    assert any("integrity validation" in warning for warning in report.warnings)


def test_integrity_warnings_surface():
    integrity = _integrity(status=ValidationStatus.VALID_WITH_WARNINGS, warnings=("x",))
    report = _evaluate(integrity=integrity)
    assert any("integrity report carries" in warning for warning in report.warnings)


def test_passport_warnings_surface():
    passport = _passport(warnings=("passport caution",))
    report = _evaluate(passport=passport)
    assert any("Passport itself carries" in warning for warning in report.warnings)


def test_clean_passport_has_no_warnings():
    report = _evaluate()
    assert report.warnings == ()


# --- Determinism -----------------------------------------------------------


def test_evaluate_is_deterministic():
    first = _evaluate()
    second = _evaluate()
    assert first.to_json() == second.to_json()


def test_identity_field_count_zero_yields_zero_completeness():
    engine = TrustEngine(TrustConfig(identity_field_count=0))
    report = _evaluate(engine=engine, passport=_passport(classification_confidence=0.0))
    assert report.identity_confidence == 0.0
