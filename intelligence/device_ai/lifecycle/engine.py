"""Device lifecycle ledger engine (milestone M3.3).

Deterministic validation and composition over a resolved
:class:`~device_ai.lifecycle.rules.LifecycleRuleSet` and an ordered sequence of
:class:`~device_ai.lifecycle.models.LifecycleEvent` objects. There is no model
and no I/O here — given the same events in the same order the engine always
produces the same :class:`~device_ai.lifecycle.models.LifecycleRecord`, which is
what makes the lifecycle history auditable and reproducible.

The evaluation has two clean stages:

1. **Validate** the event sequence against the state machine: the first event
   must be a declared initial (genesis) event, every subsequent event must be a
   legal successor of its predecessor, and no event may follow a terminal one.
   Any violation is reported as ``is_valid=False`` on the record (never raised)
   — a rejected history is data, not an engine fault.
2. **Compose** the validated events into an immutable
   :class:`~device_ai.lifecycle.models.LifecycleRecord`, capturing the device
   id, the ordered events, the validity verdict, the event count, the current
   (latest) state and provenance versions.

The engine performs no new inference, no evidence collection, no networking, no
GPS tracking and no persistence — it validates and composes device history. An
empty event sequence is a valid, empty record; a single genesis event is a valid
one-event record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import LifecycleRecord

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from .models import LifecycleEvent
    from .rules import LifecycleRuleSet


class LifecycleEngine:
    """Validate and compose device lifecycle event histories into records."""

    def validate(
        self,
        events: Sequence[LifecycleEvent],
        rules: LifecycleRuleSet,
    ) -> bool:
        """Return whether an ordered event sequence is a legal lifecycle path.

        Checks three things against the state machine: the first event is a
        declared initial (genesis) event, every subsequent event is a legal
        successor of its predecessor, and no event follows a terminal one. An
        empty sequence is trivially valid (an empty lifecycle).

        Args:
            events: The ordered lifecycle events, from genesis onward.
            rules: The resolved :class:`~device_ai.lifecycle.rules.LifecycleRuleSet`.

        Returns:
            ``True`` when the sequence is a valid path, ``False`` otherwise.
        """
        if not events:
            return True

        if not rules.is_initial(events[0].event_type):
            return False

        for previous, current in zip(events, events[1:], strict=False):
            transition = rules.transition_for(previous.event_type)
            # A terminal event (no declared successors) admits nothing after it,
            # and an undeclared source (hand-built test rule set) never permits.
            if transition is None or not transition.allows(current.event_type):
                return False

        return True

    def build_record(
        self,
        device_id: str,
        events: Sequence[LifecycleEvent],
        rules: LifecycleRuleSet,
        *,
        rules_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> LifecycleRecord:
        """Validate an event sequence and compose it into a lifecycle record.

        Runs :meth:`validate` over the events, then snapshots them into an
        immutable :class:`~device_ai.lifecycle.models.LifecycleRecord` with the
        validity verdict, the event count, the current (latest) state and
        provenance. A rejected sequence still produces a record — with
        ``is_valid=False`` — so callers can inspect *why* it failed rather than
        catching an exception.

        Args:
            device_id: The id of the device this lifecycle belongs to.
            events: The ordered lifecycle events, from genesis onward.
            rules: The resolved :class:`~device_ai.lifecycle.rules.LifecycleRuleSet`.
            rules_version: Version of the rules file, stamped onto the record.
            engine_version: Version of this engine, stamped onto the record.
            created_at: Record timestamp, or ``None``.

        Returns:
            The immutable :class:`~device_ai.lifecycle.models.LifecycleRecord`.
        """
        ordered = tuple(events)
        is_valid = self.validate(ordered, rules)
        current_state = ordered[-1].event_type.value if ordered else None
        return LifecycleRecord(
            device_id=device_id,
            events=ordered,
            is_valid=is_valid,
            event_count=len(ordered),
            current_state=current_state,
            engine_version=engine_version,
            rules_version=rules_version,
            created_at=created_at,
        )

    def can_append(
        self,
        record: LifecycleRecord,
        next_event: LifecycleEvent,
        rules: LifecycleRuleSet,
    ) -> bool:
        """Return whether ``next_event`` may legally extend ``record``.

        A convenience predicate for callers building a lifecycle incrementally:
        an empty record accepts any initial (genesis) event; a non-empty record
        accepts an event only when it is a declared successor of the record's
        current (latest) event type.

        Args:
            record: The existing
                :class:`~device_ai.lifecycle.models.LifecycleRecord`.
            next_event: The candidate
                :class:`~device_ai.lifecycle.models.LifecycleEvent`.
            rules: The resolved
                :class:`~device_ai.lifecycle.rules.LifecycleRuleSet`.

        Returns:
            ``True`` when appending ``next_event`` keeps the lifecycle valid.
        """
        if record.is_empty:
            return rules.is_initial(next_event.event_type)
        last_type = record.events[-1].event_type
        return rules.allows(last_type, next_event.event_type)
