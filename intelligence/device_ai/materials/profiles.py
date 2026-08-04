"""External material-profile library and loader (milestone M1.10).

Mirroring the M1.9 component catalogue, the material knowledge lives in an
**external** YAML/JSON file (``materials/data/materials.yaml`` by default) rather
than in code. That is a deliberate design choice: the material catalogue is data,
not logic, so it can be reviewed, extended or corrected without touching (or
redeploying) the engine code. This module owns the small, strict loader that
turns that file into validated, immutable value objects:

* :class:`MaterialSpec` — one material the catalogue asserts a *class* of device
  is made of: its name, category, nominal mass (grams), recovery/hazard flags and
  the source component categories whose presence conditions it.
* :class:`MaterialProfile` — the ordered material specs for one device class.
* :class:`MaterialProfileLibrary` — the whole loaded catalogue: its version, the
  per-type profiles, the synonym alias map and the conservative unknown fallback.
  :meth:`MaterialProfileLibrary.profile_for` resolves a (possibly messy) device
  type to a profile exactly as the component engine does.

The loader validates aggressively and fails with a typed
:class:`~device_ai.exceptions.MaterialProfileError` on any structural problem, so
a malformed catalogue never silently degrades the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from ..components.models import ComponentCategory
from ..exceptions import MaterialProfileError
from .models import MaterialCategory

# Source component categories a material entry may declare under
# ``source_components``; their presence in the consumed component report
# conditions the material and drives its confidence. Kept as the single source
# of truth (the M1.9 component vocabulary) so the loader can reject unknown
# category names.
_ALLOWED_SOURCE_COMPONENTS: frozenset[str] = frozenset(ComponentCategory.values())


@dataclass(frozen=True, slots=True)
class MaterialSpec:
    """One material the catalogue asserts a class of device is made of.

    Attributes:
        name: Human-readable material name (shown in the report).
        category: The coarse :class:`MaterialCategory` the material belongs to.
        mass_g: Nominal mass in grams a device of this class contains of this
            material, before the component inventory conditions its presence.
        recoverable: Whether the material carries meaningful recovery value.
        hazardous: Whether the material needs hazardous handling.
        source_components: Component-category wire values whose presence in the
            consumed component report conditions this material and drives its
            confidence. Empty means the material is unconditional (structural).
        notes: Short human-readable rationale (provenance; not used in scoring).
    """

    name: str
    category: MaterialCategory
    mass_g: float
    recoverable: bool = True
    hazardous: bool = False
    source_components: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class MaterialProfile:
    """The ordered material specs the catalogue holds for one device class.

    Attributes:
        device_type: Canonical (or, for the fallback, the caller-supplied)
            device type this profile describes.
        materials: The material specs for the class, in catalogue order.
        known: Whether this is a recognized profile (``False`` only for the
            unknown fallback, which drives a lower overall confidence and a
            review warning).
        notes: Short human-readable rationale for the profile (provenance).
    """

    device_type: str
    materials: tuple[MaterialSpec, ...]
    known: bool = True
    notes: str = ""


def _normalize(device_type: str) -> str:
    """Return the lookup key for ``device_type``.

    Collapses internal whitespace to single underscores and casefolds, so
    ``"  CRT  Monitor "`` and ``"crt monitor"`` both become ``"crt_monitor"`` —
    mirroring the component and recoverability engines' normalization exactly.
    """
    return "_".join(device_type.split()).casefold()


@dataclass(frozen=True, slots=True)
class MaterialProfileLibrary:
    """The whole loaded material catalogue.

    Attributes:
        version: Semantic version of the catalogue (stamped onto every report).
        profiles: Recognized profiles keyed by normalized canonical device type.
        aliases: Synonym → canonical device-type map (keys/values normalized).
        unknown: The conservative fallback profile for unrecognized types.
    """

    version: str
    profiles: dict[str, MaterialProfile]
    aliases: dict[str, str]
    unknown: MaterialProfile

    def profile_for(self, device_type: str) -> MaterialProfile:
        """Resolve the :class:`MaterialProfile` for a device type.

        The lookup is normalized (case/whitespace-insensitive) and understands
        the catalogue's synonym aliases. Unrecognized types return a copy of the
        conservative unknown fallback, stamped with the caller-supplied
        ``device_type`` for provenance.

        Args:
            device_type: The (possibly messy) device type from a device context.

        Returns:
            The matching :class:`MaterialProfile`, or the unknown fallback.
        """
        key = _normalize(device_type)
        key = self.aliases.get(key, key)
        profile = self.profiles.get(key)
        if profile is not None:
            return profile
        return replace(self.unknown, device_type=device_type.strip())


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`MaterialProfileError`."""
    if not isinstance(value, dict):
        raise MaterialProfileError(
            f"Material profile {where} must be a mapping, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _parse_spec(raw: Any, *, device_type: str, path: Path) -> MaterialSpec:
    """Validate and build one :class:`MaterialSpec` from a raw mapping.

    Args:
        raw: The raw material entry from the catalogue.
        device_type: The owning device type (for error context).
        path: The catalogue path (for error context).

    Returns:
        The validated :class:`MaterialSpec`.

    Raises:
        MaterialProfileError: If a required field is missing or invalid.
    """
    entry = _require_mapping(raw, where=f"'{device_type}' material", path=path)

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MaterialProfileError(
            f"Material under '{device_type}' is missing a non-empty 'name'.",
            details={"path": str(path), "device_type": device_type},
        )

    category_value = entry.get("category")
    try:
        category = MaterialCategory(category_value)
    except ValueError as exc:
        raise MaterialProfileError(
            f"Material '{name}' under '{device_type}' has unknown category "
            f"{category_value!r}. Allowed: {MaterialCategory.values()}.",
            details={"path": str(path), "material": name},
        ) from exc

    mass = entry.get("mass_g")
    if not isinstance(mass, int | float) or isinstance(mass, bool):
        raise MaterialProfileError(
            f"Material '{name}' under '{device_type}' needs a numeric 'mass_g'.",
            details={"path": str(path), "material": name},
        )
    if float(mass) < 0.0:
        raise MaterialProfileError(
            f"Material '{name}' under '{device_type}' has negative mass_g {mass}.",
            details={"path": str(path), "material": name},
        )

    source_raw = entry.get("source_components", []) or []
    if not isinstance(source_raw, list):
        raise MaterialProfileError(
            f"Material '{name}' under '{device_type}' has a non-list "
            "'source_components'.",
            details={"path": str(path), "material": name},
        )
    source_components: list[str] = []
    for source in source_raw:
        if source not in _ALLOWED_SOURCE_COMPONENTS:
            raise MaterialProfileError(
                f"Material '{name}' under '{device_type}' declares unknown "
                f"source_component {source!r}. Allowed: "
                f"{sorted(_ALLOWED_SOURCE_COMPONENTS)}.",
                details={"path": str(path), "material": name},
            )
        source_components.append(source)

    return MaterialSpec(
        name=name,
        category=category,
        mass_g=float(mass),
        recoverable=bool(entry.get("recoverable", True)),
        hazardous=bool(entry.get("hazardous", False)),
        source_components=tuple(source_components),
        notes=str(entry.get("notes", "")),
    )


def _parse_profile(
    device_type: str,
    raw: Any,
    *,
    path: Path,
    known: bool,
) -> MaterialProfile:
    """Validate and build one :class:`MaterialProfile` from a raw mapping."""
    body = _require_mapping(raw, where=f"'{device_type}' profile", path=path)
    materials_raw = body.get("materials", [])
    if not isinstance(materials_raw, list) or not materials_raw:
        raise MaterialProfileError(
            f"Profile '{device_type}' must list at least one material.",
            details={"path": str(path), "device_type": device_type},
        )
    specs = tuple(
        _parse_spec(item, device_type=device_type, path=path) for item in materials_raw
    )
    return MaterialProfile(
        device_type=device_type,
        materials=specs,
        known=known,
        notes=str(body.get("notes", "")),
    )


def _read_catalogue(path: Path) -> dict[str, Any]:
    """Parse the catalogue file (YAML or JSON) into a mapping.

    Args:
        path: The catalogue file to read.

    Returns:
        The parsed top-level mapping.

    Raises:
        MaterialProfileError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise MaterialProfileError(
            f"Material profile library not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise MaterialProfileError(
            f"Failed to parse material profile library '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise MaterialProfileError(
            f"Material profile library is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def load_library(path: str | Path) -> MaterialProfileLibrary:
    """Load and validate the external material-profile library.

    Reads the YAML (or JSON) catalogue, validates every profile and material,
    normalizes the alias map and builds the immutable
    :class:`MaterialProfileLibrary`.

    Args:
        path: Path to the catalogue file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`MaterialProfileLibrary`.

    Raises:
        MaterialProfileError: If the file is missing/malformed or fails
            validation.
    """
    catalogue_path = Path(path)
    raw = _read_catalogue(catalogue_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise MaterialProfileError(
            f"Material profile library '{catalogue_path}' is missing a "
            "non-empty 'version'.",
            details={"path": str(catalogue_path)},
        )

    profiles_raw = _require_mapping(
        raw.get("profiles", {}), where="'profiles'", path=catalogue_path
    )
    if not profiles_raw:
        raise MaterialProfileError(
            f"Material profile library '{catalogue_path}' defines no profiles.",
            details={"path": str(catalogue_path)},
        )
    profiles = {
        _normalize(device_type): _parse_profile(
            _normalize(device_type), body, path=catalogue_path, known=True
        )
        for device_type, body in profiles_raw.items()
    }

    aliases_raw = _require_mapping(
        raw.get("aliases", {}), where="'aliases'", path=catalogue_path
    )
    aliases: dict[str, str] = {}
    for synonym, canonical in aliases_raw.items():
        canonical_key = _normalize(str(canonical))
        if canonical_key not in profiles:
            raise MaterialProfileError(
                f"Alias '{synonym}' points at unknown canonical type "
                f"'{canonical}'.",
                details={"path": str(catalogue_path), "alias": str(synonym)},
            )
        aliases[_normalize(str(synonym))] = canonical_key

    unknown_raw = raw.get("unknown")
    if unknown_raw is None:
        raise MaterialProfileError(
            f"Material profile library '{catalogue_path}' is missing the "
            "'unknown' fallback profile.",
            details={"path": str(catalogue_path)},
        )
    unknown = _parse_profile("", unknown_raw, path=catalogue_path, known=False)

    return MaterialProfileLibrary(
        version=version,
        profiles=profiles,
        aliases=aliases,
        unknown=unknown,
    )
