"""External decision-knowledge catalogue and loader (milestone M2.1).

Mirroring the M1.11 environmental catalogue, the decision engine's knowledge
lives in an **external** YAML/JSON file (``decision/data/knowledge.yaml`` by
default) rather than in code. That is a deliberate design choice: *how much each
piece of upstream evidence weighs* toward each decision dimension is knowledge,
not logic, so it can be reviewed, tuned or corrected without touching — or
redeploying — the engine. This module owns the small, strict loader that turns
that file into validated, immutable value objects:

* :class:`Normalization` — the saturation constants that map the environmental
  engine's *unbounded physical* quantities (kg CO₂e, MJ, L, kg recovered) onto a
  normalized ``[0, 1]`` signal, so they can be blended with the already-normalized
  scores.
* :class:`KnowledgeBase` — the whole loaded catalogue: its version, the
  per-dimension ``signal → weight`` maps, the ``confidence source → weight`` map
  and the normalization constants.

The engine's input signals and confidence sources are a **fixed** vocabulary
(:data:`CANONICAL_SIGNALS` and :data:`CONFIDENCE_SOURCES`) — the catalogue may
re-weight them but may not invent new ones, so a typo in the file is caught at
load time rather than silently ignored. The loader validates aggressively and
fails with a typed :class:`~device_ai.exceptions.DecisionKnowledgeError` on any
structural problem, so a malformed catalogue never silently degrades the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import DecisionKnowledgeError
from .models import DecisionDimension

# The canonical normalized input signals the inference engine projects from the
# upstream reports. The catalogue may weight these but may not name any other —
# an unknown signal in a dimension's weight map is a load-time error. Kept here
# as the single source of truth shared by the loader and the inference engine.
CANONICAL_SIGNALS: frozenset[str] = frozenset(
    {
        "repairability",
        "reusability",
        "recyclability",
        "circularity_index",
        "hazard_severity",
        "hazard_reduction",
        "hazardous_mass_fraction",
        "critical_material_presence",
        "recoverable_mass_fraction",
        "environmental_savings",
        "identity_completeness",
    }
)

# The canonical upstream confidence sources blended into the report's separate
# overall-confidence axis. The catalogue may weight these but may not name any
# other. Single source of truth shared by the loader and the inference engine.
CONFIDENCE_SOURCES: frozenset[str] = frozenset(
    {
        "recoverability",
        "components",
        "materials",
        "environmental",
        "fusion",
    }
)

# The saturation constants the normalization block must supply, mapped to the
# attribute they populate. Each must be a strictly-positive number (it is a
# divisor). Single source of truth for the loader and the error messages.
_NORMALIZATION_FIELDS: dict[str, str] = {
    "carbon_saturation_kg": "carbon_saturation_kg",
    "energy_saturation_mj": "energy_saturation_mj",
    "water_saturation_l": "water_saturation_l",
    "critical_recovery_saturation_kg": "critical_recovery_saturation_kg",
}


@dataclass(frozen=True, slots=True)
class Normalization:
    """Saturation constants mapping unbounded physical amounts onto ``[0, 1]``.

    The environmental engine reports real physical quantities (carbon, energy,
    water saved and critical material recovered) that have no natural upper
    bound, so they cannot be blended directly with the normalized upstream
    scores. Each is divided by its saturation constant and clamped to ``[0, 1]``:
    the constant is the amount at which the signal is considered "as high as it
    gets" for weighting purposes. The constants are catalogue data so they can be
    tuned without a code change.

    Attributes:
        carbon_saturation_kg: kg CO₂e saved at which the carbon signal saturates.
        energy_saturation_mj: MJ saved at which the energy signal saturates.
        water_saturation_l: litres saved at which the water signal saturates.
        critical_recovery_saturation_kg: kg of critical material recovered at
            which the critical-material signal saturates.
    """

    carbon_saturation_kg: float
    energy_saturation_mj: float
    water_saturation_l: float
    critical_recovery_saturation_kg: float


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    """The whole loaded decision-knowledge catalogue.

    Attributes:
        version: Semantic version of the catalogue (stamped onto every report).
        dimensions: Per-dimension ``signal name → weight`` maps, one entry per
            :class:`DecisionDimension`. Every signal name is in
            :data:`CANONICAL_SIGNALS`; every weight is non-negative.
        confidence_weights: ``confidence source → weight`` map over
            :data:`CONFIDENCE_SOURCES`; every weight is non-negative and at least
            one is positive.
        normalization: The saturation constants for the physical signals.
    """

    version: str
    dimensions: dict[DecisionDimension, dict[str, float]]
    confidence_weights: dict[str, float]
    normalization: Normalization

    def weights_for(self, dimension: DecisionDimension) -> dict[str, float]:
        """Return the ``signal → weight`` map for ``dimension``.

        Args:
            dimension: The decision dimension to read weights for.

        Returns:
            The dimension's ``signal name → weight`` map (empty when — which the
            loader forbids for the shipped catalogue — a dimension has no
            weights).
        """
        return self.dimensions.get(dimension, {})


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`DecisionKnowledgeError`."""
    if not isinstance(value, dict):
        raise DecisionKnowledgeError(
            f"Decision knowledge {where} must be a mapping, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _parse_number(
    value: Any,
    *,
    field: str,
    where: str,
    path: Path,
    minimum: float,
    allow_equal: bool,
) -> float:
    """Validate and return one numeric catalogue value.

    Rejects booleans (``bool`` is an ``int`` subclass but never a valid weight)
    and non-numerics, then enforces the lower bound.

    Args:
        value: The raw value from the catalogue.
        field: The field name (for error context).
        where: The containing section (for error context).
        path: The catalogue path (for error context).
        minimum: The lower bound the value must respect.
        allow_equal: Whether ``value == minimum`` is permitted.

    Returns:
        The validated value as a ``float``.

    Raises:
        DecisionKnowledgeError: If the value is missing, non-numeric or out of
            range.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise DecisionKnowledgeError(
            f"Decision knowledge {where} needs a numeric '{field}'.",
            details={"path": str(path), "where": where, "field": field},
        )
    number = float(value)
    out_of_range = number < minimum if allow_equal else number <= minimum
    if out_of_range:
        bound = f">= {minimum}" if allow_equal else f"> {minimum}"
        raise DecisionKnowledgeError(
            f"Decision knowledge {where} field '{field}' must be {bound}, "
            f"got {number}.",
            details={"path": str(path), "where": where, "field": field},
        )
    return number


def _parse_weight_map(
    raw: Any,
    *,
    allowed: frozenset[str],
    where: str,
    path: Path,
) -> dict[str, float]:
    """Validate a ``name → weight`` mapping against an allowed vocabulary.

    Every key must be in ``allowed`` and every value a non-negative number. At
    least one weight must be strictly positive, otherwise the mapping would make
    its dimension/confidence identically zero (almost certainly a mistake).

    Args:
        raw: The raw mapping from the catalogue.
        allowed: The permitted key vocabulary.
        where: The containing section (for error context).
        path: The catalogue path (for error context).

    Returns:
        The validated ``name → weight`` map.

    Raises:
        DecisionKnowledgeError: If a key is unknown, a value invalid, or no
            weight is positive.
    """
    mapping = _require_mapping(raw, where=where, path=path)
    if not mapping:
        raise DecisionKnowledgeError(
            f"Decision knowledge {where} defines no weights.",
            details={"path": str(path), "where": where},
        )
    weights: dict[str, float] = {}
    for name, value in mapping.items():
        key = str(name)
        if key not in allowed:
            raise DecisionKnowledgeError(
                f"Decision knowledge {where} names unknown key {key!r}. "
                f"Allowed: {sorted(allowed)}.",
                details={"path": str(path), "where": where, "key": key},
            )
        weights[key] = _parse_number(
            value,
            field=key,
            where=where,
            path=path,
            minimum=0.0,
            allow_equal=True,
        )
    if not any(weight > 0.0 for weight in weights.values()):
        raise DecisionKnowledgeError(
            f"Decision knowledge {where} must have at least one positive weight.",
            details={"path": str(path), "where": where},
        )
    return weights


def _read_catalogue(path: Path) -> dict[str, Any]:
    """Parse the catalogue file (YAML or JSON) into a mapping.

    Args:
        path: The catalogue file to read.

    Returns:
        The parsed top-level mapping.

    Raises:
        DecisionKnowledgeError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise DecisionKnowledgeError(
            f"Decision knowledge catalogue not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise DecisionKnowledgeError(
            f"Failed to parse decision knowledge catalogue '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise DecisionKnowledgeError(
            f"Decision knowledge catalogue is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def _parse_normalization(raw: Any, *, path: Path) -> Normalization:
    """Validate and build the :class:`Normalization` block.

    Args:
        raw: The raw ``normalization`` mapping from the catalogue.
        path: The catalogue path (for error context).

    Returns:
        The validated :class:`Normalization`.

    Raises:
        DecisionKnowledgeError: If a saturation constant is missing or not
            strictly positive.
    """
    mapping = _require_mapping(raw, where="'normalization'", path=path)
    values: dict[str, float] = {}
    for key in _NORMALIZATION_FIELDS:
        values[key] = _parse_number(
            mapping.get(key),
            field=key,
            where="'normalization'",
            path=path,
            minimum=0.0,
            allow_equal=False,
        )
    return Normalization(
        carbon_saturation_kg=values["carbon_saturation_kg"],
        energy_saturation_mj=values["energy_saturation_mj"],
        water_saturation_l=values["water_saturation_l"],
        critical_recovery_saturation_kg=values["critical_recovery_saturation_kg"],
    )


def load_knowledge(path: str | Path) -> KnowledgeBase:
    """Load and validate the external decision-knowledge catalogue.

    Reads the YAML (or JSON) catalogue, validates the version, the normalization
    block, every dimension's weight map (all six dimensions required) and the
    confidence weight map, and builds the immutable :class:`KnowledgeBase`.

    Args:
        path: Path to the catalogue file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`KnowledgeBase`.

    Raises:
        DecisionKnowledgeError: If the file is missing/malformed or fails
            validation.
    """
    catalogue_path = Path(path)
    raw = _read_catalogue(catalogue_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise DecisionKnowledgeError(
            f"Decision knowledge catalogue '{catalogue_path}' is missing a "
            "non-empty 'version'.",
            details={"path": str(catalogue_path)},
        )

    normalization = _parse_normalization(raw.get("normalization"), path=catalogue_path)

    dimensions_raw = _require_mapping(
        raw.get("dimensions", {}), where="'dimensions'", path=catalogue_path
    )
    dimensions: dict[DecisionDimension, dict[str, float]] = {}
    for dimension_value, body in dimensions_raw.items():
        try:
            dimension = DecisionDimension(dimension_value)
        except ValueError as exc:
            raise DecisionKnowledgeError(
                f"Dimensions name unknown decision dimension {dimension_value!r}. "
                f"Allowed: {DecisionDimension.values()}.",
                details={
                    "path": str(catalogue_path),
                    "dimension": str(dimension_value),
                },
            ) from exc
        dimensions[dimension] = _parse_weight_map(
            body,
            allowed=CANONICAL_SIGNALS,
            where=f"dimension '{dimension.value}'",
            path=catalogue_path,
        )

    missing = [member.value for member in DecisionDimension if member not in dimensions]
    if missing:
        raise DecisionKnowledgeError(
            f"Decision knowledge catalogue '{catalogue_path}' is missing weights "
            f"for dimension(s): {missing}.",
            details={"path": str(catalogue_path), "missing": missing},
        )

    confidence_weights = _parse_weight_map(
        raw.get("confidence"),
        allowed=CONFIDENCE_SOURCES,
        where="'confidence'",
        path=catalogue_path,
    )

    return KnowledgeBase(
        version=version,
        dimensions=dimensions,
        confidence_weights=confidence_weights,
        normalization=normalization,
    )
