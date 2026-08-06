"""Device lifecycle ledger domain models (milestone M3.3).

The Device Lifecycle Ledger Engine models the **complete lifecycle of a device
as an ordered sequence of immutable events** — from first registration through
use, collection, transport, assessment, refurbishment or recycling, to final
disposal. It sits *above* the M3.1 blockchain ledger core: where the ledger core
chains passport *verdicts*, this engine chains the device's *history*, then hands
the resulting record to the ledger for tamper-evident anchoring (M3.2 backends).

The engine derives **no new inference and collects no new evidence**: it accepts
lifecycle events, validates their ordering against an external state machine, and
composes them into an immutable, canonically serializable record. The value
objects here are the vocabulary of that history:

* :class:`LifecycleEventType` — the fixed vocabulary of lifecycle stages a device
  can move through (registered, in use, collected, recycled, ...). A ``str``
  enum so members serialize to their wire value directly and are the single
  source of truth the external transition rules are validated against.
* :class:`LifecycleEvent` — one immutable event: its type, an optional actor and
  location, an optional free-form note, and an optional timestamp. The atomic
  unit a lifecycle is built from.
* :class:`LifecycleRecord` — the immutable, ordered history: the device id, the
  ordered events, whether the sequence is a valid path through the state machine,
  the current (latest) event type, and provenance (engine/rules versions, an
  optional timestamp).

Every object is a frozen, slotted dataclass with deterministic ``to_dict`` and
``to_json`` serialization, so the same inputs always yield byte-identical output
(modulo optional timestamps). There is no networking, GPS tracking, event
streaming, QR scanning, wallet, digital signature or smart contract here — those
are out of scope for M3.3. The engine is a **local, deterministic data
structure** that models device history and validates it against external rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "LifecycleEvent",
    "LifecycleEventType",
    "LifecycleRecord",
]


class LifecycleEventType(str, Enum):
    """The fixed vocabulary of lifecycle stages a device can move through.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a rules-file string (e.g. ``"collected"``). This enum is
    the single source of truth the external transition rules are validated
    against on load — a rules file naming an event type outside this set is
    rejected.

    The members trace an e-waste device's journey: it is ``REGISTERED`` when its
    passport is first minted, ``IN_USE`` during its service life, ``COLLECTED``
    when handed to a collector, ``IN_TRANSIT`` while moving between facilities,
    ``ASSESSED`` once graded, then either ``REFURBISHED`` (back to use or resale)
    or ``RECYCLED`` (materials recovered), and finally ``DISPOSED`` when it
    reaches end-of-life. The legal *transitions* between these stages are policy,
    defined in the external rules file — this enum only fixes the vocabulary.
    """

    REGISTERED = "registered"
    IN_USE = "in_use"
    COLLECTED = "collected"
    IN_TRANSIT = "in_transit"
    ASSESSED = "assessed"
    REFURBISHED = "refurbished"
    RECYCLED = "recycled"
    DISPOSED = "disposed"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every event type, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """One immutable event in a device's lifecycle.

    The atomic unit a :class:`LifecycleRecord` is built from. It captures *what*
    happened (the :class:`LifecycleEventType`), optionally *who* recorded it and
    *where*, an optional free-form note, and *when* it occurred. Only the event
    type is required; every other field defaults to empty/``None`` so a caller
    can record a bare state transition or a fully annotated one.

    Attributes:
        event_type: The :class:`LifecycleEventType` this event represents.
        actor: Optional identifier of the party that recorded the event (an
            operator, a facility, a collector). Empty string when unknown.
        location: Optional human-readable location the event occurred at (a
            city, a facility name). Empty string when unknown. This is a free
            text label only — the engine performs no GPS tracking.
        note: Optional free-form annotation for the event. Empty string when
            none.
        occurred_at: UTC timestamp the event occurred (``None`` when the service
            was constructed without a clock, keeping the event a pure function
            of its inputs).
    """

    event_type: LifecycleEventType
    actor: str = ""
    location: str = ""
    note: str = ""
    occurred_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the event.

        The keys are emitted in a fixed, logical order, so the mapping is a
        deterministic function of the inputs (the only source of variation is
        the optional ``occurred_at`` timestamp).

        Returns:
            A plain ``dict`` with the event type, actor, location, note and an
            ISO-8601 ``occurred_at`` (or ``None``).
        """
        return {
            "event_type": self.event_type.value,
            "actor": self.actor,
            "location": self.location,
            "note": self.note,
            "occurred_at": (
                self.occurred_at.isoformat() if self.occurred_at is not None else None
            ),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the event.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same event always serializes to the exact
        same bytes. Because :meth:`to_dict` is a pure function of the inputs,
        the only source of variation is the optional ``occurred_at`` timestamp.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    """The immutable, ordered lifecycle history of one device.

    Produced by the :class:`~device_ai.lifecycle.engine.LifecycleEngine` from an
    ordered sequence of :class:`LifecycleEvent` objects validated against the
    external transition rules. It is a **deterministic data structure** — given
    the same events in the same order it always serializes identically (modulo
    optional timestamps) — and it is what the
    :class:`~device_ai.lifecycle.service.LifecycleService` hands to the ledger
    for tamper-evident anchoring.

    Attributes:
        device_id: The id of the device whose lifecycle this record captures
            (typically the passport id that anchors the device identity).
        events: The ordered lifecycle events, from the genesis event onward.
        is_valid: Whether the event sequence is a valid path through the state
            machine (the first event is an initial event, every transition is
            declared legal, and no event follows a terminal one).
        event_count: Number of events in the record.
        current_state: Wire value of the latest event's type (the device's
            current lifecycle stage), or ``None`` when the record is empty.
        engine_version: Version of the lifecycle engine that produced this.
        rules_version: Version of the external transition-rules file used.
        created_at: UTC timestamp the record was assembled (``None`` when the
            service was constructed without a clock).
    """

    device_id: str
    events: tuple[LifecycleEvent, ...]
    is_valid: bool
    event_count: int
    current_state: str | None = None
    engine_version: str = ""
    rules_version: str = ""
    created_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        """Return whether the record holds no events."""
        return not self.events

    @property
    def event_types(self) -> tuple[str, ...]:
        """Return the ordered wire values of every event's type."""
        return tuple(event.event_type.value for event in self.events)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the lifecycle record.

        The keys are emitted in a fixed, logical order, so the mapping is a
        deterministic function of the inputs (the only source of variation is
        the optional ``created_at`` timestamp).

        Returns:
            A plain ``dict`` with the device id, the ordered events, the
            validation status, event count, current state, provenance versions
            and an ISO-8601 ``created_at`` (or ``None``).
        """
        return {
            "device_id": self.device_id,
            "events": [event.to_dict() for event in self.events],
            "is_valid": self.is_valid,
            "event_count": self.event_count,
            "current_state": self.current_state,
            "engine_version": self.engine_version,
            "rules_version": self.rules_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the lifecycle record.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same record always serializes to the exact
        same bytes. Because :meth:`to_dict` is a pure function of the inputs,
        the only source of variation is the optional ``created_at`` timestamp.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )
