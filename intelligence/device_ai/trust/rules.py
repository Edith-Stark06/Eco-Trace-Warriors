"""External trust catalogue and strict loader (milestone M2.5).

Mirroring the M2.4 integrity rule-set, the M2.2 circular rule catalogue and the
M2.1 knowledge catalogue, the trust engine's **scoring policy** lives in an
external YAML/JSON file (``trust/data/rules.yaml`` by default) rather than in
code. That is a deliberate design choice: *how much each trust sub-axis weighs,
and the score thresholds that map onto each trust level* is policy, not logic,
so it can be reviewed, tuned or corrected without touching — or redeploying —
the engine. This module owns the small, strict loader that turns that file into
validated, immutable value objects:

* :class:`AxisWeight` — one trust sub-axis's non-negative blend weight. The
  trust score is the weighted average of the four axes' ``[0, 1]`` values, so a
  weight is how much that axis moves the score.
* :class:`TrustLevelRule` — one trust level's inclusive score floor: a passport
  whose score is at or above ``min_score`` (and below the next-higher level's
  floor) maps to this level. The lowest level's floor is ``0.0`` so every score
  resolves.
* :class:`TrustRuleSet` — the whole loaded catalogue: its version, the per-axis
  weights and the ordered trust levels (sorted by descending floor).

The engine's sub-axes are a **fixed** vocabulary (:data:`CANONICAL_AXES`) and
its trust levels a fixed set (:class:`~device_ai.trust.models.TrustLevel`) — the
catalogue may weight and threshold them but may not invent new ones, so a typo
in the file is caught at load time rather than silently ignored. The loader
validates aggressively (a non-empty version, all four axes weighted, a positive
total weight, all four levels declared exactly once with in-range floors and a
``0.0`` floor covering the bottom of the range) and fails with a typed
:class:`~device_ai.exceptions.PassportTrustRuleError` on any structural problem,
so a malformed catalogue never silently degrades the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import PassportTrustRuleError
from .models import TrustLevel

# The canonical trust sub-axes the engine projects from the four upstream
# inputs. The catalogue must weight each of these and may not name any other —
# an unknown axis, or an omitted one, is a load-time error. Kept here as the
# single source of truth shared by the loader and the engine.
CANONICAL_AXES: frozenset[str] = frozenset(
    {
        "identity_confidence",
        "evidence_consistency",
        "decision_confidence",
        "integrity_confidence",
    }
)

__all__ = [
    "CANONICAL_AXES",
    "AxisWeight",
    "TrustLevelRule",
    "TrustRuleSet",
    "load_rules",
]


@dataclass(frozen=True, slots=True)
class AxisWeight:
    """One trust sub-axis's non-negative blend weight.

    Attributes:
        axis: The canonical axis name (one of :data:`CANONICAL_AXES`).
        weight: The non-negative weight this axis carries within the trust
            score's weighted average.
    """

    axis: str
    weight: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the axis weight."""
        return {"axis": self.axis, "weight": self.weight}


