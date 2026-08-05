"""External circular-decision rule catalogue and loader (milestone M2.2).

Mirroring the M2.1 decision-knowledge catalogue and the M1.11 environmental
catalogue, the circular engine's decision rules live in an **external** YAML/JSON
file (``circular/data/rules.yaml`` by default) rather than in code. That is a
deliberate design choice: *which evidence triggers which recommendation, and in
what order of precedence* is policy, not logic, so it can be reviewed, tuned or
corrected without touching — or redeploying — the engine. This module owns the
small, strict loader that turns that file into validated, immutable value
objects:

* :class:`RuleCondition` — one comparison of a projected ``[0, 1]`` signal
  against a threshold (``gte``/``lte``/``gt``/``lt``). A rule fires only when
  *all* of its conditions hold, so a condition is a plain conjunction term.
* :class:`DecisionRule` — one policy rule: a unique id, a unique precedence
  (lower wins), the action and priority it advises, the conditions that trigger
  it, a human reason, and optional confidence damping / operator warning.
* :class:`DefaultRule` — the required fallback recommendation applied when no
  rule fires, so the engine always yields a defined action and never guesses.
* :class:`RuleCatalogue` — the whole loaded catalogue: its version, the rules
  sorted by ascending precedence, and the default fallback.

The engine's input signals are a **fixed** vocabulary (:data:`CANONICAL_SIGNALS`)
and its operators a fixed set (:data:`CONDITION_OPERATORS`) — the catalogue may
combine them but may not invent new ones, so a typo in the file is caught at load
time rather than silently ignored. The loader validates aggressively (unique ids,
unique precedences, known signals/operators/actions/priorities, in-range
thresholds) and fails with a typed
:class:`~device_ai.exceptions.CircularRuleError` on any structural problem, so
a malformed catalogue never silently degrades the engine.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import CircularRuleError
from .models import Priority, RecommendedAction

# The canonical normalized input signals the engine projects from the four
# upstream inputs. The catalogue may reference these in conditions but may not
# name any other — an unknown signal in a condition is a load-time error. Kept
# here as the single source of truth shared by the loader and the engine.
CANONICAL_SIGNALS: frozenset[str] = frozenset(
    {
        # Consolidated decision-knowledge dimension scores (M2.1).
        "repairability",
        "reusability",
        "recycling",
        "hazard_score",
        "environmental_priority",
        "material_value",
        "decision_confidence",
        # Recoverability assessment (M1.8).
        "hazard_severity",
        "recoverability_confidence",
        "upstream_manual_review",
        "upstream_hazardous_disposal",
        # Environmental impact (M1.11).
        "circularity_index",
        "hazard_reduction",
        "environmental_confidence",
        # Fused device context (M1.7).
        "identity_completeness",
        "conflict",
    }
)

# The comparison operators a rule condition may use, mapped to their predicate.
# A fixed vocabulary so a typo (``ge``) is rejected at load time. Every operator
# compares a projected signal value against a fixed threshold; there is no
# float-equality operator by design (signals are continuous).
_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "gte": lambda value, threshold: value >= threshold,
    "lte": lambda value, threshold: value <= threshold,
    "gt": lambda value, threshold: value > threshold,
    "lt": lambda value, threshold: value < threshold,
}

#: The condition operators the catalogue may use (single source of truth).
CONDITION_OPERATORS: frozenset[str] = frozenset(_OPERATORS)


@dataclass(frozen=True, slots=True)
class RuleCondition:
    """One conjunction term: a projected signal compared to a threshold.

    Attributes:
        signal: The canonical signal name (one of :data:`CANONICAL_SIGNALS`).
        operator: The comparison operator (one of :data:`CONDITION_OPERATORS`).
        threshold: The ``[0, 1]`` value the signal is compared against.
    """

    signal: str
    operator: str
    threshold: float

    def matches(self, signals: Mapping[str, float]) -> bool:
        """Return whether this condition holds for the projected ``signals``.

        A signal the engine did not project is read as ``0.0`` (absent evidence
        contributes nothing), so conditions never raise on a missing signal.

        Args:
            signals: The engine's projected ``signal name → [0, 1] value`` map.

        Returns:
            ``True`` when the comparison holds, else ``False``.
        """
        value = signals.get(self.signal, 0.0)
        return _OPERATORS[self.operator](value, self.threshold)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the condition."""
        return {
            "signal": self.signal,
            "operator": self.operator,
            "threshold": self.threshold,
        }


