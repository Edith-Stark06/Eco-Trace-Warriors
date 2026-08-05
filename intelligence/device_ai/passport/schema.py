"""External device-passport schema and strict validator (milestone M2.3).

Mirroring the M2.2 circular rule catalogue and the M2.1 knowledge catalogue, the
passport's **structural contract** lives in an external YAML/JSON file
(``passport/data/schema.yaml`` by default) rather than in code. That is a
deliberate design choice: *which sections a passport must contain, and the shape
and ranges of each* is a contract that can be reviewed and versioned as the
passport evolves, without touching — or redeploying — the builder. This module
owns the small, strict loader that turns that file into an immutable
:class:`PassportSchema`, and the validator that checks an assembled passport
against it:

* :class:`SectionKind` — the kind of one section: a plain ``string``, an
  ``object`` with a fixed set of fields, or an ordered ``array``.
* :class:`SectionSchema` — one section's contract: its name, kind, the fields an
  object section must contain, and the subset of those fields that are normalized
  ``[0, 1]`` confidences.
* :class:`PassportSchema` — the whole loaded schema: its version and the ordered
  sections a passport must contain.

The loader validates aggressively (a non-empty version, at least one section,
known section kinds, non-empty object field lists, confidence fields drawn from
the section's own fields) and fails with a typed
:class:`~device_ai.exceptions.PassportSchemaError` on any structural problem, so
a malformed schema never silently degrades the builder. The
:func:`validate_passport` function then checks a built passport's ``to_dict``
against the loaded schema and raises
:class:`~device_ai.exceptions.PassportValidationError` when a required section is
missing, an object field is absent, or a confidence is out of range — so a
malformed passport never leaves the builder.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import PassportSchemaError, PassportValidationError


class SectionKind(str, Enum):
    """The kind of one passport section the schema may declare.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a schema string (e.g. ``"object"``). This enum is the single
    source of truth the external schema's section kinds are validated against on
    load — a schema naming a kind outside this set is rejected.
    """

    STRING = "string"
    OBJECT = "object"
    ARRAY = "array"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every kind, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class SectionSchema:
    """The contract for one passport section.

    Attributes:
        name: The section name (a key in the passport's serialized form).
        kind: The :class:`SectionKind` the section's value must be.
        fields: For an ``object`` section, the field names the value must contain
            (empty for ``string``/``array`` sections).
        confidence_fields: The subset of ``fields`` whose values must be numeric
            and within ``[0, 1]`` (empty when the section has none).
    """

    name: str
    kind: SectionKind
    fields: tuple[str, ...] = ()
    confidence_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the section schema."""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "fields": list(self.fields),
            "confidence_fields": list(self.confidence_fields),
        }


@dataclass(frozen=True, slots=True)
class PassportSchema:
    """The whole loaded device-passport schema.

    Attributes:
        version: Semantic version of the schema (stamped onto every passport).
        sections: The sections a passport must contain, in declaration order.
    """

    version: str
    sections: tuple[SectionSchema, ...]

    @property
    def section_count(self) -> int:
        """Return the number of sections the schema declares."""
        return len(self.sections)

    @property
    def section_names(self) -> tuple[str, ...]:
        """Return the declared section names, in declaration order."""
        return tuple(section.name for section in self.sections)

    def section(self, name: str) -> SectionSchema | None:
        """Return the section named ``name``, or ``None`` when absent."""
        for section in self.sections:
            if section.name == name:
                return section
        return None


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`PassportSchemaError`."""
    if not isinstance(value, dict):
        raise PassportSchemaError(
            f"Passport schema {where} must be a mapping, got {type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_sequence(value: Any, *, where: str, path: Path) -> list[Any]:
    """Return ``value`` as a list or raise :class:`PassportSchemaError`.

    Strings and mappings are rejected even though they are iterable — a field
    list must be an explicit sequence.
    """
    if not isinstance(value, list):
        raise PassportSchemaError(
            f"Passport schema {where} must be a list, got {type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_str(value: Any, *, field: str, where: str, path: Path) -> str:
    """Return a non-empty string field or raise :class:`PassportSchemaError`."""
    if not isinstance(value, str) or not value.strip():
        raise PassportSchemaError(
            f"Passport schema {where} needs a non-empty '{field}' string.",
            details={"path": str(path), "where": where, "field": field},
        )
    return value.strip()


def _parse_field_names(raw: Any, *, where: str, path: Path) -> tuple[str, ...]:
    """Validate and return a section's ordered, unique field-name list."""
    names_raw = _require_sequence(raw, where=where, path=path)
    names: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(names_raw):
        name = _require_str(
            item, field="field", where=f"{where} entry #{index}", path=path
        )
        if name in seen:
            raise PassportSchemaError(
                f"Passport schema {where} lists a duplicate field {name!r}.",
                details={"path": str(path), "where": where, "field": name},
            )
        seen.add(name)
        names.append(name)
    return tuple(names)


