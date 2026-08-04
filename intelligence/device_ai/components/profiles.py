"""External component-profile library and loader (milestone M1.9).

Unlike the M1.8 recoverability profile table — which is hand-curated *in code* —
the component knowledge lives in an **external** YAML/JSON file
(``components/data/components.yaml`` by default). That is a deliberate design
choice: the component catalogue is data, not logic, so it can be reviewed,
extended or corrected without touching (or redeploying) the engine code. This
module owns the small, strict loader that turns that file into validated,
immutable value objects:

* :class:`ComponentSpec` — one component the catalogue asserts a *class* of
  device typically contains: its name, category, base likelihood (a prior in
  ``[0, 1]``), hazard/recovery flags and the identity signals that corroborate
  it.
* :class:`ComponentProfile` — the ordered component specs for one device class.
* :class:`ComponentProfileLibrary` — the whole loaded catalogue: its version,
  the per-type profiles, the synonym alias map and the conservative unknown
  fallback. :meth:`ComponentProfileLibrary.profile_for` resolves a (possibly
  messy) device type to a profile exactly as the recoverability engine does.

The loader validates aggressively and fails with a typed
:class:`~device_ai.exceptions.ComponentProfileError` on any structural problem,
so a malformed catalogue never silently degrades the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import ComponentProfileError
from .models import ComponentCategory

# Identity signals a catalogue entry may declare under ``implied_by``; their
# presence in the fused context corroborates the component. Kept as the single
# source of truth so the loader can reject unknown signal names.
_ALLOWED_IMPLIED_BY: frozenset[str] = frozenset(
    {"model", "serial_number", "imei", "mac_address"}
)


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    """One component the catalogue asserts a class of device typically contains.

    Attributes:
        name: Human-readable component name (shown in the report).
        category: The coarse :class:`ComponentCategory` the component belongs to.
        base_likelihood: Prior probability in ``[0, 1]`` that a device of this
            class contains the component, before any evidence is applied.
        hazardous: Whether the component needs hazardous handling.
        recoverable: Whether the component carries meaningful recovery value.
        implied_by: Identity signals (``model``/``serial_number``/``imei``/
            ``mac_address``) whose presence in the fused context corroborates
            this component and boosts its presence confidence.
        notes: Short human-readable rationale (provenance; not used in scoring).
    """

    name: str
    category: ComponentCategory
    base_likelihood: float
    hazardous: bool = False
    recoverable: bool = True
    implied_by: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ComponentProfile:
    """The ordered component specs the catalogue holds for one device class.

    Attributes:
        device_type: Canonical (or, for the fallback, the caller-supplied)
            device type this profile describes.
        components: The component specs for the class, in catalogue order.
        known: Whether this is a recognized profile (``False`` only for the
            unknown fallback, which drives a lower overall confidence and a
            review warning).
        notes: Short human-readable rationale for the profile (provenance).
    """

    device_type: str
    components: tuple[ComponentSpec, ...]
    known: bool = True
    notes: str = ""


def _normalize(device_type: str) -> str:
    """Return the lookup key for ``device_type``.

    Collapses internal whitespace to single underscores and casefolds, so
    ``"  CRT  Monitor "`` and ``"crt monitor"`` both become ``"crt_monitor"`` —
    mirroring the recoverability engine's normalization exactly.
    """
    return "_".join(device_type.split()).casefold()


@dataclass(frozen=True, slots=True)
class ComponentProfileLibrary:
    """The whole loaded component catalogue.

    Attributes:
        version: Semantic version of the catalogue (stamped onto every report).
        profiles: Recognized profiles keyed by normalized canonical device type.
        aliases: Synonym → canonical device-type map (keys/values normalized).
        unknown: The conservative fallback profile for unrecognized types.
    """

    version: str
    profiles: dict[str, ComponentProfile]
    aliases: dict[str, str]
    unknown: ComponentProfile

    def profile_for(self, device_type: str) -> ComponentProfile:
        """Resolve the :class:`ComponentProfile` for a device type.

        The lookup is normalized (case/whitespace-insensitive) and understands
        the catalogue's synonym aliases. Unrecognized types return a copy of the
        conservative unknown fallback, stamped with the caller-supplied
        ``device_type`` for provenance.

        Args:
            device_type: The (possibly messy) device type from a device context.

        Returns:
            The matching :class:`ComponentProfile`, or the unknown fallback.
        """
        key = _normalize(device_type)
        key = self.aliases.get(key, key)
        profile = self.profiles.get(key)
        if profile is not None:
            return profile
        return replace(self.unknown, device_type=device_type.strip())


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`ComponentProfileError`."""
    if not isinstance(value, dict):
        raise ComponentProfileError(
            f"Component profile {where} must be a mapping, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _parse_spec(raw: Any, *, device_type: str, path: Path) -> ComponentSpec:
    """Validate and build one :class:`ComponentSpec` from a raw mapping.

    Args:
        raw: The raw component entry from the catalogue.
        device_type: The owning device type (for error context).
        path: The catalogue path (for error context).

    Returns:
        The validated :class:`ComponentSpec`.

    Raises:
        ComponentProfileError: If a required field is missing or invalid.
    """
    entry = _require_mapping(raw, where=f"'{device_type}' component", path=path)

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ComponentProfileError(
            f"Component under '{device_type}' is missing a non-empty 'name'.",
            details={"path": str(path), "device_type": device_type},
        )

    category_value = entry.get("category")
    try:
        category = ComponentCategory(category_value)
    except ValueError as exc:
        raise ComponentProfileError(
            f"Component '{name}' under '{device_type}' has unknown category "
            f"{category_value!r}. Allowed: {ComponentCategory.values()}.",
            details={"path": str(path), "component": name},
        ) from exc

    likelihood = entry.get("base_likelihood")
    if not isinstance(likelihood, int | float) or isinstance(likelihood, bool):
        raise ComponentProfileError(
            f"Component '{name}' under '{device_type}' needs a numeric "
            "'base_likelihood'.",
            details={"path": str(path), "component": name},
        )
    if not 0.0 <= float(likelihood) <= 1.0:
        raise ComponentProfileError(
            f"Component '{name}' under '{device_type}' has base_likelihood "
            f"{likelihood} outside [0, 1].",
            details={"path": str(path), "component": name},
        )

    implied_raw = entry.get("implied_by", []) or []
    if not isinstance(implied_raw, list):
        raise ComponentProfileError(
            f"Component '{name}' under '{device_type}' has a non-list " "'implied_by'.",
            details={"path": str(path), "component": name},
        )
    implied_by: list[str] = []
    for signal in implied_raw:
        if signal not in _ALLOWED_IMPLIED_BY:
            raise ComponentProfileError(
                f"Component '{name}' under '{device_type}' declares unknown "
                f"implied_by signal {signal!r}. Allowed: "
                f"{sorted(_ALLOWED_IMPLIED_BY)}.",
                details={"path": str(path), "component": name},
            )
        implied_by.append(signal)

    return ComponentSpec(
        name=name,
        category=category,
        base_likelihood=float(likelihood),
        hazardous=bool(entry.get("hazardous", False)),
        recoverable=bool(entry.get("recoverable", True)),
        implied_by=tuple(implied_by),
        notes=str(entry.get("notes", "")),
    )


def _parse_profile(
    device_type: str,
    raw: Any,
    *,
    path: Path,
    known: bool,
) -> ComponentProfile:
    """Validate and build one :class:`ComponentProfile` from a raw mapping."""
    body = _require_mapping(raw, where=f"'{device_type}' profile", path=path)
    components_raw = body.get("components", [])
    if not isinstance(components_raw, list) or not components_raw:
        raise ComponentProfileError(
            f"Profile '{device_type}' must list at least one component.",
            details={"path": str(path), "device_type": device_type},
        )
    specs = tuple(
        _parse_spec(item, device_type=device_type, path=path) for item in components_raw
    )
    return ComponentProfile(
        device_type=device_type,
        components=specs,
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
        ComponentProfileError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise ComponentProfileError(
            f"Component profile library not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ComponentProfileError(
            f"Failed to parse component profile library '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise ComponentProfileError(
            f"Component profile library is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def load_library(path: str | Path) -> ComponentProfileLibrary:
    """Load and validate the external component-profile library.

    Reads the YAML (or JSON) catalogue, validates every profile and component,
    normalizes the alias map and builds the immutable
    :class:`ComponentProfileLibrary`.

    Args:
        path: Path to the catalogue file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`ComponentProfileLibrary`.

    Raises:
        ComponentProfileError: If the file is missing/malformed or fails
            validation.
    """
    catalogue_path = Path(path)
    raw = _read_catalogue(catalogue_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise ComponentProfileError(
            f"Component profile library '{catalogue_path}' is missing a "
            "non-empty 'version'.",
            details={"path": str(catalogue_path)},
        )

    profiles_raw = _require_mapping(
        raw.get("profiles", {}), where="'profiles'", path=catalogue_path
    )
    if not profiles_raw:
        raise ComponentProfileError(
            f"Component profile library '{catalogue_path}' defines no profiles.",
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
            raise ComponentProfileError(
                f"Alias '{synonym}' points at unknown canonical type "
                f"'{canonical}'.",
                details={"path": str(catalogue_path), "alias": str(synonym)},
            )
        aliases[_normalize(str(synonym))] = canonical_key

    unknown_raw = raw.get("unknown")
    if unknown_raw is None:
        raise ComponentProfileError(
            f"Component profile library '{catalogue_path}' is missing the "
            "'unknown' fallback profile.",
            details={"path": str(catalogue_path)},
        )
    unknown = _parse_profile("", unknown_raw, path=catalogue_path, known=False)

    return ComponentProfileLibrary(
        version=version,
        profiles=profiles,
        aliases=aliases,
        unknown=unknown,
    )
