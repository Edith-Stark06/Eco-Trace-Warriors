"""External lifecycle transition rules and strict loader (milestone M3.3).

Mirroring the M2.5 trust catalogue and the M3.1 ledger config, the lifecycle
engine's **state machine** lives in an external YAML/JSON file
(``lifecycle/data/transitions.yaml`` by default) rather than in code. That is a
deliberate design choice: *which lifecycle transitions are legal, which events
may start a lifecycle, and which end it* is policy, not logic, so it can be
reviewed, tuned or corrected without touching — or redeploying — the engine.
This module owns the small, strict loader that turns that file into validated,
immutable value objects:

* :class:`LifecycleTransition` — one event type's allowed successor set: from a
  given :class:`~device_ai.lifecycle.models.LifecycleEventType`, which event
  types may legally follow. A terminal event declares an empty successor set.
* :class:`LifecycleRuleSet` — the whole loaded state machine: its version, the
  per-event transitions, and the set of initial (genesis) events a lifecycle may
  legally begin with.

The engine's event types are a **fixed** vocabulary
(:class:`~device_ai.lifecycle.models.LifecycleEventType`) — the rules file may
wire transitions between them but may not invent new ones, so a typo in the file
is caught at load time rather than silently ignored. The loader validates
aggressively (a non-empty version, every event type declared exactly once, no
unknown event-type names, no duplicate successors, a non-empty initial-events
list, and at least one terminal event) and fails with a typed
:class:`~device_ai.exceptions.LifecycleRuleError` on any structural problem, so a
malformed file never silently degrades the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import LifecycleRuleError
from .models import LifecycleEventType

__all__ = [
    "LifecycleRuleSet",
    "LifecycleTransition",
    "load_rules",
]


@dataclass(frozen=True, slots=True)
class LifecycleTransition:
    """One event type's set of legally permitted successor event types.

    Attributes:
        source: The :class:`~device_ai.lifecycle.models.LifecycleEventType` the
            transition is *from*.
        targets: The event types that may legally follow :attr:`source`, in
            declaration order. An empty tuple marks :attr:`source` as a terminal
            event (no event may follow it).
    """

    source: LifecycleEventType
    targets: tuple[LifecycleEventType, ...]

    @property
    def is_terminal(self) -> bool:
        """Return whether this event type permits no successor (a lifecycle end)."""
        return not self.targets

    def allows(self, target: LifecycleEventType) -> bool:
        """Return whether ``target`` may legally follow :attr:`source`."""
        return target in self.targets

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the transition."""
        return {
            "source": self.source.value,
            "targets": [target.value for target in self.targets],
        }


