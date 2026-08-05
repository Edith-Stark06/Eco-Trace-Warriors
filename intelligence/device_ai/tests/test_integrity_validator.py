"""Unit tests for the passport integrity validator (milestone M2.4).

Exercises :meth:`PassportIntegrityValidator.validate` against hand-built
:class:`DevicePassport` documents and hand-built rule-sets: the happy path (valid,
hashed), the three verdict states (valid / valid-with-warnings / invalid), every
structural-error kind (missing required section, wrong kind, missing object field,
out-of-range confidence), the optional-section warning, hash determinism and
tamper-detection, and the unsupported-algorithm engine fault. No pipeline, no
models, no disk — the validator is tested in isolation.
"""

import dataclasses

import pytest

from device_ai.exceptions import PassportIntegrityError
from device_ai.integrity.config import IntegrityConfig
from device_ai.integrity.models import PassportIntegrityReport, ValidationStatus
from device_ai.integrity.rules import IntegrityRuleSet, SectionKind, SectionRule
from device_ai.integrity.validator import PassportIntegrityValidator
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


def _passport(**overrides) -> DevicePassport:
    """Return a minimal, structurally-conformant passport for validation."""
    base = {
        "passport_id": "ET-PP-AABBCCDDEEFF",
        "passport_version": "1.0.0",
        "eco_id": "ET-2026-00000001",
        "device_identity": DeviceIdentity(
            brand="Dell",
            model="XPS-13",
            serial_number="SN123",
            imei="",
            mac_address="",
        ),
        "classification": Classification(
            device_type="laptop", confidence=0.9, has_conflicts=False
        ),
        "decision_summary": DecisionSummary(
            recommended_action="refurbish",
            priority="medium",
            confidence=0.85,
            winning_rule_id="rule_1",
            triggered_count=1,
        ),
        "material_summary": MaterialSummary(
            material_count=5,
            total_mass_g=1200.0,
            recoverable_mass_g=1000.0,
            hazardous_mass_g=50.0,
            confidence=0.8,
        ),
        "environmental_summary": EnvironmentalSummary(
            carbon_saved_kg=12.5,
            energy_saved_mj=300.0,
            water_saved_l=150.0,
            landfill_diversion_kg=1.0,
            critical_material_recovery_kg=0.05,
            circularity_index=0.7,
            hazard_reduction_score=0.6,
            confidence=0.75,
        ),
        "fingerprint_summary": FingerprintSummary(
            fingerprint="f" * 64,
            dimension=512,
            encoder_name="CLIP",
            encoder_version="1.0",
            metric="cosine",
        ),
        "confidence_summary": ConfidenceSummary(
            identity_confidence=0.9,
            decision_confidence=0.85,
            material_confidence=0.8,
            environmental_confidence=0.75,
            overall=0.825,
        ),
        "metadata": PassportMetadata(
            passport_engine_version="1.0.0",
            schema_version="1.0.0",
            fusion_engine_version="1.0.0",
            decision_engine_version="1.0.0",
            decision_rules_version="1.0.0",
            material_engine_version="1.0.0",
            material_profile_version="1.0.0",
            environmental_engine_version="1.0.0",
            environmental_factors_version="1.0.0",
            source_image_count=1,
            created_at=None,
        ),
        "reasoning": ("Reason one", "Reason two"),
        "warnings": ("Warning one",),
    }
    base.update(overrides)
    return DevicePassport(**base)


def _rules() -> IntegrityRuleSet:
    """Return a small rule-set: one string, one object with a confidence field."""
    return IntegrityRuleSet(
        version="1.0",
        sections=(
            SectionRule(name="passport_id", kind=SectionKind.STRING),
            SectionRule(
                name="classification",
                kind=SectionKind.OBJECT,
                fields=("device_type", "confidence", "has_conflicts"),
                confidence_fields=("confidence",),
            ),
            SectionRule(name="reasoning", kind=SectionKind.ARRAY),
        ),
    )


def _validator(*, algorithm="sha256") -> PassportIntegrityValidator:
    return PassportIntegrityValidator(IntegrityConfig(hash_algorithm=algorithm))


# --- Happy path -----------------------------------------------------------


def test_validate_conformant_passport_is_valid():
    report = _validator().validate(_passport(), _rules())
    assert isinstance(report, PassportIntegrityReport)
    assert report.status is ValidationStatus.VALID
    assert report.is_valid is True
    assert report.error_count == 0
    assert report.warning_count == 0


def test_validate_records_one_checked_section_per_rule():
    report = _validator().validate(_passport(), _rules())
    assert report.checked_count == 3
    names = [section.name for section in report.checked_sections]
    assert names == ["passport_id", "classification", "reasoning"]
    assert all(section.present for section in report.checked_sections)
    assert all(section.valid for section in report.checked_sections)


def test_validate_stamps_observed_versions():
    report = _validator().validate(
        _passport(), _rules(), rules_version="1.0", engine_version="9.9"
    )
    assert report.schema_version == "1.0.0"
    assert report.passport_version == "1.0.0"
    assert report.rules_version == "1.0"
    assert report.engine_version == "9.9"
    assert report.passport_id == "ET-PP-AABBCCDDEEFF"


# --- Integrity hash -------------------------------------------------------


