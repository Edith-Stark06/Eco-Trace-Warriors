"""Unit tests for the trust catalogue loader (milestone M2.5).

Exercises the strict trust-catalogue loader against the shipped YAML catalogue
and hand-built malformed catalogues. Mirrors the M2.4 integrity rule-set and the
M2.2 circular rule catalogue test structure: a loader that aggressively validates
the external catalogue file and fails with a typed
:class:`PassportTrustRuleError` on any structural problem.
"""

from pathlib import Path

import pytest

from device_ai.exceptions import PassportTrustRuleError
from device_ai.trust.models import TrustLevel
from device_ai.trust.rules import (
    CANONICAL_AXES,
    AxisWeight,
    TrustLevelRule,
    TrustRuleSet,
    load_rules,
)

# --- Loader: shipped catalogue --------------------------------------------


def _shipped():
    from device_ai.trust.config import DEFAULT_RULES_PATH

    package_root = Path(__file__).resolve().parent.parent
    return load_rules(package_root / DEFAULT_RULES_PATH)


def test_load_shipped_catalogue():
    rules = _shipped()
    assert isinstance(rules, TrustRuleSet)
    assert rules.version == "1.0.0"
    assert set(rules.axis_names) == CANONICAL_AXES
    assert rules.level_count == 4


def test_shipped_catalogue_weights_all_axes():
    rules = _shipped()
    assert set(rules.axis_names) == {
        "identity_confidence",
        "evidence_consistency",
        "decision_confidence",
        "integrity_confidence",
    }
    for axis in CANONICAL_AXES:
        assert rules.weight_for(axis) > 0.0
    assert rules.total_weight > 0.0


def test_shipped_catalogue_axes_in_canonical_order():
    rules = _shipped()
    assert rules.axis_names == (
        "identity_confidence",
        "evidence_consistency",
        "decision_confidence",
        "integrity_confidence",
    )


def test_shipped_catalogue_levels_sorted_descending():
    rules = _shipped()
    floors = [rule.min_score for rule in rules.levels]
    assert floors == sorted(floors, reverse=True)
    # A 0.0-floor level exists so every score resolves.
    assert any(rule.min_score == 0.0 for rule in rules.levels)


def test_shipped_catalogue_declares_every_level():
    rules = _shipped()
    declared = {rule.level for rule in rules.levels}
    assert declared == set(TrustLevel)


# --- level_for mapping -----------------------------------------------------


def test_level_for_maps_scores_to_levels():
    rules = _shipped()
    assert rules.level_for(0.90) is TrustLevel.HIGH
    assert rules.level_for(0.60) is TrustLevel.MEDIUM
    assert rules.level_for(0.30) is TrustLevel.LOW
    assert rules.level_for(0.10) is TrustLevel.UNTRUSTED


def test_level_for_boundary_is_inclusive():
    rules = _shipped()
    # A score exactly on a floor maps to that level (inclusive floor).
    assert rules.level_for(0.75) is TrustLevel.HIGH
    assert rules.level_for(0.50) is TrustLevel.MEDIUM
    assert rules.level_for(0.25) is TrustLevel.LOW
    assert rules.level_for(0.0) is TrustLevel.UNTRUSTED


def test_weight_for_absent_axis_is_zero():
    rules = _shipped()
    assert rules.weight_for("nonexistent_axis") == 0.0


# --- Loader: malformed catalogue ------------------------------------------


def test_load_missing_catalogue_raises():
    with pytest.raises(PassportTrustRuleError, match="not found"):
        load_rules(Path("/nonexistent/rules.yaml"))


def test_load_empty_catalogue_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(PassportTrustRuleError, match="empty"):
        load_rules(path)


def test_load_non_mapping_root_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(PassportTrustRuleError, match="root must be a mapping"):
        load_rules(path)


def test_load_catalogue_without_version_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("weights: {}\nlevels: []\n", encoding="utf-8")
    with pytest.raises(PassportTrustRuleError, match="version"):
        load_rules(path)


def test_load_catalogue_without_weights_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("version: '1.0'\nlevels: []\n", encoding="utf-8")
    with pytest.raises(PassportTrustRuleError, match="missing the required 'weights'"):
        load_rules(path)


def test_load_catalogue_with_empty_weights_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("version: '1.0'\nweights: {}\nlevels: []\n", encoding="utf-8")
    with pytest.raises(PassportTrustRuleError, match="no axis weights"):
        load_rules(path)


def test_load_catalogue_with_unknown_axis_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\nweights:\n  mystery_axis: 0.5\nlevels: []\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="unknown axis"):
        load_rules(path)


def test_load_catalogue_with_missing_axis_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n"
        "weights:\n"
        "  identity_confidence: 0.5\n"
        "  evidence_consistency: 0.5\n"
        "levels: []\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="missing required axis"):
        load_rules(path)