@dataclass(frozen=True, slots=True)
class DecisionRule:
    """One policy rule that maps matching evidence to a recommendation.

    Attributes:
        rule_id: Unique machine-readable identifier (catalogue provenance).
        precedence: Unique precedence rank; the matching rule with the *lowest*
            precedence wins the recommendation.
        action: The end-of-life action this rule advises when it fires.
        priority: The triage priority this rule advises when it fires.
        reason: Human-readable explanation stamped onto the report when it fires.
        conditions: The conditions that must *all* hold for the rule to fire
            (at least one; a rule with no conditions would be a hidden default).
        confidence_factor: Multiplicative factor in ``(0, 1]`` applied to the
            recommendation confidence when this rule fires (``1.0`` leaves it
            unchanged) — e.g. a low-confidence rule damps it.
        warning: Optional operator-facing caution emitted when the rule fires.
    """

    rule_id: str
    precedence: int
    action: RecommendedAction
    priority: Priority
    reason: str
    conditions: tuple[RuleCondition, ...]
    confidence_factor: float = 1.0
    warning: str | None = None

    def matches(self, signals: Mapping[str, float]) -> bool:
        """Return whether every condition holds for the projected ``signals``.

        Args:
            signals: The engine's projected ``signal name → [0, 1] value`` map.

        Returns:
            ``True`` when all conditions hold (a conjunction), else ``False``.
        """
        return all(condition.matches(signals) for condition in self.conditions)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the rule."""
        return {
            "rule_id": self.rule_id,
            "precedence": self.precedence,
            "action": self.action.value,
            "priority": self.priority.value,
            "reason": self.reason,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "confidence_factor": self.confidence_factor,
            "warning": self.warning,
        }


@dataclass(frozen=True, slots=True)
class DefaultRule:
    """The fallback recommendation applied when no rule fires.

    Attributes:
        action: The action recommended when no rule matched.
        priority: The priority recommended when no rule matched.
        reason: Human-readable explanation stamped onto the report as the
            fallback rationale.
    """

    action: RecommendedAction
    priority: Priority
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the default."""
        return {
            "action": self.action.value,
            "priority": self.priority.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RuleCatalogue:
    """The whole loaded circular-decision rule catalogue.

    Attributes:
        version: Semantic version of the catalogue (stamped onto every report).
        rules: The policy rules, sorted by ascending precedence (winner first).
        default: The fallback recommendation applied when no rule fires.
    """

    version: str
    rules: tuple[DecisionRule, ...]
    default: DefaultRule

    @property
    def rule_count(self) -> int:
        """Return the number of policy rules in the catalogue."""
        return len(self.rules)


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`CircularRuleError`."""
    if not isinstance(value, dict):
        raise CircularRuleError(
            f"Circular rule catalogue {where} must be a mapping, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_sequence(value: Any, *, where: str, path: Path) -> list[Any]:
    """Return ``value`` as a list or raise :class:`CircularRuleError`.

    Strings and mappings are rejected even though they are iterable — a rules
    block must be an explicit sequence.
    """
    if not isinstance(value, list):
        raise CircularRuleError(
            f"Circular rule catalogue {where} must be a list, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_str(value: Any, *, field: str, where: str, path: Path) -> str:
    """Return a non-empty string field or raise :class:`CircularRuleError`."""
    if not isinstance(value, str) or not value.strip():
        raise CircularRuleError(
            f"Circular rule catalogue {where} needs a non-empty '{field}' string.",
            details={"path": str(path), "where": where, "field": field},
        )
    return value.strip()


def _parse_number(
    value: Any,
    *,
    field: str,
    where: str,
    path: Path,
    minimum: float,
    maximum: float,
    allow_equal_min: bool,
) -> float:
    """Validate and return one numeric catalogue value within ``[min, max]``.

    Rejects booleans (``bool`` is an ``int`` subclass but never a valid number)
    and non-numerics, then enforces the inclusive upper bound and the lower bound
    (inclusive when ``allow_equal_min``, else exclusive).

    Args:
        value: The raw value from the catalogue.
        field: The field name (for error context).
        where: The containing section (for error context).
        path: The catalogue path (for error context).
        minimum: The lower bound the value must respect.
        maximum: The inclusive upper bound the value must respect.
        allow_equal_min: Whether ``value == minimum`` is permitted.

    Returns:
        The validated value as a ``float``.

    Raises:
        CircularRuleError: If the value is non-numeric or out of range.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise CircularRuleError(
            f"Circular rule catalogue {where} needs a numeric '{field}'.",
            details={"path": str(path), "where": where, "field": field},
        )
    number = float(value)
    below = number < minimum if allow_equal_min else number <= minimum
    if below or number > maximum:
        low = f">= {minimum}" if allow_equal_min else f"> {minimum}"
        raise CircularRuleError(
            f"Circular rule catalogue {where} field '{field}' must be {low} and "
            f"<= {maximum}, got {number}.",
            details={"path": str(path), "where": where, "field": field},
        )
    return number


def _parse_precedence(value: Any, *, where: str, path: Path) -> int:
    """Validate and return a rule's non-negative integer precedence."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise CircularRuleError(
            f"Circular rule catalogue {where} needs an integer 'precedence'.",
            details={"path": str(path), "where": where, "field": "precedence"},
        )
    if value < 0:
        raise CircularRuleError(
            f"Circular rule catalogue {where} field 'precedence' must be >= 0, "
            f"got {value}.",
            details={"path": str(path), "where": where, "field": "precedence"},
        )
    return value


def _parse_action(value: Any, *, where: str, path: Path) -> RecommendedAction:
    """Validate and return a rule's :class:`RecommendedAction`."""
    text = _require_str(value, field="action", where=where, path=path)
    try:
        return RecommendedAction(text)
    except ValueError as exc:
        allowed = sorted(member.value for member in RecommendedAction)
        raise CircularRuleError(
            f"Circular rule catalogue {where} names unknown action {text!r}. "
            f"Allowed: {allowed}.",
            details={"path": str(path), "where": where, "field": "action"},
        ) from exc


def _parse_priority(value: Any, *, where: str, path: Path) -> Priority:
    """Validate and return a rule's :class:`Priority`."""
    text = _require_str(value, field="priority", where=where, path=path)
    try:
        return Priority(text)
    except ValueError as exc:
        raise CircularRuleError(
            f"Circular rule catalogue {where} names unknown priority {text!r}. "
            f"Allowed: {Priority.values()}.",
            details={"path": str(path), "where": where, "field": "priority"},
        ) from exc


def _parse_condition(raw: Any, *, where: str, path: Path) -> RuleCondition:
    """Validate and build one :class:`RuleCondition`."""
    mapping = _require_mapping(raw, where=where, path=path)
    signal = _require_str(mapping.get("signal"), field="signal", where=where, path=path)
    if signal not in CANONICAL_SIGNALS:
        raise CircularRuleError(
            f"Circular rule catalogue {where} names unknown signal {signal!r}. "
            f"Allowed: {sorted(CANONICAL_SIGNALS)}.",
            details={"path": str(path), "where": where, "field": "signal"},
        )
    operator = _require_str(
        mapping.get("operator"), field="operator", where=where, path=path
    )
    if operator not in CONDITION_OPERATORS:
        raise CircularRuleError(
            f"Circular rule catalogue {where} names unknown operator {operator!r}. "
            f"Allowed: {sorted(CONDITION_OPERATORS)}.",
            details={"path": str(path), "where": where, "field": "operator"},
        )
    threshold = _parse_number(
        mapping.get("threshold"),
        field="threshold",
        where=where,
        path=path,
        minimum=0.0,
        maximum=1.0,
        allow_equal_min=True,
    )
    return RuleCondition(signal=signal, operator=operator, threshold=threshold)


def _parse_rule(raw: Any, *, index: int, path: Path) -> DecisionRule:
    """Validate and build one :class:`DecisionRule`."""
    where = f"rule #{index}"
    mapping = _require_mapping(raw, where=where, path=path)
    rule_id = _require_str(mapping.get("id"), field="id", where=where, path=path)
    where = f"rule '{rule_id}'"
    precedence = _parse_precedence(mapping.get("precedence"), where=where, path=path)
    action = _parse_action(mapping.get("action"), where=where, path=path)
    priority = _parse_priority(mapping.get("priority"), where=where, path=path)
    reason = _require_str(mapping.get("reason"), field="reason", where=where, path=path)

    conditions_raw = _require_sequence(
        mapping.get("when"), where=f"{where} 'when'", path=path
    )
    if not conditions_raw:
        raise CircularRuleError(
            f"Circular rule catalogue {where} defines no 'when' conditions; a "
            "rule must have at least one condition.",
            details={"path": str(path), "where": where},
        )
    conditions = tuple(
        _parse_condition(item, where=f"{where} condition #{position}", path=path)
        for position, item in enumerate(conditions_raw)
    )

    confidence_factor = 1.0
    if "confidence_factor" in mapping:
        confidence_factor = _parse_number(
            mapping.get("confidence_factor"),
            field="confidence_factor",
            where=where,
            path=path,
            minimum=0.0,
            maximum=1.0,
            allow_equal_min=False,
        )
    warning_raw = mapping.get("warning")
    warning = (
        _require_str(warning_raw, field="warning", where=where, path=path)
        if warning_raw is not None
        else None
    )
    return DecisionRule(
        rule_id=rule_id,
        precedence=precedence,
        action=action,
        priority=priority,
        reason=reason,
        conditions=conditions,
        confidence_factor=confidence_factor,
        warning=warning,
    )


def _parse_default(raw: Any, *, path: Path) -> DefaultRule:
    """Validate and build the required :class:`DefaultRule` fallback."""
    where = "'default'"
    mapping = _require_mapping(raw, where=where, path=path)
    return DefaultRule(
        action=_parse_action(mapping.get("action"), where=where, path=path),
        priority=_parse_priority(mapping.get("priority"), where=where, path=path),
        reason=_require_str(
            mapping.get("reason"), field="reason", where=where, path=path
        ),
    )


def _read_catalogue(path: Path) -> dict[str, Any]:
    """Parse the catalogue file (YAML or JSON) into a mapping.

    Args:
        path: The catalogue file to read.

    Returns:
        The parsed top-level mapping.

    Raises:
        CircularRuleError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise CircularRuleError(
            f"Circular rule catalogue not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise CircularRuleError(
            f"Failed to parse circular rule catalogue '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise CircularRuleError(
            f"Circular rule catalogue is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def load_rules(path: str | Path) -> RuleCatalogue:
    """Load and validate the external circular-decision rule catalogue.

    Reads the YAML (or JSON) catalogue, validates the version, every rule (unique
    id, unique precedence, known action/priority/signals/operators, in-range
    thresholds and at least one condition) and the required default fallback, and
    builds the immutable :class:`RuleCatalogue` with rules sorted by ascending
    precedence.

    Args:
        path: Path to the catalogue file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`RuleCatalogue`.

    Raises:
        CircularRuleError: If the file is missing/malformed or fails
            validation.
    """
    catalogue_path = Path(path)
    raw = _read_catalogue(catalogue_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise CircularRuleError(
            f"Circular rule catalogue '{catalogue_path}' is missing a non-empty "
            "'version'.",
            details={"path": str(catalogue_path)},
        )

    rules_raw = _require_sequence(
        raw.get("rules", []), where="'rules'", path=catalogue_path
    )
    if not rules_raw:
        raise CircularRuleError(
            f"Circular rule catalogue '{catalogue_path}' defines no rules.",
            details={"path": str(catalogue_path)},
        )

    rules = [
        _parse_rule(item, index=index, path=catalogue_path)
        for index, item in enumerate(rules_raw)
    ]

    seen_ids: set[str] = set()
    seen_precedences: dict[int, str] = {}
    for rule in rules:
        if rule.rule_id in seen_ids:
            raise CircularRuleError(
                f"Circular rule catalogue '{catalogue_path}' has a duplicate rule "
                f"id {rule.rule_id!r}.",
                details={"path": str(catalogue_path), "rule_id": rule.rule_id},
            )
        seen_ids.add(rule.rule_id)
        if rule.precedence in seen_precedences:
            other = seen_precedences[rule.precedence]
            raise CircularRuleError(
                f"Circular rule catalogue '{catalogue_path}' has a duplicate "
                f"precedence {rule.precedence} shared by {other!r} and "
                f"{rule.rule_id!r}; precedence must be unique so the winning rule "
                "is unambiguous.",
                details={
                    "path": str(catalogue_path),
                    "precedence": rule.precedence,
                },
            )
        seen_precedences[rule.precedence] = rule.rule_id

    if "default" not in raw:
        raise CircularRuleError(
            f"Circular rule catalogue '{catalogue_path}' is missing the required "
            "'default' fallback recommendation.",
            details={"path": str(catalogue_path)},
        )
    default = _parse_default(raw.get("default"), path=catalogue_path)

    ordered = tuple(sorted(rules, key=lambda rule: rule.precedence))
    return RuleCatalogue(version=version, rules=ordered, default=default)
