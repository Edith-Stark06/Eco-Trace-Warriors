"""Tests for the external circular-decision rule catalogue and loader (M2.2).

The catalogue is stored *outside* the code as a versioned YAML file, so these
tests cover both the shipped catalogue (structure, invariants, uniqueness of ids
and precedences, a valid default) and the loader's aggressive validation on
hand-written good/bad catalogues in ``tmp_path`` — no images, no models, no
filesystem beyond the temp catalogue.
"""

import json
from pathlib import Path

import pytest

from device_ai.circular.config import DEFAULT_RULES_PATH
from device_ai.circular.models import Priority, RecommendedAction
from device_ai.circular.rules import (
    CANONICAL_SIGNALS,
    CONDITION_OPERATORS,
    DecisionRule,
    DefaultRule,
    RuleCatalogue,
    RuleCondition,
    load_rules,
)
from device_ai.exceptions import CircularRuleError

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SHIPPED = _PACKAGE_ROOT / DEFAULT_RULES_PATH


@pytest.fixture()
def catalogue() -> RuleCatalogue:
    """Load the shipped circular-decision rule catalogue once for the suite."""
    return load_rules(_SHIPPED)


# --- Shipped catalogue structure & invariants ----------------------------


def test_shipped_catalogue_loads(catalogue):
    assert catalogue.version
    assert catalogue.rule_count == len(catalogue.rules)
    assert catalogue.rules
    assert isinstance(catalogue.default, DefaultRule)


def test_rules_are_sorted_by_ascending_precedence(catalogue):
    precedences = [rule.precedence for rule in catalogue.rules]
    assert precedences == sorted(precedences)


def test_rule_ids_are_unique(catalogue):
    ids = [rule.rule_id for rule in catalogue.rules]
    assert len(ids) == len(set(ids))


def test_rule_precedences_are_unique(catalogue):
    precedences = [rule.precedence for rule in catalogue.rules]
    assert len(precedences) == len(set(precedences))


def test_every_rule_uses_only_canonical_signals_and_operators(catalogue):
    for rule in catalogue.rules:
        assert isinstance(rule, DecisionRule)
        assert rule.conditions, rule.rule_id
        for condition in rule.conditions:
            assert condition.signal in CANONICAL_SIGNALS, condition.signal
            assert condition.operator in CONDITION_OPERATORS, condition.operator
            assert 0.0 <= condition.threshold <= 1.0, condition.threshold


def test_every_rule_names_a_known_action_and_priority(catalogue):
    for rule in catalogue.rules:
        assert isinstance(rule.action, RecommendedAction)
        assert isinstance(rule.priority, Priority)
        assert 0.0 < rule.confidence_factor <= 1.0, rule.rule_id


def test_default_is_a_known_action_and_priority(catalogue):
    assert isinstance(catalogue.default.action, RecommendedAction)
    assert isinstance(catalogue.default.priority, Priority)
    assert catalogue.default.reason


# --- Condition & rule matching semantics ---------------------------------


def test_condition_matches_uses_operator_predicate():
    condition = RuleCondition(signal="reusability", operator="gte", threshold=0.5)
    assert condition.matches({"reusability": 0.5}) is True
    assert condition.matches({"reusability": 0.6}) is True
    assert condition.matches({"reusability": 0.4}) is False


def test_condition_missing_signal_reads_as_zero():
    # A signal the engine did not project is read as 0.0, so a gte-against a
    # positive threshold never spuriously fires on absent evidence.
    condition = RuleCondition(signal="conflict", operator="gte", threshold=1.0)
    assert condition.matches({}) is False
    lte = RuleCondition(signal="conflict", operator="lte", threshold=0.0)
    assert lte.matches({}) is True


def test_rule_matches_is_a_conjunction():
    rule = DecisionRule(
        rule_id="both",
        precedence=1,
        action=RecommendedAction.RECYCLE,
        priority=Priority.LOW,
        reason="two conditions",
        conditions=(
            RuleCondition("recycling", "gte", 0.45),
            RuleCondition("material_value", "gte", 0.6),
        ),
    )
    assert rule.matches({"recycling": 0.5, "material_value": 0.7}) is True
    # One condition failing fails the whole rule.
    assert rule.matches({"recycling": 0.5, "material_value": 0.5}) is False


def test_rule_and_condition_round_trip_to_dict():
    condition = RuleCondition(signal="reusability", operator="gte", threshold=0.65)
    assert condition.to_dict() == {
        "signal": "reusability",
        "operator": "gte",
        "threshold": 0.65,
    }
    rule = DecisionRule(
        rule_id="refurbish",
        precedence=70,
        action=RecommendedAction.REFURBISH,
        priority=Priority.MEDIUM,
        reason="reusable",
        conditions=(condition,),
        confidence_factor=0.9,
        warning="check it",
    )
    payload = rule.to_dict()
    assert payload["rule_id"] == "refurbish"
    assert payload["action"] == "refurbish"
    assert payload["priority"] == "medium"
    assert payload["confidence_factor"] == 0.9
    assert payload["warning"] == "check it"
    assert payload["conditions"] == [condition.to_dict()]


# --- Loader validation (hand-written catalogues) -------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


_GOOD_RULE = (
    "rules:\n"
    "  - id: recycle\n"
    "    precedence: 100\n"
    "    action: recycle\n"
    "    priority: low\n"
    "    reason: recyclable\n"
    "    when:\n"
    "      - signal: recycling\n"
    "        operator: gte\n"
    "        threshold: 0.45\n"
)

