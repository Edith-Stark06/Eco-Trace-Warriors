"""Unit tests for the device lifecycle engine (milestone M3.3).

Exercises the deterministic :class:`LifecycleEngine`: validation of event
sequences against a resolved rule set, composition into immutable
:class:`LifecycleRecord` objects, and the incremental ``can_append`` predicate.
Uses a hand-built rule set so the tests stay independent of the shipped YAML.
Offline — no ledger, no upstream engines, no images.
"""

from __future__ import annotations

from device_ai.lifecycle.engine import LifecycleEngine
from device_ai.lifecycle.models import LifecycleEvent, LifecycleEventType
from device_ai.lifecycle.rules import LifecycleRuleSet, LifecycleTransition

E = LifecycleEventType


def _rules() -> LifecycleRuleSet:
    """A compact, valid rule set covering the linear happy path and a fork."""
    return LifecycleRuleSet(
        version="test-1",
        transitions=(
            LifecycleTransition(E.REGISTERED, (E.IN_USE, E.COLLECTED)),
            LifecycleTransition(E.IN_USE, (E.COLLECTED,)),
            LifecycleTransition(E.COLLECTED, (E.ASSESSED,)),
            LifecycleTransition(E.IN_TRANSIT, (E.ASSESSED,)),
            LifecycleTransition(E.ASSESSED, (E.REFURBISHED, E.RECYCLED)),
            LifecycleTransition(E.REFURBISHED, (E.IN_USE,)),
            LifecycleTransition(E.RECYCLED, (E.DISPOSED,)),
            LifecycleTransition(E.DISPOSED, ()),
        ),
        initial_events=(E.REGISTERED,),
    )


def _events(*types: LifecycleEventType) -> list[LifecycleEvent]:
    return [LifecycleEvent(event_type=t) for t in types]


# -- validate ----------------------------------------------------------------


def test_empty_sequence_is_valid():
    assert LifecycleEngine().validate([], _rules()) is True


def test_single_genesis_event_is_valid():
    assert LifecycleEngine().validate(_events(E.REGISTERED), _rules()) is True


def test_non_initial_first_event_is_invalid():
    """A lifecycle may not begin with a non-initial event."""
    assert LifecycleEngine().validate(_events(E.IN_USE), _rules()) is False


def test_valid_linear_path():
    seq = _events(
        E.REGISTERED, E.IN_USE, E.COLLECTED, E.ASSESSED, E.RECYCLED, E.DISPOSED
    )
    assert LifecycleEngine().validate(seq, _rules()) is True


def test_illegal_transition_is_invalid():
    """An undeclared transition (registered -> assessed) is rejected."""
    seq = _events(E.REGISTERED, E.ASSESSED)
    assert LifecycleEngine().validate(seq, _rules()) is False


def test_event_after_terminal_is_invalid():
    """No event may follow a terminal (disposed) event."""
    seq = _events(E.REGISTERED, E.COLLECTED, E.ASSESSED, E.RECYCLED, E.DISPOSED)
    assert LifecycleEngine().validate(seq, _rules()) is True
    seq_extended = [*seq, LifecycleEvent(event_type=E.IN_USE)]
    assert LifecycleEngine().validate(seq_extended, _rules()) is False


def test_refurbish_loop_back_to_use():
    """A refurbished device may re-enter use (a legal loop)."""
    seq = _events(E.REGISTERED, E.COLLECTED, E.ASSESSED, E.REFURBISHED, E.IN_USE)
    assert LifecycleEngine().validate(seq, _rules()) is True


# -- build_record ------------------------------------------------------------


def test_build_record_valid_path_stamps_provenance():
    engine = LifecycleEngine()
    seq = _events(E.REGISTERED, E.IN_USE, E.COLLECTED)
    record = engine.build_record(
        "dev-1", seq, _rules(), rules_version="test-1", engine_version="9.9.9"
    )
    assert record.is_valid is True
    assert record.device_id == "dev-1"
    assert record.event_count == 3
    assert record.current_state == "collected"
    assert record.rules_version == "test-1"
    assert record.engine_version == "9.9.9"


def test_build_record_invalid_path_is_data_not_exception():
    """A rejected sequence yields is_valid=False, not a raised error."""
    engine = LifecycleEngine()
    record = engine.build_record("dev-1", _events(E.IN_USE), _rules())
    assert record.is_valid is False
    assert record.current_state == "in_use"


def test_build_record_empty_is_valid_empty():
    engine = LifecycleEngine()
    record = engine.build_record("dev-1", [], _rules())
    assert record.is_valid is True
    assert record.is_empty is True
    assert record.current_state is None
    assert record.event_count == 0


# -- can_append --------------------------------------------------------------


def test_can_append_to_empty_requires_initial():
    engine = LifecycleEngine()
    empty = engine.build_record("dev-1", [], _rules())
    assert engine.can_append(empty, LifecycleEvent(event_type=E.REGISTERED), _rules())
    assert not engine.can_append(empty, LifecycleEvent(event_type=E.IN_USE), _rules())


def test_can_append_follows_current_state():
    engine = LifecycleEngine()
    record = engine.build_record("dev-1", _events(E.REGISTERED), _rules())
    assert engine.can_append(record, LifecycleEvent(event_type=E.IN_USE), _rules())
    assert not engine.can_append(
        record, LifecycleEvent(event_type=E.ASSESSED), _rules()
    )


def test_can_append_after_terminal_is_false():
    engine = LifecycleEngine()
    seq = _events(E.REGISTERED, E.COLLECTED, E.ASSESSED, E.RECYCLED, E.DISPOSED)
    record = engine.build_record("dev-1", seq, _rules())
    assert not engine.can_append(record, LifecycleEvent(event_type=E.IN_USE), _rules())