def test_hash_is_sha256_hex_of_fixed_length():
    report = _validator().validate(_passport(), _rules())
    assert report.hash_algorithm == "sha256"
    assert len(report.canonical_hash) == 64
    assert all(char in "0123456789abcdef" for char in report.canonical_hash)


def test_hash_is_deterministic_for_identical_passport():
    first = _validator().validate(_passport(), _rules())
    second = _validator().validate(_passport(), _rules())
    assert first.canonical_hash == second.canonical_hash


def test_hash_changes_when_passport_mutated():
    report = _validator().validate(_passport(), _rules())
    tampered = dataclasses.replace(_passport(), eco_id="HACKED")
    tampered_report = _validator().validate(tampered, _rules())
    assert tampered_report.canonical_hash != report.canonical_hash


def test_hash_present_even_for_invalid_passport():
    payload = _passport()
    broken = dataclasses.replace(
        payload,
        classification=Classification(
            device_type="laptop", confidence=1.5, has_conflicts=False
        ),
    )
    report = _validator().validate(broken, _rules())
    assert report.status is ValidationStatus.INVALID
    assert len(report.canonical_hash) == 64


def test_unsupported_algorithm_raises_engine_error():
    with pytest.raises(PassportIntegrityError, match="Unsupported integrity hash"):
        _validator(algorithm="not-a-real-algorithm").validate(_passport(), _rules())


# --- Verdict states -------------------------------------------------------


def test_missing_required_section_is_invalid():
    rules = IntegrityRuleSet(
        version="1.0",
        sections=(SectionRule(name="not_a_section", kind=SectionKind.STRING),),
    )
    report = _validator().validate(_passport(), rules)
    assert report.status is ValidationStatus.INVALID
    assert report.is_valid is False
    assert any("missing required section" in error for error in report.errors)
    checked = report.checked_sections[0]
    assert checked.present is False
    assert checked.valid is False


def test_missing_optional_section_is_valid_with_warnings():
    rules = IntegrityRuleSet(
        version="1.0",
        sections=(
            SectionRule(name="passport_id", kind=SectionKind.STRING),
            SectionRule(name="not_a_section", kind=SectionKind.STRING, required=False),
        ),
    )
    report = _validator().validate(_passport(), rules)
    assert report.status is ValidationStatus.VALID_WITH_WARNINGS
    assert report.is_valid is True
    assert report.error_count == 0
    assert any("optional section" in warning for warning in report.warnings)
    # The optional section is absent but still recorded as valid (not an error).
    optional = report.checked_sections[1]
    assert optional.present is False
    assert optional.valid is True


# --- Structural errors ----------------------------------------------------


def test_string_section_with_non_string_is_error():
    rules = IntegrityRuleSet(
        version="1.0",
        sections=(SectionRule(name="classification", kind=SectionKind.STRING),),
    )
    report = _validator().validate(_passport(), rules)
    assert report.status is ValidationStatus.INVALID
    assert any("must be a string" in error for error in report.errors)


def test_array_section_with_non_list_is_error():
    rules = IntegrityRuleSet(
        version="1.0",
        sections=(SectionRule(name="passport_id", kind=SectionKind.ARRAY),),
    )
    report = _validator().validate(_passport(), rules)
    assert report.status is ValidationStatus.INVALID
    assert any("must be an array" in error for error in report.errors)


def test_object_section_with_non_mapping_is_error():
    rules = IntegrityRuleSet(
        version="1.0",
        sections=(
            SectionRule(name="passport_id", kind=SectionKind.OBJECT, fields=("a",)),
        ),
    )
    report = _validator().validate(_passport(), rules)
    assert report.status is ValidationStatus.INVALID
    assert any("must be an object" in error for error in report.errors)


def test_object_section_missing_field_is_error():
    rules = IntegrityRuleSet(
        version="1.0",
        sections=(
            SectionRule(
                name="classification",
                kind=SectionKind.OBJECT,
                fields=("device_type", "missing_field"),
            ),
        ),
    )
    report = _validator().validate(_passport(), rules)
    assert report.status is ValidationStatus.INVALID
    assert any("missing required field" in error for error in report.errors)


def test_confidence_out_of_range_is_error():
    broken = dataclasses.replace(
        _passport(),
        classification=Classification(
            device_type="laptop", confidence=1.5, has_conflicts=False
        ),
    )
    report = _validator().validate(broken, _rules())
    assert report.status is ValidationStatus.INVALID
    assert any("numeric confidence within [0, 1]" in error for error in report.errors)


def test_confidence_boolean_is_error():
    broken = dataclasses.replace(
        _passport(),
        classification=Classification(
            device_type="laptop",
            confidence=True,  # type: ignore[arg-type]
            has_conflicts=False,
        ),
    )
    report = _validator().validate(broken, _rules())
    assert report.status is ValidationStatus.INVALID
    assert any("numeric confidence" in error for error in report.errors)


def test_multiple_errors_are_deduplicated_and_ordered():
    rules = IntegrityRuleSet(
        version="1.0",
        sections=(
            SectionRule(name="alpha", kind=SectionKind.STRING),
            SectionRule(name="beta", kind=SectionKind.STRING),
        ),
    )
    report = _validator().validate(_passport(), rules)
    assert report.error_count == 2
    assert "alpha" in report.errors[0]
    assert "beta" in report.errors[1]
