"""Unit tests for the passport schema loader and validator (milestone M2.3).

Exercises the strict passport-schema loader against the shipped YAML schema and
hand-built malformed schemas, and the validator against conformant/malformed
passport payloads. Mirrors the circular :mod:`test_circular_rules` structure: a
loader that aggressively validates the external schema file and a validator that
checks every assembled passport against it.
"""

from pathlib import Path

import pytest

from device_ai.exceptions import PassportSchemaError, PassportValidationError
from device_ai.passport.schema import (
    PassportSchema,
    SectionKind,
    SectionSchema,
    load_schema,
    validate_passport,
)

# --- Loader: shipped schema -----------------------------------------------


def test_load_shipped_schema():
    from device_ai.passport.config import DEFAULT_SCHEMA_PATH

    package_root = Path(__file__).resolve().parent.parent
    schema = load_schema(package_root / DEFAULT_SCHEMA_PATH)
    assert isinstance(schema, PassportSchema)
    assert schema.version == "1.0.0"
    assert schema.section_count == 13
    assert "passport_id" in schema.section_names
    assert "device_identity" in schema.section_names
    assert "confidence_summary" in schema.section_names


def test_shipped_schema_declares_required_sections():
    from device_ai.passport.config import DEFAULT_SCHEMA_PATH

    package_root = Path(__file__).resolve().parent.parent
    schema = load_schema(package_root / DEFAULT_SCHEMA_PATH)
    required = {
        "passport_id",
        "passport_version",
        "eco_id",
        "device_identity",
        "classification",
        "decision_summary",
        "material_summary",
        "environmental_summary",
        "fingerprint_summary",
        "confidence_summary",
        "metadata",
        "reasoning",
        "warnings",
    }
    assert set(schema.section_names) == required


def test_shipped_schema_object_sections_have_fields():
    from device_ai.passport.config import DEFAULT_SCHEMA_PATH

    package_root = Path(__file__).resolve().parent.parent
    schema = load_schema(package_root / DEFAULT_SCHEMA_PATH)
    identity = schema.section("device_identity")
    assert identity is not None
    assert identity.kind is SectionKind.OBJECT
    assert "brand" in identity.fields
    assert "model" in identity.fields


def test_shipped_schema_declares_confidence_fields():
    from device_ai.passport.config import DEFAULT_SCHEMA_PATH

    package_root = Path(__file__).resolve().parent.parent
    schema = load_schema(package_root / DEFAULT_SCHEMA_PATH)
    classification = schema.section("classification")
    assert classification is not None
    assert "confidence" in classification.confidence_fields
    confidence_summary = schema.section("confidence_summary")
    assert confidence_summary is not None
    assert len(confidence_summary.confidence_fields) == 5


# --- Loader: malformed schema ---------------------------------------------


def test_load_missing_schema_raises():
    with pytest.raises(PassportSchemaError, match="not found"):
        load_schema(Path("/nonexistent/schema.yaml"))


def test_load_empty_schema_raises():
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        path = Path(f.name)
    try:
        with pytest.raises(PassportSchemaError, match="empty"):
            load_schema(path)
    finally:
        path.unlink()


def test_load_schema_without_version_raises():
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("sections: {}\n")
        path = Path(f.name)
    try:
        with pytest.raises(PassportSchemaError, match="version"):
            load_schema(path)
    finally:
        path.unlink()


def test_load_schema_without_sections_raises():
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("version: '1.0'\n")
        path = Path(f.name)
    try:
        with pytest.raises(PassportSchemaError, match="sections"):
            load_schema(path)
    finally:
        path.unlink()


def test_load_schema_with_empty_sections_raises():
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("version: '1.0'\nsections: {}\n")
        path = Path(f.name)
    try:
        with pytest.raises(PassportSchemaError, match="no sections"):
            load_schema(path)
    finally:
        path.unlink()


def test_load_schema_with_unknown_kind_raises():
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("version: '1.0'\nsections:\n  test:\n    kind: mystery\n")
        path = Path(f.name)
    try:
        with pytest.raises(PassportSchemaError, match="unknown kind"):
            load_schema(path)
    finally:
        path.unlink()


def test_load_object_section_without_fields_key_raises():
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("version: '1.0'\nsections:\n  test:\n    kind: object\n")
        path = Path(f.name)
    try:
        # A missing 'fields' key is a null field list, rejected as "must be a list".
        with pytest.raises(PassportSchemaError, match="must be a list"):
            load_schema(path)
    finally:
        path.unlink()


def test_load_object_section_with_empty_fields_raises():
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(
            "version: '1.0'\nsections:\n  test:\n    kind: object\n    fields: []\n"
        )
        path = Path(f.name)
    try:
        with pytest.raises(PassportSchemaError, match="no 'fields'"):
            load_schema(path)
    finally:
        path.unlink()


def test_load_schema_with_confidence_field_not_in_fields_raises():
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(
            "version: '1.0'\n"
            "sections:\n"
            "  test:\n"
            "    kind: object\n"
            "    fields: [a, b]\n"
            "    confidence_fields: [c]\n"
        )
        path = Path(f.name)
    try:
        with pytest.raises(PassportSchemaError, match="not present in"):
            load_schema(path)
    finally:
        path.unlink()


# --- Validator: conformant payload ----------------------------------------