_GOOD_DEFAULT = (
    "default:\n"
    "  action: manual_review\n"
    "  priority: low\n"
    "  reason: nothing matched\n"
)


def _good_catalogue() -> str:
    return 'version: "1.0.0"\n' + _GOOD_RULE + _GOOD_DEFAULT


def test_hand_written_good_catalogue_loads(tmp_path):
    good = _write(tmp_path / "r.yaml", _good_catalogue())
    catalogue = load_rules(good)
    assert catalogue.version == "1.0.0"
    assert catalogue.rule_count == 1
    assert catalogue.rules[0].rule_id == "recycle"
    assert catalogue.default.action is RecommendedAction.MANUAL_REVIEW


def test_missing_file_raises(tmp_path):
    with pytest.raises(CircularRuleError):
        load_rules(tmp_path / "nope.yaml")


def test_malformed_yaml_raises(tmp_path):
    bad = _write(tmp_path / "r.yaml", "version: '1'\nrules: [::::\n")
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_empty_catalogue_raises(tmp_path):
    bad = _write(tmp_path / "r.yaml", "")
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_root_not_a_mapping_raises(tmp_path):
    bad = _write(tmp_path / "r.yaml", "- just\n- a\n- list\n")
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_missing_version_raises(tmp_path):
    bad = _write(tmp_path / "r.yaml", _GOOD_RULE + _GOOD_DEFAULT)
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_no_rules_raises(tmp_path):
    bad = _write(tmp_path / "r.yaml", 'version: "1"\nrules: []\n' + _GOOD_DEFAULT)
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_rules_not_a_list_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml", 'version: "1"\nrules:\n  recycle: 1\n' + _GOOD_DEFAULT
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_missing_default_raises(tmp_path):
    bad = _write(tmp_path / "r.yaml", 'version: "1"\n' + _GOOD_RULE)
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_rule_with_no_conditions_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: nowhen\n"
        "    precedence: 1\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when: []\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_unknown_signal_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: 1\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: unobtanium\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_unknown_operator_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: 1\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: ge\n"  # not one of gte/lte/gt/lt
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_unknown_action_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: 1\n"
        "    action: teleport\n"  # not a RecommendedAction
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_unknown_priority_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: 1\n"
        "    action: recycle\n"
        "    priority: urgent\n"  # not a Priority
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_out_of_range_threshold_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: 1\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 1.5\n" + _GOOD_DEFAULT,  # > 1.0
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_negative_precedence_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: -1\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_bool_precedence_is_rejected_as_integer(tmp_path):
    # ``True`` is an int subclass in Python; the loader must not accept it.
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: true\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_bool_threshold_is_rejected_as_numeric(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: 1\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: true\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_out_of_range_confidence_factor_raises(tmp_path):
    # confidence_factor must be in (0, 1]; zero is not permitted.
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: r\n"
        "    precedence: 1\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    confidence_factor: 0.0\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_duplicate_rule_id_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: dup\n"
        "    precedence: 1\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 0.5\n"
        "  - id: dup\n"  # duplicate id
        "    precedence: 2\n"
        "    action: repair\n"
        "    priority: medium\n"
        "    reason: r2\n"
        "    when:\n"
        "      - signal: repairability\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_duplicate_precedence_raises(tmp_path):
    bad = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: one\n"
        "    precedence: 5\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 0.5\n"
        "  - id: two\n"
        "    precedence: 5\n"  # duplicate precedence
        "    action: repair\n"
        "    priority: medium\n"
        "    reason: r2\n"
        "    when:\n"
        "      - signal: repairability\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    with pytest.raises(CircularRuleError):
        load_rules(bad)


def test_loader_sorts_rules_by_precedence(tmp_path):
    unsorted = _write(
        tmp_path / "r.yaml",
        'version: "1"\n'
        "rules:\n"
        "  - id: late\n"
        "    precedence: 90\n"
        "    action: recycle\n"
        "    priority: low\n"
        "    reason: r\n"
        "    when:\n"
        "      - signal: recycling\n"
        "        operator: gte\n"
        "        threshold: 0.5\n"
        "  - id: early\n"
        "    precedence: 10\n"
        "    action: repair\n"
        "    priority: medium\n"
        "    reason: r2\n"
        "    when:\n"
        "      - signal: repairability\n"
        "        operator: gte\n"
        "        threshold: 0.5\n" + _GOOD_DEFAULT,
    )
    catalogue = load_rules(unsorted)
    assert [rule.rule_id for rule in catalogue.rules] == ["early", "late"]


# --- JSON catalogue parity ------------------------------------------------


def test_json_catalogue_loads(tmp_path):
    doc = {
        "version": "9.9.9",
        "rules": [
            {
                "id": "recycle",
                "precedence": 100,
                "action": "recycle",
                "priority": "low",
                "reason": "recyclable",
                "when": [{"signal": "recycling", "operator": "gte", "threshold": 0.45}],
            }
        ],
        "default": {
            "action": "manual_review",
            "priority": "low",
            "reason": "nothing matched",
        },
    }
    path = tmp_path / "r.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalogue = load_rules(path)
    assert catalogue.version == "9.9.9"
    assert catalogue.rule_count == 1