def _parse_section(name: str, raw: Any, *, path: Path) -> SectionSchema:
    """Validate and build one :class:`SectionSchema`."""
    where = f"section '{name}'"
    mapping = _require_mapping(raw, where=where, path=path)

    kind_text = _require_str(mapping.get("kind"), field="kind", where=where, path=path)
    try:
        kind = SectionKind(kind_text)
    except ValueError as exc:
        raise PassportSchemaError(
            f"Passport schema {where} names unknown kind {kind_text!r}. "
            f"Allowed: {SectionKind.values()}.",
            details={"path": str(path), "where": where, "field": "kind"},
        ) from exc

    fields: tuple[str, ...] = ()
    confidence_fields: tuple[str, ...] = ()
    if kind is SectionKind.OBJECT:
        fields = _parse_field_names(
            mapping.get("fields"), where=f"{where} 'fields'", path=path
        )
        if not fields:
            raise PassportSchemaError(
                f"Passport schema {where} is an object but declares no 'fields'.",
                details={"path": str(path), "where": where},
            )
        if "confidence_fields" in mapping:
            confidence_fields = _parse_field_names(
                mapping.get("confidence_fields"),
                where=f"{where} 'confidence_fields'",
                path=path,
            )
            unknown = [field for field in confidence_fields if field not in fields]
            if unknown:
                raise PassportSchemaError(
                    f"Passport schema {where} lists confidence field(s) {unknown} "
                    "not present in the section's 'fields'.",
                    details={"path": str(path), "where": where, "unknown": unknown},
                )
    elif "fields" in mapping:
        raise PassportSchemaError(
            f"Passport schema {where} is a {kind.value} but declares 'fields'; "
            "only object sections may list fields.",
            details={"path": str(path), "where": where},
        )

    return SectionSchema(
        name=name,
        kind=kind,
        fields=fields,
        confidence_fields=confidence_fields,
    )


def _read_schema(path: Path) -> dict[str, Any]:
    """Parse the schema file (YAML or JSON) into a mapping.

    Args:
        path: The schema file to read.

    Returns:
        The parsed top-level mapping.

    Raises:
        PassportSchemaError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise PassportSchemaError(
            f"Passport schema not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise PassportSchemaError(
            f"Failed to parse passport schema '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise PassportSchemaError(
            f"Passport schema is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def load_schema(path: str | Path) -> PassportSchema:
    """Load and validate the external device-passport schema.

    Reads the YAML (or JSON) schema, validates the version and every section
    (known kind, non-empty object field lists, confidence fields drawn from the
    section's own fields) and builds the immutable :class:`PassportSchema` with
    sections in declaration order.

    Args:
        path: Path to the schema file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`PassportSchema`.

    Raises:
        PassportSchemaError: If the file is missing/malformed or fails
            validation.
    """
    schema_path = Path(path)
    raw = _read_schema(schema_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise PassportSchemaError(
            f"Passport schema '{schema_path}' is missing a non-empty 'version'.",
            details={"path": str(schema_path)},
        )

    if "sections" not in raw:
        raise PassportSchemaError(
            f"Passport schema '{schema_path}' is missing the required 'sections' "
            "mapping.",
            details={"path": str(schema_path)},
        )
    sections_raw = _require_mapping(
        raw.get("sections"), where="'sections'", path=schema_path
    )
    if not sections_raw:
        raise PassportSchemaError(
            f"Passport schema '{schema_path}' declares no sections.",
            details={"path": str(schema_path)},
        )

    sections = tuple(
        _parse_section(str(name), definition, path=schema_path)
        for name, definition in sections_raw.items()
    )
    return PassportSchema(version=version, sections=sections)


def _validate_confidence(value: Any, *, section: str, field: str) -> None:
    """Raise :class:`PassportValidationError` unless ``value`` is in ``[0, 1]``."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise PassportValidationError(
            f"Passport section '{section}' field '{field}' must be a numeric "
            f"confidence, got {type(value).__name__}.",
            details={"section": section, "field": field},
        )
    number = float(value)
    if number < 0.0 or number > 1.0:
        raise PassportValidationError(
            f"Passport section '{section}' field '{field}' must be within [0, 1], "
            f"got {number}.",
            details={"section": section, "field": field},
        )


def validate_passport(payload: Mapping[str, Any], schema: PassportSchema) -> None:
    """Validate a serialized passport against the loaded schema.

    Checks that every declared section is present, that each ``object`` section
    is a mapping containing all of its fields, that each ``string`` section is a
    string and each ``array`` section a list, and that every declared confidence
    field is numeric and within ``[0, 1]``. Raises on the first violation, so a
    malformed passport is rejected rather than silently emitted.

    Args:
        payload: The passport's serialized form (its ``to_dict`` output).
        schema: The loaded schema to validate against.

    Raises:
        PassportValidationError: If any section is missing, malformed, or carries
            an out-of-range confidence.
    """
    for section in schema.sections:
        if section.name not in payload:
            raise PassportValidationError(
                f"Passport is missing required section '{section.name}'.",
                details={"section": section.name},
            )
        value = payload[section.name]

        if section.kind is SectionKind.STRING:
            if not isinstance(value, str):
                raise PassportValidationError(
                    f"Passport section '{section.name}' must be a string, got "
                    f"{type(value).__name__}.",
                    details={"section": section.name},
                )
        elif section.kind is SectionKind.ARRAY:
            if not isinstance(value, list):
                raise PassportValidationError(
                    f"Passport section '{section.name}' must be an array, got "
                    f"{type(value).__name__}.",
                    details={"section": section.name},
                )
        else:  # SectionKind.OBJECT
            if not isinstance(value, Mapping):
                raise PassportValidationError(
                    f"Passport section '{section.name}' must be an object, got "
                    f"{type(value).__name__}.",
                    details={"section": section.name},
                )
            for field in section.fields:
                if field not in value:
                    raise PassportValidationError(
                        f"Passport section '{section.name}' is missing required "
                        f"field '{field}'.",
                        details={"section": section.name, "field": field},
                    )
            for field in section.confidence_fields:
                _validate_confidence(value[field], section=section.name, field=field)
