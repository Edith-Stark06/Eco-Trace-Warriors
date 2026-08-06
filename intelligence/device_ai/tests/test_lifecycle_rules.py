"""Unit tests for the lifecycle transition-rules loader (milestone M3.3).

Exercises the strict lifecycle-rules loader against the shipped YAML rules and
hand-built malformed rules. Mirrors the M2.5 trust-catalogue and M3.1 ledger
config test structure: a loader that aggressively validates the external rules
file and fails with a typed :class:`LifecycleRuleError` on any structural
problem. Offline — no engine, no ledger.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from device_ai.exceptions import LifecycleRuleError
from device_ai.lifecycle.config import DEFAULT_RULES_PATH
from device_ai.lifecycle.models import LifecycleEventType
from device_ai.lifecycle.rules import (
    LifecycleRuleSet,
    LifecycleTransition,
    load_rules,
)


def _shipped() -> LifecycleRuleSet:
    package_root = Path(__file__).resolve().parent.parent
    return load_rules(package_root / DEFAULT_RULES_PATH)


# -- Loader: shipped rules ---------------------------------------------------


def test_load_shipped_rules():
    rules = _shipped()
    assert isinstance(rules, LifecycleRuleSet)
    assert rules.version == "1.0.0"


def test_shipped_declares_every_event_type_once():
    """Every LifecycleEventType has exactly one transition, in canonical order."""
    rules = _shipped()
    sources = [t.source for t in rules.transitions]
    assert sources == list(LifecycleEventType)


def test_shipped_initial_events():
    rules = _shipped()
    assert rules.initial_events == (LifecycleEventType.REGISTERED,)
    assert rules.is_initial(LifecycleEventType.REGISTERED) is True
    assert rules.is_initial(LifecycleEventType.IN_USE) is False


def test_shipped_terminal_events():
    """Disposal is terminal; it declares no successor."""
    rules = _shipped()
    assert rules.terminal_events == (LifecycleEventType.DISPOSED,)
    transition = rules.transition_for(LifecycleEventType.DISPOSED)
    assert transition is not None
    assert transition.is_terminal is True
    assert transition.targets == ()


def test_shipped_allows_expected_transitions():
    rules = _shipped()
    assert rules.allows(LifecycleEventType.REGISTERED, LifecycleEventType.IN_USE)
    assert rules.allows(LifecycleEventType.ASSESSED, LifecycleEventType.RECYCLED)
    assert rules.allows(LifecycleEventType.RECYCLED, LifecycleEventType.DISPOSED)
    # No skipping straight from registered to disposed.
    assert not rules.allows(LifecycleEventType.REGISTERED, LifecycleEventType.DISPOSED)
    # Nothing follows a terminal event.
    assert not rules.allows(LifecycleEventType.DISPOSED, LifecycleEventType.IN_USE)


def test_shipped_to_dict_round_trips_through_json():
    """The rule set serializes to a JSON-safe mapping."""
    rules = _shipped()
    data = rules.to_dict()
    assert data["version"] == "1.0.0"
    assert data["initial_events"] == ["registered"]
    # JSON-serializable without error.
    json.dumps(data)


# -- Loader: malformed rules -------------------------------------------------


def _write(tmp_path: Path, mapping: object) -> Path:
    """Write ``mapping`` as JSON (the loader accepts .json) and return its path."""
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _valid_mapping() -> dict:
    """A complete, valid rules mapping every event type declares once."""
    return {
        "version": "1.0.0",
        "initial_events": ["registered"],
        "transitions": {
            "registered": ["in_use"],
            "in_use": ["collected"],
            "collected": ["assessed"],
            "in_transit": ["assessed"],
            "assessed": ["recycled"],
            "refurbished": ["in_use"],
            "recycled": ["disposed"],
            "disposed": [],
        },
    }


def test_valid_baseline_loads(tmp_path):
    """The baseline mapping the negative tests mutate is itself valid."""
    rules = load_rules(_write(tmp_path, _valid_mapping()))
    assert rules.version == "1.0.0"


def test_missing_file_raises(tmp_path):
    with pytest.raises(LifecycleRuleError):
        load_rules(tmp_path / "nope.yaml")


def test_empty_file_raises(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(LifecycleRuleError):
        load_rules(path)


def test_root_not_mapping_raises(tmp_path):
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, ["not", "a", "mapping"]))


def test_missing_version_raises(tmp_path):
    mapping = _valid_mapping()
    del mapping["version"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_missing_transitions_raises(tmp_path):
    mapping = _valid_mapping()
    del mapping["transitions"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_missing_initial_events_raises(tmp_path):
    mapping = _valid_mapping()
    del mapping["initial_events"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_incomplete_transitions_raises(tmp_path):
    """Omitting an event type's transition is rejected."""
    mapping = _valid_mapping()
    del mapping["transitions"]["disposed"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_unknown_event_type_key_raises(tmp_path):
    mapping = _valid_mapping()
    mapping["transitions"]["teleported"] = []
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_unknown_target_raises(tmp_path):
    mapping = _valid_mapping()
    mapping["transitions"]["registered"] = ["teleported"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_self_transition_raises(tmp_path):
    mapping = _valid_mapping()
    mapping["transitions"]["in_use"] = ["in_use"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_duplicate_target_raises(tmp_path):
    mapping = _valid_mapping()
    mapping["transitions"]["registered"] = ["in_use", "in_use"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_no_terminal_event_raises(tmp_path):
    """A state machine with no terminal event cannot end and is rejected."""
    mapping = _valid_mapping()
    # Give disposed a successor so nothing is terminal.
    mapping["transitions"]["disposed"] = ["registered"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_empty_initial_events_raises(tmp_path):
    mapping = _valid_mapping()
    mapping["initial_events"] = []
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_duplicate_initial_event_raises(tmp_path):
    mapping = _valid_mapping()
    mapping["initial_events"] = ["registered", "registered"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_unknown_initial_event_raises(tmp_path):
    mapping = _valid_mapping()
    mapping["initial_events"] = ["teleported"]
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_transition_targets_not_a_list_raises(tmp_path):
    mapping = _valid_mapping()
    mapping["transitions"]["registered"] = "in_use"
    with pytest.raises(LifecycleRuleError):
        load_rules(_write(tmp_path, mapping))


def test_error_carries_code_and_path(tmp_path):
    """The typed error exposes its code and the offending path in details."""
    path = _write(tmp_path, {"version": "1.0.0"})
    with pytest.raises(LifecycleRuleError) as exc_info:
        load_rules(path)
    assert exc_info.value.code == "LIFECYCLE_RULE_ERROR"
    assert exc_info.value.details.get("path") == str(path)


def test_transition_helpers():
    """LifecycleTransition exposes terminal/allows helpers."""
    t = LifecycleTransition(
        source=LifecycleEventType.ASSESSED,
        targets=(LifecycleEventType.RECYCLED, LifecycleEventType.DISPOSED),
    )
    assert t.is_terminal is False
    assert t.allows(LifecycleEventType.RECYCLED) is True
    assert t.allows(LifecycleEventType.IN_USE) is False
    terminal = LifecycleTransition(source=LifecycleEventType.DISPOSED, targets=())
    assert terminal.is_terminal is True