@dataclass(frozen=True, slots=True)
class LifecycleRuleSet:
    """The whole loaded lifecycle state machine.

    Attributes:
        version: Semantic version of the rules file (stamped onto every record).
        transitions: The per-event transitions, one per
            :class:`~device_ai.lifecycle.models.LifecycleEventType`, in canonical
            declaration order.
        initial_events: The event types a lifecycle may legally begin with, in
            declaration order.
    """

    version: str
    transitions: tuple[LifecycleTransition, ...]
    initial_events: tuple[LifecycleEventType, ...]

    @property
    def terminal_events(self) -> tuple[LifecycleEventType, ...]:
        """Return the event types that end a lifecycle (no legal successor)."""
        return tuple(t.source for t in self.transitions if t.is_terminal)

    def transition_for(self, source: LifecycleEventType) -> LifecycleTransition | None:
        """Return the transition declared for ``source`` (``None`` if absent).

        The loader guarantees every event type is declared, so this only returns
        ``None`` for a rule set that was hand-built incompletely in a test.
        """
        for transition in self.transitions:
            if transition.source == source:
                return transition
        return None

    def is_initial(self, event_type: LifecycleEventType) -> bool:
        """Return whether ``event_type`` may legally begin a lifecycle."""
        return event_type in self.initial_events

    def allows(self, source: LifecycleEventType, target: LifecycleEventType) -> bool:
        """Return whether the transition ``source`` → ``target`` is permitted."""
        transition = self.transition_for(source)
        return transition is not None and transition.allows(target)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the rule set."""
        return {
            "version": self.version,
            "transitions": [t.to_dict() for t in self.transitions],
            "initial_events": [e.value for e in self.initial_events],
        }


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`LifecycleRuleError`."""
    if not isinstance(value, dict):
        raise LifecycleRuleError(
            f"Lifecycle rules {where} must be a mapping, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_sequence(value: Any, *, where: str, path: Path) -> list[Any]:
    """Return ``value`` as a list or raise :class:`LifecycleRuleError`.

    Strings and mappings are rejected even though they are iterable — a targets
    or initial-events block must be an explicit sequence.
    """
    if not isinstance(value, list):
        raise LifecycleRuleError(
            f"Lifecycle rules {where} must be a list, got {type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _parse_event_type(value: Any, *, where: str, path: Path) -> LifecycleEventType:
    """Return ``value`` as a :class:`LifecycleEventType` or raise.

    Rejects non-strings and any name outside the fixed event-type vocabulary, so
    a typo in the rules file is a load-time error rather than a silent drop.
    """
    if not isinstance(value, str) or not value.strip():
        raise LifecycleRuleError(
            f"Lifecycle rules {where} needs a non-empty event-type string.",
            details={"path": str(path), "where": where},
        )
    try:
        return LifecycleEventType(value.strip())
    except ValueError as exc:
        raise LifecycleRuleError(
            f"Lifecycle rules {where} names unknown event type {value.strip()!r}. "
            f"Allowed: {LifecycleEventType.values()}.",
            details={"path": str(path), "where": where},
        ) from exc


def _parse_targets(
    raw: Any, *, source: LifecycleEventType, path: Path
) -> tuple[LifecycleEventType, ...]:
    """Validate and build one event type's successor set.

    Rejects a self-loop, a duplicate target, and any unknown event type. An
    empty list is legal — it marks a terminal event.
    """
    where = f"transition '{source.value}'"
    targets_raw = _require_sequence(raw, where=where, path=path)
    targets: list[LifecycleEventType] = []
    for item in targets_raw:
        target = _parse_event_type(item, where=f"{where} target", path=path)
        if target == source:
            raise LifecycleRuleError(
                f"Lifecycle rules {where} declares a self-transition to "
                f"{source.value!r}; an event may not follow itself.",
                details={"path": str(path), "where": where},
            )
        if target in targets:
            raise LifecycleRuleError(
                f"Lifecycle rules {where} declares duplicate target "
                f"{target.value!r}; each successor must be listed once.",
                details={"path": str(path), "where": where},
            )
        targets.append(target)
    return tuple(targets)


def _parse_transitions(raw: Any, *, path: Path) -> tuple[LifecycleTransition, ...]:
    """Validate and build the per-event transitions.

    Requires every :class:`LifecycleEventType` declared exactly once (no unknown
    key, no missing type, no duplicate), and at least one terminal event so a
    lifecycle can legally end. Returns the transitions in canonical event-type
    declaration order for a stable, reproducible rule set.
    """
    mapping = _require_mapping(raw, where="'transitions'", path=path)
    if not mapping:
        raise LifecycleRuleError(
            f"Lifecycle rules '{path}' declares no transitions.",
            details={"path": str(path)},
        )

    by_source: dict[LifecycleEventType, LifecycleTransition] = {}
    for key, value in mapping.items():
        source = _parse_event_type(key, where="'transitions' key", path=path)
        if source in by_source:
            raise LifecycleRuleError(
                f"Lifecycle rules '{path}' declares transition {source.value!r} "
                "more than once.",
                details={"path": str(path), "source": source.value},
            )
        targets = _parse_targets(value, source=source, path=path)
        by_source[source] = LifecycleTransition(source=source, targets=targets)

    missing = [m.value for m in LifecycleEventType if m not in by_source]
    if missing:
        raise LifecycleRuleError(
            f"Lifecycle rules '{path}' is missing transition(s) for {missing}; "
            "every event type must declare its successors (empty for terminal).",
            details={"path": str(path), "missing": missing},
        )
    if not any(t.is_terminal for t in by_source.values()):
        raise LifecycleRuleError(
            f"Lifecycle rules '{path}' declares no terminal event; at least one "
            "event type must have an empty successor set so a lifecycle can end.",
            details={"path": str(path)},
        )
    # Emit in canonical declaration order for a reproducible rule set.
    return tuple(by_source[member] for member in LifecycleEventType)


def _parse_initial_events(raw: Any, *, path: Path) -> tuple[LifecycleEventType, ...]:
    """Validate and build the set of legal genesis events.

    Requires a non-empty list of known event types with no duplicates — every
    lifecycle must begin with one of these.
    """
    events_raw = _require_sequence(raw, where="'initial_events'", path=path)
    if not events_raw:
        raise LifecycleRuleError(
            f"Lifecycle rules '{path}' declares no initial events; a lifecycle "
            "must be able to begin somewhere.",
            details={"path": str(path)},
        )
    events: list[LifecycleEventType] = []
    for item in events_raw:
        event = _parse_event_type(item, where="'initial_events'", path=path)
        if event in events:
            raise LifecycleRuleError(
                f"Lifecycle rules '{path}' lists initial event {event.value!r} "
                "more than once.",
                details={"path": str(path), "event": event.value},
            )
        events.append(event)
    return tuple(events)


def _read_rules(path: Path) -> dict[str, Any]:
    """Parse the rules file (YAML or JSON) into a mapping.

    Raises:
        LifecycleRuleError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise LifecycleRuleError(
            f"Lifecycle rules not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise LifecycleRuleError(
            f"Failed to parse lifecycle rules '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise LifecycleRuleError(
            f"Lifecycle rules are empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def load_rules(path: str | Path) -> LifecycleRuleSet:
    """Load and validate the external lifecycle transition rules.

    Reads the YAML (or JSON) rules file, validates the version, the transitions
    (every event type declared exactly once, no unknown/self/duplicate targets,
    at least one terminal event) and the initial events (a non-empty list of
    known, non-duplicated event types), and builds the immutable
    :class:`LifecycleRuleSet` with transitions in canonical event-type order.

    Args:
        path: Path to the rules file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`LifecycleRuleSet`.

    Raises:
        LifecycleRuleError: If the file is missing/malformed or fails
            validation.
    """
    rules_path = Path(path)
    raw = _read_rules(rules_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise LifecycleRuleError(
            f"Lifecycle rules '{rules_path}' is missing a non-empty 'version'.",
            details={"path": str(rules_path)},
        )

    if "transitions" not in raw:
        raise LifecycleRuleError(
            f"Lifecycle rules '{rules_path}' is missing the required "
            "'transitions' mapping.",
            details={"path": str(rules_path)},
        )
    transitions = _parse_transitions(raw.get("transitions"), path=rules_path)

    if "initial_events" not in raw:
        raise LifecycleRuleError(
            f"Lifecycle rules '{rules_path}' is missing the required "
            "'initial_events' list.",
            details={"path": str(rules_path)},
        )
    initial_events = _parse_initial_events(raw.get("initial_events"), path=rules_path)

    return LifecycleRuleSet(
        version=version,
        transitions=transitions,
        initial_events=initial_events,
    )