def test_validate_minimal_conformant_passport():
    from device_ai.passport.config import DEFAULT_SCHEMA_PATH

    package_root = Path(__file__).resolve().parent.parent
    schema = load_schema(package_root / DEFAULT_SCHEMA_PATH)
    payload = {
        "passport_id": "ET-PP-AABBCCDDEEFF",
        "passport_version": "1.0.0",
        "eco_id": "ET-2026-00000001",
        "device_identity": {
            "brand": "Dell",
            "model": "XPS-13",
            "serial_number": "SN123",
            "imei": "",
            "mac_address": "",
        },
        "classification": {
            "device_type": "laptop",
            "confidence": 0.9,
            "has_conflicts": False,
        },
        "decision_summary": {
            "recommended_action": "refurbish",
            "priority": "medium",
            "confidence": 0.85,
            "winning_rule_id": "rule_1",
            "triggered_count": 1,
        },
        "material_summary": {
            "material_count": 5,
            "total_mass_g": 1200.0,
            "recoverable_mass_g": 1000.0,
            "hazardous_mass_g": 50.0,
            "confidence": 0.8,
        },
        "environmental_summary": {
            "carbon_saved_kg": 12.5,
            "energy_saved_mj": 300.0,
            "water_saved_l": 150.0,
            "landfill_diversion_kg": 1.0,
            "critical_material_recovery_kg": 0.05,
            "circularity_index": 0.7,
            "hazard_reduction_score": 0.6,
            "confidence": 0.75,
        },
        "fingerprint_summary": {
            "fingerprint": "f" * 64,
            "dimension": 512,
            "encoder_name": "CLIP",
            "encoder_version": "1.0",
            "metric": "cosine",
        },
        "confidence_summary": {
            "identity_confidence": 0.9,
            "decision_confidence": 0.85,
            "material_confidence": 0.8,
            "environmental_confidence": 0.75,
            "overall": 0.825,
        },
        "metadata": {
            "passport_engine_version": "1.0.0",
            "schema_version": "1.0.0",
            "fusion_engine_version": "1.0.0",
            "decision_engine_version": "1.0.0",
            "decision_rules_version": "1.0.0",
            "material_engine_version": "1.0.0",
            "material_profile_version": "1.0.0",
            "environmental_engine_version": "1.0.0",
            "environmental_factors_version": "1.0.0",
            "source_image_count": 1,
            "created_at": "2026-08-01T12:00:00Z",
        },
        "reasoning": ["Reason one", "Reason two"],
        "warnings": ["Warning one"],
    }
    validate_passport(payload, schema)  # Should not raise


# --- Validator: malformed payload -----------------------------------------


def test_validate_missing_section_raises():
    from device_ai.passport.config import DEFAULT_SCHEMA_PATH

    package_root = Path(__file__).resolve().parent.parent
    schema = load_schema(package_root / DEFAULT_SCHEMA_PATH)
    payload = {"passport_id": "ET-PP-AABBCCDDEEFF"}
    with pytest.raises(PassportValidationError, match="missing required section"):
        validate_passport(payload, schema)


def test_validate_string_section_with_non_string_raises():
    schema = PassportSchema(
        version="1.0",
        sections=(SectionSchema(name="test_id", kind=SectionKind.STRING),),
    )
    payload = {"test_id": 123}
    with pytest.raises(PassportValidationError, match="must be a string"):
        validate_passport(payload, schema)


def test_validate_array_section_with_non_list_raises():
    schema = PassportSchema(
        version="1.0",
        sections=(SectionSchema(name="test_list", kind=SectionKind.ARRAY),),
    )
    payload = {"test_list": "not a list"}
    with pytest.raises(PassportValidationError, match="must be an array"):
        validate_passport(payload, schema)


def test_validate_object_section_with_non_mapping_raises():
    schema = PassportSchema(
        version="1.0",
        sections=(
            SectionSchema(name="test_obj", kind=SectionKind.OBJECT, fields=("a", "b")),
        ),
    )
    payload = {"test_obj": "not a mapping"}
    with pytest.raises(PassportValidationError, match="must be an object"):
        validate_passport(payload, schema)


def test_validate_object_missing_field_raises():
    schema = PassportSchema(
        version="1.0",
        sections=(
            SectionSchema(name="test_obj", kind=SectionKind.OBJECT, fields=("a", "b")),
        ),
    )
    payload = {"test_obj": {"a": 1}}
    with pytest.raises(PassportValidationError, match="missing required field"):
        validate_passport(payload, schema)


def test_validate_confidence_out_of_range_raises():
    schema = PassportSchema(
        version="1.0",
        sections=(
            SectionSchema(
                name="test_obj",
                kind=SectionKind.OBJECT,
                fields=("conf",),
                confidence_fields=("conf",),
            ),
        ),
    )
    payload = {"test_obj": {"conf": 1.5}}
    with pytest.raises(PassportValidationError, match=r"within \[0, 1\]"):
        validate_passport(payload, schema)


def test_validate_confidence_with_boolean_raises():
    schema = PassportSchema(
        version="1.0",
        sections=(
            SectionSchema(
                name="test_obj",
                kind=SectionKind.OBJECT,
                fields=("conf",),
                confidence_fields=("conf",),
            ),
        ),
    )
    payload = {"test_obj": {"conf": True}}
    with pytest.raises(PassportValidationError, match="must be a numeric"):
        validate_passport(payload, schema)