@dataclass(frozen=True, slots=True)
class TrustLevelRule:
    """One trust level's inclusive score floor.

    Attributes:
        level: The :class:`~device_ai.trust.models.TrustLevel` this rule maps to.
        min_score: The inclusive ``[0, 1]`` score floor: a passport whose score
            is at or above this (and below the next-higher level's floor) maps
            to :attr:`level`.
    """

    level: TrustLevel
    min_score: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the level rule."""
        return {"level": self.level.value, "min_score": self.min_score}


@dataclass(frozen=True, slots=True)
class TrustRuleSet:
    """The whole loaded trust catalogue.

    Attributes:
        version: Semantic version of the catalogue (stamped onto every report).
        weights: The per-axis blend weights, in canonical-axis declaration
            order.
        levels: The trust levels, sorted by descending score floor (most
            trustworthy first).
    """

    version: str
    weights: tuple[AxisWeight, ...]
    levels: tuple[TrustLevelRule, ...]

    @property
    def axis_names(self) -> tuple[str, ...]:
        """Return the weighted axis names, in declaration order."""
        return tuple(weight.axis for weight in self.weights)

    @property
    def total_weight(self) -> float:
        """Return the sum of every axis weight (always positive)."""
        return sum(weight.weight for weight in self.weights)

    @property
    def level_count(self) -> int:
        """Return the number of trust levels the catalogue declares."""
        return len(self.levels)

    def weight_for(self, axis: str) -> float:
        """Return the blend weight for ``axis`` (``0.0`` when absent)."""
        for weight in self.weights:
            if weight.axis == axis:
                return weight.weight
        return 0.0

    def level_for(self, score: float) -> TrustLevel:
        """Return the trust level a ``score`` maps to.

        The levels are sorted by descending floor, so the first level whose
        floor the score meets or exceeds wins. Because the loader guarantees a
        level with a ``0.0`` floor, every score in ``[0, 1]`` resolves.

        Args:
            score: The normalized ``[0, 1]`` trust score.

        Returns:
            The matching :class:`~device_ai.trust.models.TrustLevel`.
        """
        for rule in self.levels:
            if score >= rule.min_score:
                return rule.level
        # Unreachable given the loader's 0.0-floor guarantee; the lowest level
        # is the safe fallback.
        return self.levels[-1].level


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`PassportTrustRuleError`."""
    if not isinstance(value, dict):
        raise PassportTrustRuleError(
            f"Trust catalogue {where} must be a mapping, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_sequence(value: Any, *, where: str, path: Path) -> list[Any]:
    """Return ``value`` as a list or raise :class:`PassportTrustRuleError`.

    Strings and mappings are rejected even though they are iterable — a levels
    block must be an explicit sequence.
    """
    if not isinstance(value, list):
        raise PassportTrustRuleError(
            f"Trust catalogue {where} must be a list, got {type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_str(value: Any, *, field: str, where: str, path: Path) -> str:
    """Return a non-empty string field or raise :class:`PassportTrustRuleError`."""
    if not isinstance(value, str) or not value.strip():
        raise PassportTrustRuleError(
            f"Trust catalogue {where} needs a non-empty '{field}' string.",
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
) -> float:
    """Validate and return one numeric catalogue value within ``[min, max]``.

    Rejects booleans (``bool`` is an ``int`` subclass but never a valid number)
    and non-numerics, then enforces the inclusive bounds.

    Raises:
        PassportTrustRuleError: If the value is non-numeric or out of range.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise PassportTrustRuleError(
            f"Trust catalogue {where} needs a numeric '{field}'.",
            details={"path": str(path), "where": where, "field": field},
        )
    number = float(value)
    if number < minimum or number > maximum:
        raise PassportTrustRuleError(
            f"Trust catalogue {where} field '{field}' must be within "
            f"[{minimum}, {maximum}], got {number}.",
            details={"path": str(path), "where": where, "field": field},
        )
    return number


def _parse_weights(raw: Any, *, path: Path) -> tuple[AxisWeight, ...]:
    """Validate and build the per-axis blend weights.

    Requires every canonical axis to be weighted exactly once, rejects any
    unknown axis, and enforces a positive total weight so the weighted average
    is well-defined.
    """
    mapping = _require_mapping(raw, where="'weights'", path=path)
    if not mapping:
        raise PassportTrustRuleError(
            f"Trust catalogue '{path}' declares no axis weights.",
            details={"path": str(path)},
        )

    weights: list[AxisWeight] = []
    for axis, value in mapping.items():
        axis_name = str(axis)
        if axis_name not in CANONICAL_AXES:
            raise PassportTrustRuleError(
                f"Trust catalogue 'weights' names unknown axis {axis_name!r}. "
                f"Allowed: {sorted(CANONICAL_AXES)}.",
                details={"path": str(path), "axis": axis_name},
            )
        weight = _parse_number(
            value,
            field=axis_name,
            where="'weights'",
            path=path,
            minimum=0.0,
            maximum=1.0,
        )
        weights.append(AxisWeight(axis=axis_name, weight=weight))

    present = {weight.axis for weight in weights}
    missing = sorted(CANONICAL_AXES - present)
    if missing:
        raise PassportTrustRuleError(
            f"Trust catalogue 'weights' is missing required axis/axes {missing}.",
            details={"path": str(path), "missing": missing},
        )
    if sum(weight.weight for weight in weights) <= 0.0:
        raise PassportTrustRuleError(
            f"Trust catalogue '{path}' weights sum to zero; at least one axis "
            "must carry a positive weight.",
            details={"path": str(path)},
        )
    # Emit in canonical declaration order for a stable, reproducible report.
    order = (
        "identity_confidence",
        "evidence_consistency",
        "decision_confidence",
        "integrity_confidence",
    )
    by_axis = {weight.axis: weight for weight in weights}
    return tuple(by_axis[axis] for axis in order)


def _parse_level(raw: Any, *, index: int, path: Path) -> TrustLevelRule:
    """Validate and build one :class:`TrustLevelRule`."""
    where = f"level #{index}"
    mapping = _require_mapping(raw, where=where, path=path)
    level_text = _require_str(
        mapping.get("level"), field="level", where=where, path=path
    )
    try:
        level = TrustLevel(level_text)
    except ValueError as exc:
        raise PassportTrustRuleError(
            f"Trust catalogue {where} names unknown level {level_text!r}. "
            f"Allowed: {TrustLevel.values()}.",
            details={"path": str(path), "where": where, "field": "level"},
        ) from exc
    min_score = _parse_number(
        mapping.get("min_score"),
        field="min_score",
        where=f"level '{level_text}'",
        path=path,
        minimum=0.0,
        maximum=1.0,
    )
    return TrustLevelRule(level=level, min_score=min_score)


def _parse_levels(raw: Any, *, path: Path) -> tuple[TrustLevelRule, ...]:
    """Validate and build the ordered trust levels.

    Requires every :class:`~device_ai.trust.models.TrustLevel` declared exactly
    once and a ``0.0`` floor so every score resolves; returns the levels sorted
    by descending floor (most trustworthy first).
    """
    levels_raw = _require_sequence(raw, where="'levels'", path=path)
    if not levels_raw:
        raise PassportTrustRuleError(
            f"Trust catalogue '{path}' declares no trust levels.",
            details={"path": str(path)},
        )

    levels = [
        _parse_level(item, index=index, path=path)
        for index, item in enumerate(levels_raw)
    ]

    seen: set[TrustLevel] = set()
    for rule in levels:
        if rule.level in seen:
            raise PassportTrustRuleError(
                f"Trust catalogue '{path}' has a duplicate level "
                f"{rule.level.value!r}; each level must be declared once.",
                details={"path": str(path), "level": rule.level.value},
            )
        seen.add(rule.level)

    missing = sorted(member.value for member in TrustLevel if member not in seen)
    if missing:
        raise PassportTrustRuleError(
            f"Trust catalogue '{path}' is missing required level(s) {missing}; "
            "every trust level must be declared.",
            details={"path": str(path), "missing": missing},
        )
    if not any(rule.min_score == 0.0 for rule in levels):
        raise PassportTrustRuleError(
            f"Trust catalogue '{path}' has no level with a 0.0 floor; the levels "
            "must cover the bottom of the score range so every score resolves.",
            details={"path": str(path)},
        )

    return tuple(sorted(levels, key=lambda rule: rule.min_score, reverse=True))


def _read_catalogue(path: Path) -> dict[str, Any]:
    """Parse the catalogue file (YAML or JSON) into a mapping.

    Raises:
        PassportTrustRuleError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise PassportTrustRuleError(
            f"Trust catalogue not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise PassportTrustRuleError(
            f"Failed to parse trust catalogue '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise PassportTrustRuleError(
            f"Trust catalogue is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def load_rules(path: str | Path) -> TrustRuleSet:
    """Load and validate the external trust catalogue.

    Reads the YAML (or JSON) catalogue, validates the version, the per-axis
    weights (all four canonical axes weighted, no unknown axis, a positive
    total) and the trust levels (all four declared exactly once, in-range
    floors, a ``0.0`` floor), and builds the immutable :class:`TrustRuleSet`
    with levels sorted by descending floor.

    Args:
        path: Path to the catalogue file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`TrustRuleSet`.

    Raises:
        PassportTrustRuleError: If the file is missing/malformed or fails
            validation.
    """
    catalogue_path = Path(path)
    raw = _read_catalogue(catalogue_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise PassportTrustRuleError(
            f"Trust catalogue '{catalogue_path}' is missing a non-empty " "'version'.",
            details={"path": str(catalogue_path)},
        )

    if "weights" not in raw:
        raise PassportTrustRuleError(
            f"Trust catalogue '{catalogue_path}' is missing the required "
            "'weights' mapping.",
            details={"path": str(catalogue_path)},
        )
    weights = _parse_weights(raw.get("weights"), path=catalogue_path)

    if "levels" not in raw:
        raise PassportTrustRuleError(
            f"Trust catalogue '{catalogue_path}' is missing the required "
            "'levels' list.",
            details={"path": str(catalogue_path)},
        )
    levels = _parse_levels(raw.get("levels"), path=catalogue_path)

    return TrustRuleSet(version=version, weights=weights, levels=levels)