def test_load_catalogue_with_negative_weight_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n"
        "weights:\n"
        "  identity_confidence: -0.1\n"
        "  evidence_consistency: 0.5\n"
        "  decision_confidence: 0.5\n"
        "  integrity_confidence: 0.5\n"
        "levels: []\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="within"):
        load_rules(path)


def test_load_catalogue_with_all_zero_weights_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n"
        "weights:\n"
        "  identity_confidence: 0.0\n"
        "  evidence_consistency: 0.0\n"
        "  decision_confidence: 0.0\n"
        "  integrity_confidence: 0.0\n"
        "levels:\n"
        "  - {level: untrusted, min_score: 0.0}\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="sum to zero"):
        load_rules(path)


def test_load_catalogue_with_boolean_weight_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n"
        "weights:\n"
        "  identity_confidence: true\n"
        "  evidence_consistency: 0.5\n"
        "  decision_confidence: 0.5\n"
        "  integrity_confidence: 0.5\n"
        "levels: []\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="numeric"):
        load_rules(path)


def _valid_weights_block() -> str:
    return (
        "weights:\n"
        "  identity_confidence: 0.25\n"
        "  evidence_consistency: 0.25\n"
        "  decision_confidence: 0.25\n"
        "  integrity_confidence: 0.25\n"
    )


def test_load_catalogue_without_levels_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("version: '1.0'\n" + _valid_weights_block(), encoding="utf-8")
    with pytest.raises(PassportTrustRuleError, match="missing the required 'levels'"):
        load_rules(path)


def test_load_catalogue_with_empty_levels_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n" + _valid_weights_block() + "levels: []\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="no trust levels"):
        load_rules(path)


def test_load_catalogue_with_unknown_level_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n"
        + _valid_weights_block()
        + "levels:\n  - {level: superb, min_score: 0.9}\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="unknown level"):
        load_rules(path)


def test_load_catalogue_with_duplicate_level_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n" + _valid_weights_block() + "levels:\n"
        "  - {level: high, min_score: 0.9}\n"
        "  - {level: high, min_score: 0.5}\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="duplicate level"):
        load_rules(path)


def test_load_catalogue_missing_a_level_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n" + _valid_weights_block() + "levels:\n"
        "  - {level: high, min_score: 0.75}\n"
        "  - {level: medium, min_score: 0.5}\n"
        "  - {level: low, min_score: 0.0}\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="missing required level"):
        load_rules(path)


def test_load_catalogue_without_zero_floor_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n" + _valid_weights_block() + "levels:\n"
        "  - {level: high, min_score: 0.75}\n"
        "  - {level: medium, min_score: 0.5}\n"
        "  - {level: low, min_score: 0.25}\n"
        "  - {level: untrusted, min_score: 0.1}\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="0.0 floor"):
        load_rules(path)


def test_load_catalogue_with_out_of_range_floor_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: '1.0'\n"
        + _valid_weights_block()
        + "levels:\n  - {level: high, min_score: 1.5}\n",
        encoding="utf-8",
    )
    with pytest.raises(PassportTrustRuleError, match="within"):
        load_rules(path)


def test_load_catalogue_from_json(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(
        '{"version": "9.9", "weights": {"identity_confidence": 0.25, '
        '"evidence_consistency": 0.25, "decision_confidence": 0.25, '
        '"integrity_confidence": 0.25}, "levels": [{"level": "high", '
        '"min_score": 0.75}, {"level": "medium", "min_score": 0.5}, '
        '{"level": "low", "min_score": 0.25}, {"level": "untrusted", '
        '"min_score": 0.0}]}',
        encoding="utf-8",
    )
    rules = load_rules(path)
    assert rules.version == "9.9"
    assert rules.level_count == 4


def test_load_unparseable_yaml_raises(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("version: '1.0'\nweights: {::::\n", encoding="utf-8")
    with pytest.raises(PassportTrustRuleError, match="Failed to parse"):
        load_rules(path)


# --- Value objects ---------------------------------------------------------


def test_axis_weight_to_dict():
    weight = AxisWeight(axis="identity_confidence", weight=0.3)
    assert weight.to_dict() == {"axis": "identity_confidence", "weight": 0.3}


def test_trust_level_rule_to_dict():
    rule = TrustLevelRule(level=TrustLevel.HIGH, min_score=0.75)
    assert rule.to_dict() == {"level": "high", "min_score": 0.75}


def test_canonical_axes_membership():
    assert "identity_confidence" in CANONICAL_AXES
    assert "evidence_consistency" in CANONICAL_AXES
    assert "decision_confidence" in CANONICAL_AXES
    assert "integrity_confidence" in CANONICAL_AXES
    assert len(CANONICAL_AXES) == 4
