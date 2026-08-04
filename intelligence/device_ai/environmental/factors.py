"""External environmental conversion-factor library and loader (M1.11).

Mirroring the M1.10 material catalogue, the environmental knowledge lives in an
**external** YAML/JSON file (``environmental/data/factors.yaml`` by default)
rather than in code. That is a deliberate design choice: the conversion factors
are data, not logic, so they can be reviewed, extended or corrected (as
life-cycle-assessment sources improve) without touching — or redeploying — the
engine. This module owns the small, strict loader that turns that file into
validated, immutable value objects:

* :class:`MaterialFactor` — the per-kilogram avoided burden of recovering one
  :class:`~device_ai.materials.models.MaterialCategory` rather than producing it
  from virgin feedstock: kilograms of CO₂e, megajoules of primary energy and
  litres of freshwater saved, plus whether the category counts as a *critical*
  material.
* :class:`FactorLibrary` — the whole loaded catalogue: its version, the
  per-category factors and the conservative ``default`` factor applied to any
  category the catalogue does not name. :meth:`FactorLibrary.factor_for`
  resolves a category to a factor, never failing for a category outside the
  catalogue.

The loader validates aggressively and fails with a typed
:class:`~device_ai.exceptions.EnvironmentalFactorError` on any structural
problem, so a malformed catalogue never silently degrades the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import EnvironmentalFactorError
from ..materials.models import MaterialCategory

# The three numeric conversion factors every entry must supply, mapped to the
# attribute they populate. Kept as the single source of truth so the loader and
# the error messages agree on the accepted keys and their meaning.
_NUMERIC_FIELDS: dict[str, str] = {
    "carbon_kg_per_kg": "carbon_saved_kg",
    "energy_mj_per_kg": "energy_saved_mj",
    "water_l_per_kg": "water_saved_l",
}


@dataclass(frozen=True, slots=True)
class MaterialFactor:
    """The per-kilogram avoided environmental burden of one material category.

    Attributes:
        category: The :class:`MaterialCategory` this factor applies to.
        carbon_kg_per_kg: Kilograms of CO₂e avoided per kilogram recovered.
        energy_mj_per_kg: Megajoules of primary energy avoided per kilogram.
        water_l_per_kg: Litres of freshwater avoided per kilogram.
        critical: Whether recovering this category counts toward critical-material
            recovery (precious metals, critical materials, rare earths).
        notes: Short human-readable rationale/source (provenance; not scored).
    """

    category: MaterialCategory
    carbon_kg_per_kg: float
    energy_mj_per_kg: float
    water_l_per_kg: float
    critical: bool = False
    notes: str = ""


@dataclass(frozen=True, slots=True)
class FactorLibrary:
    """The whole loaded environmental conversion-factor catalogue.

    Attributes:
        version: Semantic version of the catalogue (stamped onto every report).
        factors: Per-category factors keyed by :class:`MaterialCategory`.
        default: Conservative fallback factor applied to any category the
            catalogue does not explicitly name, so a newly added material
            category never crashes the engine.
    """

    version: str
    factors: dict[MaterialCategory, MaterialFactor]
    default: MaterialFactor

    def factor_for(self, category: MaterialCategory) -> MaterialFactor:
        """Resolve the :class:`MaterialFactor` for a material category.

        Categories the catalogue does not name resolve to the conservative
        ``default`` factor (re-stamped with the requested category), so the
        lookup never fails.

        Args:
            category: The material category to resolve a factor for.

        Returns:
            The matching :class:`MaterialFactor`, or the default fallback.
        """
        factor = self.factors.get(category)
        if factor is not None:
            return factor
        return MaterialFactor(
            category=category,
            carbon_kg_per_kg=self.default.carbon_kg_per_kg,
            energy_mj_per_kg=self.default.energy_mj_per_kg,
            water_l_per_kg=self.default.water_l_per_kg,
            critical=self.default.critical,
            notes=self.default.notes,
        )


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`EnvironmentalFactorError`."""
    if not isinstance(value, dict):
        raise EnvironmentalFactorError(
            f"Environmental factor {where} must be a mapping, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _parse_factor(
    category: MaterialCategory,
    raw: Any,
    *,
    path: Path,
) -> MaterialFactor:
    """Validate and build one :class:`MaterialFactor` from a raw mapping.

    Args:
        category: The material category the factor applies to.
        raw: The raw factor entry from the catalogue.
        path: The catalogue path (for error context).

    Returns:
        The validated :class:`MaterialFactor`.

    Raises:
        EnvironmentalFactorError: If a required field is missing or invalid.
    """
    entry = _require_mapping(raw, where=f"'{category.value}' factor", path=path)

    values: dict[str, float] = {}
    for key in _NUMERIC_FIELDS:
        number = entry.get(key)
        if not isinstance(number, int | float) or isinstance(number, bool):
            raise EnvironmentalFactorError(
                f"Factor '{category.value}' needs a numeric '{key}'.",
                details={"path": str(path), "category": category.value},
            )
        if float(number) < 0.0:
            raise EnvironmentalFactorError(
                f"Factor '{category.value}' has negative '{key}' {number}.",
                details={"path": str(path), "category": category.value},
            )
        values[key] = float(number)

    return MaterialFactor(
        category=category,
        carbon_kg_per_kg=values["carbon_kg_per_kg"],
        energy_mj_per_kg=values["energy_mj_per_kg"],
        water_l_per_kg=values["water_l_per_kg"],
        critical=bool(entry.get("critical", False)),
        notes=str(entry.get("notes", "")),
    )


