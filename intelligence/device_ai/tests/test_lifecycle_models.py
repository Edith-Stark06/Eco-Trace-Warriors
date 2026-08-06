"""Unit tests for the device lifecycle domain models (milestone M3.3).

Exercises the frozen, slotted :class:`LifecycleEventType`, :class:`LifecycleEvent`
and :class:`LifecycleRecord` value objects: their immutability, their canonical
``to_dict``/``to_json`` serialization, and their computed properties. Offline —
no upstream engines, no ledger, no images.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from device_ai.lifecycle.models import (
    LifecycleEvent,
    LifecycleEventType,
    LifecycleRecord,
)

_TS = datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC)


# -- LifecycleEventType ------------------------------------------------------


def test_event_type_is_str_enum():
    """Members serialize to their wire value directly (a ``str`` enum)."""
    assert LifecycleEventType.REGISTERED == "registered"
    assert LifecycleEventType.DISPOSED.value == "disposed"


def test_event_type_values_in_declaration_order():
    """``values()`` returns every wire value in declaration order."""
    assert LifecycleEventType.values() == [
        "registered",
        "in_use",
        "collected",
        "in_transit",
        "assessed",
        "refurbished",
        "recycled",
        "disposed",
    ]


def test_event_type_constructed_from_wire_value():
    """A wire string round-trips back to its member."""
    assert LifecycleEventType("collected") is LifecycleEventType.COLLECTED


def test_event_type_unknown_value_raises():
    """An unknown wire value is rejected."""
    with pytest.raises(ValueError):
        LifecycleEventType("teleported")


# -- LifecycleEvent ----------------------------------------------------------


def test_event_defaults_are_empty():
    """Only the event type is required; the rest default to empty/None."""
    event = LifecycleEvent(event_type=LifecycleEventType.REGISTERED)
    assert event.actor == ""
    assert event.location == ""
    assert event.note == ""
    assert event.occurred_at is None


def test_event_is_frozen():
    """Events are immutable."""
    event = LifecycleEvent(event_type=LifecycleEventType.IN_USE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.actor = "tamper"  # type: ignore[misc]


def test_event_to_dict_shape_and_timestamp():
    """``to_dict`` emits every field with an ISO-8601 timestamp."""
    event = LifecycleEvent(
        event_type=LifecycleEventType.COLLECTED,
        actor="collector-7",
        location="Bengaluru",
        note="curbside pickup",
        occurred_at=_TS,
    )
    assert event.to_dict() == {
        "event_type": "collected",
        "actor": "collector-7",
        "location": "Bengaluru",
        "note": "curbside pickup",
        "occurred_at": _TS.isoformat(),
    }


def test_event_to_dict_none_timestamp():
    """A clockless event serializes ``occurred_at`` as ``None``."""
    event = LifecycleEvent(event_type=LifecycleEventType.COLLECTED)
    assert event.to_dict()["occurred_at"] is None


def test_event_to_json_is_canonical_and_stable():
    """``to_json`` is deterministic (sorted keys, fixed separators)."""
    event = LifecycleEvent(event_type=LifecycleEventType.ASSESSED, actor="grader")
    first = event.to_json()
    assert first == event.to_json()
    assert '"event_type":"assessed"' in first
    # Compact form has no spaces after separators.
    assert ", " not in first
    assert ": " not in first


def test_event_to_json_indent_is_pretty_but_canonical():
    """Indented output stays canonical (sorted keys)."""
    event = LifecycleEvent(event_type=LifecycleEventType.REGISTERED)
    pretty = event.to_json(indent=2)
    assert "\n" in pretty
    # keys still sorted: actor comes before event_type
    assert pretty.index('"actor"') < pretty.index('"event_type"')


# -- LifecycleRecord ---------------------------------------------------------


def _record(*types: LifecycleEventType, valid: bool = True) -> LifecycleRecord:
    events = tuple(LifecycleEvent(event_type=t) for t in types)
    return LifecycleRecord(
        device_id="ET-PP-0001",
        events=events,
        is_valid=valid,
        event_count=len(events),
        current_state=events[-1].event_type.value if events else None,
        engine_version="1.0.0",
        rules_version="1.0.0",
    )


def test_record_is_frozen():
    """Records are immutable."""
    record = _record(LifecycleEventType.REGISTERED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.is_valid = False  # type: ignore[misc]


def test_record_is_empty_and_event_types():
    """Computed helpers reflect the ordered events."""
    empty = _record()
    assert empty.is_empty is True
    assert empty.event_types == ()
    assert empty.current_state is None

    filled = _record(LifecycleEventType.REGISTERED, LifecycleEventType.IN_USE)
    assert filled.is_empty is False
    assert filled.event_types == ("registered", "in_use")
    assert filled.current_state == "in_use"


def test_record_to_dict_shape():
    """``to_dict`` emits provenance, ordered events and the verdict."""
    record = _record(LifecycleEventType.REGISTERED, LifecycleEventType.COLLECTED)
    data = record.to_dict()
    assert data["device_id"] == "ET-PP-0001"
    assert data["is_valid"] is True
    assert data["event_count"] == 2
    assert data["current_state"] == "collected"
    assert data["engine_version"] == "1.0.0"
    assert data["rules_version"] == "1.0.0"
    assert data["created_at"] is None
    assert [e["event_type"] for e in data["events"]] == ["registered", "collected"]


def test_record_to_json_is_canonical_and_stable():
    """``to_json`` is deterministic across calls."""
    record = _record(LifecycleEventType.REGISTERED)
    assert record.to_json() == record.to_json()
    assert '"device_id":"ET-PP-0001"' in record.to_json()
