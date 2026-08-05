"""Unit tests for the passport validation rule-set loader (milestone M2.4).

Exercises the strict rule-set loader against the shipped YAML rule-set and
hand-built malformed rule-sets. Mirrors the passport-schema :mod:`test_passport_schema`
structure: a loader that aggressively validates the external rule-set file and
fails with a typed :class:`PassportIntegrityRuleError` on any structural problem.
"""

from pathlib import Path

import pytest

from device_ai.exceptions import PassportIntegrityRuleError
from device_ai.integrity.rules import (
    IntegrityRuleSet,
    SectionKind,
    SectionRule,
    load_rules,
)

# --- Loader: shipped rule-set ---------------------------------------------


def test_load_shipped_rules():
    from device_ai.integrity.config import DEFAULT_RULES_PATH

    package_root = Path(__file__).resolve().parent.parent
    rules = load_rules(package_root / DEFAULT_RULES_PATH)
    assert isinstance(rules, IntegrityRuleSet)
    assert rules.version == "1.0.0"
    assert rules.section_count == 13
    assert "passport_id" in rules.section_names
    assert "device_identity" in rules.section_names
    assert "confidence_summary" in rules.section_names


def test_shipped_rules_declare_required_sections():
    from device_ai.integrity.config import DEFAULT_RULES_PATH

    package_root = Path(__file__).resolve().parent.parent
    rules = load_rules(package_root / DEFAULT_RULES_PATH)
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
    assert set(rules.section_names) == required


def test_shipped_rules_mark_fingerprint_optional():
    from device_ai.integrity.config import DEFAULT_RULES_PATH

    package_root = Path(__file__).resolve().parent.parent
    rules = load_rules(package_root / DEFAULT_RULES_PATH)
    fingerprint = rules.section("fingerprint_summary")
    assert fingerprint is not None
    assert fingerprint.required is False
    # Every other section defaults to required.
    identity = rules.section("device_identity")
    assert identity is not None
    assert identity.required is True


def test_shipped_rules_object_sections_have_fields():
    from device_ai.integrity.config import DEFAULT_RULES_PATH

    package_root = Path(__file__).resolve().parent.parent
    rules = load_rules(package_root / DEFAULT_RULES_PATH)
    identity = rules.section("device_identity")
    assert identity is not None
    assert identity.kind is SectionKind.OBJECT
    assert "brand" in identity.fields
    assert "model" in identity.fields


def test_shipped_rules_declare_confidence_fields():
    from device_ai.integrity.config import DEFAULT_RULES_PATH

    package_root = Path(__file__).resolve().parent.parent
    rules = load_rules(package_root / DEFAULT_RULES_PATH)
    classification = rules.section("classification")
    assert classification is not None
    assert "confidence" in classification.confidence_fields
    confidence_summary = rules.section("confidence_summary")
    assert confidence_summary is not None
    assert len(confidence_summary.confidence_fields) == 5


# --- Loader: malformed rule-set -------------------------------------------


def test_load_missing_rules_raises():
    with pytest.raises(PassportIntegrityRuleError, match="not found"):
        load_rules(Path("/nonexistent/rules.yaml"))


def test_load_empty_rules_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(PassportIntegrityRuleError, match="empty"):
        load_rules(path)


def test_load_rules_without_version_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("sections: {}\n", encoding="utf-8")
    with pytest.raises(PassportIntegrityRuleError, match="version"):
        load_rules(path)


def test_load_rules_without_sections_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("version: '1.0'\n", encoding="utf-8")
    with pytest.raises(PassportIntegrityRuleError, match="sections"):
        load_rules(path)


def test_load_rules_with_empty_sections_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("version: '1.0'\nsections: {}\n", encoding="utf-8")
    with pytest.raises(PassportIntegrityRuleError, match="no sections"):
        load_rules(path)


def test_load_rules_with_unknown_kind_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\nsections:\n  test:\n    kind: mystery\n", encoding="utf-8"
    )
    with pytest.raises(PassportIntegrityRuleError, match="unknown kind"):
        load_rules(path)


def test_load_object_section_without_fields_key_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\nsections:\n  test:\n    kind: object\n", encoding="utf-8"
    )
    # A missing 'fields' key is a null field list, rejected as "must be a list".
    with pytest.raises(PassportIntegrityRuleError, match="must be a list"):
        load_rules(path)


def test_load_object_section_with_empty_fields_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\nsections:\n  test:\n    kind: object\n    fields: []\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportIntegrityRuleError, match="no 'fields'"):
        load_rules(path)


def test_load_rules_with_confidence_field_not_in_fields_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n"
        "sections:\n"
        "  test:\n"
        "    kind: object\n"
        "    fields: [a, b]\n"
        "    confidence_fields: [c]\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportIntegrityRuleError, match="not present in"):
        load_rules(path)


def test_load_string_section_with_fields_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\nsections:\n  test:\n    kind: string\n    fields: [a]\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportIntegrityRuleError, match="only object sections"):
        load_rules(path)


def test_load_rules_with_non_boolean_required_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\nsections:\n  test:\n    kind: string\n    required: maybe\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportIntegrityRuleError, match="boolean 'required'"):
        load_rules(path)


def test_load_rules_with_duplicate_field_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\nsections:\n  test:\n    kind: object\n    fields: [a, a]\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportIntegrityRuleError, match="duplicate field"):
        load_rules(path)


def test_load_rules_from_json(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(
        '{"version": "9.9", "sections": {"passport_id": {"kind": "string"}}}',
        encoding="utf-8",
    )
    rules = load_rules(path)
    assert rules.version == "9.9"
    assert rules.section_names == ("passport_id",)


# --- Value objects --------------------------------------------------------


def test_section_rule_to_dict_round_trips_fields():
    rule = SectionRule(
        name="classification",
        kind=SectionKind.OBJECT,
        fields=("device_type", "confidence"),
        confidence_fields=("confidence",),
        required=True,
    )
    payload = rule.to_dict()
    assert payload == {
        "name": "classification",
        "kind": "object",
        "fields": ["device_type", "confidence"],
        "confidence_fields": ["confidence"],
        "required": True,
    }


def test_section_kind_values():
    assert SectionKind.values() == ["string", "object", "array"]