def _read_catalogue(path: Path) -> dict[str, Any]:
    """Parse the catalogue file (YAML or JSON) into a mapping.

    Args:
        path: The catalogue file to read.

    Returns:
        The parsed top-level mapping.

    Raises:
        EnvironmentalFactorError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise EnvironmentalFactorError(
            f"Environmental factor library not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise EnvironmentalFactorError(
            f"Failed to parse environmental factor library '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise EnvironmentalFactorError(
            f"Environmental factor library is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def load_library(path: str | Path) -> FactorLibrary:
    """Load and validate the external environmental conversion-factor library.

    Reads the YAML (or JSON) catalogue, validates every factor and the required
    ``default`` fallback, and builds the immutable :class:`FactorLibrary`.

    Args:
        path: Path to the catalogue file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`FactorLibrary`.

    Raises:
        EnvironmentalFactorError: If the file is missing/malformed or fails
            validation.
    """
    catalogue_path = Path(path)
    raw = _read_catalogue(catalogue_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise EnvironmentalFactorError(
            f"Environmental factor library '{catalogue_path}' is missing a "
            "non-empty 'version'.",
            details={"path": str(catalogue_path)},
        )

    factors_raw = _require_mapping(
        raw.get("factors", {}), where="'factors'", path=catalogue_path
    )
    if not factors_raw:
        raise EnvironmentalFactorError(
            f"Environmental factor library '{catalogue_path}' defines no factors.",
            details={"path": str(catalogue_path)},
        )

    factors: dict[MaterialCategory, MaterialFactor] = {}
    for category_value, body in factors_raw.items():
        try:
            category = MaterialCategory(category_value)
        except ValueError as exc:
            raise EnvironmentalFactorError(
                f"Factor names unknown material category {category_value!r}. "
                f"Allowed: {MaterialCategory.values()}.",
                details={"path": str(catalogue_path), "category": str(category_value)},
            ) from exc
        factors[category] = _parse_factor(category, body, path=catalogue_path)

    default_raw = raw.get("default")
    if default_raw is None:
        raise EnvironmentalFactorError(
            f"Environmental factor library '{catalogue_path}' is missing the "
            "'default' fallback factor.",
            details={"path": str(catalogue_path)},
        )
    default = _parse_factor(MaterialCategory.OTHER, default_raw, path=catalogue_path)

    return FactorLibrary(version=version, factors=factors, default=default)
