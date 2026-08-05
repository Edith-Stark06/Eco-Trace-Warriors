"""External passport validation rule-set and strict loader (milestone M2.4).

Mirroring the M2.3 passport schema, the M2.2 circular rule catalogue and the
M2.1 knowledge catalogue, the integrity engine's **validation contract** lives in
an external YAML/JSON file (``integrity/data/rules.yaml`` by default) rather than
in code. That is a deliberate design choice: *which sections a passport must
contain, the shape and ranges of each, and which sections are optional* is a
contract that can be reviewed and versioned independently as the passport
evolves, without touching — or redeploying — the validator. This module owns the
small, strict loader that turns that file into an immutable
:class:`IntegrityRuleSet`:

* :class:`SectionKind` — the kind of one section: a plain ``string``, an
  ``object`` with a fixed set of fields, or an ordered ``array``.
* :class:`SectionRule` — one section's contract: its name, kind, the fields an
  object section must contain, the subset of those fields that are normalized
  ``[0, 1]`` confidences, and whether the section is *required* (a missing
  required section is an error; a missing optional section is a warning).
* :class:`IntegrityRuleSet` — the whole loaded rule-set: its version and the
  ordered sections a passport is checked against.

The loader validates aggressively (a non-empty version, at least one section,
known section kinds, non-empty object field lists, confidence fields drawn from
the section's own fields) and fails with a typed
:class:`~device_ai.exceptions.PassportIntegrityRuleError` on any structural
problem, so a malformed rule-set never silently degrades the validator. Note the
asymmetry with the passport schema loader: a malformed *rule-set* raises (it is
an engine fault), whereas a malformed *passport* is reported as ordered errors on
the produced report (it is data the engine was asked to judge).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import PassportIntegrityRuleError

__all__ = [
    "IntegrityRuleSet",
    "SectionKind",
    "SectionRule",
    "load_rules",
]


class SectionKind(str, Enum):
    """The kind of one passport section the rule-set may declare.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a rule-set string (e.g. ``"object"``). This enum is the
    single source of truth the external rule-set's section kinds are validated
    against on load — a rule-set naming a kind outside this set is rejected.
    """

    STRING = "string"
    OBJECT = "object"
    ARRAY = "array"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every kind, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class SectionRule:
    """The validation contract for one passport section.

    Attributes:
        name: The section name (a key in the passport's serialized form).
        kind: The :class:`SectionKind` the section's value must be.
        fields: For an ``object`` section, the field names the value must contain
            (empty for ``string``/``array`` sections).
        confidence_fields: The subset of ``fields`` whose values must be numeric
            and within ``[0, 1]`` (empty when the section has none).
        required: Whether the section must be present. A missing *required*
            section is an error (the passport is invalid); a missing *optional*
            section is a warning (the passport stays valid-with-warnings).
    """

    name: str
    kind: SectionKind
    fields: tuple[str, ...] = ()
    confidence_fields: tuple[str, ...] = ()
    required: bool = True

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the section rule."""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "fields": list(self.fields),
            "confidence_fields": list(self.confidence_fields),
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class IntegrityRuleSet:
    """The whole loaded passport validation rule-set.

    Attributes:
        version: Semantic version of the rule-set (stamped onto every report).
        sections: The sections a passport is checked against, in declaration
            order.
    """

    version: str
    sections: tuple[SectionRule, ...]

    @property
    def section_count(self) -> int:
        """Return the number of sections the rule-set declares."""
        return len(self.sections)

    @property
    def section_names(self) -> tuple[str, ...]:
        """Return the declared section names, in declaration order."""
        return tuple(section.name for section in self.sections)

    def section(self, name: str) -> SectionRule | None:
        """Return the section named ``name``, or ``None`` when absent."""
        for section in self.sections:
            if section.name == name:
                return section
        return None


def _require_mapping(value: Any, *, where: str, path: Path) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`PassportIntegrityRuleError`."""
    if not isinstance(value, dict):
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set {where} must be a mapping, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_sequence(value: Any, *, where: str, path: Path) -> list[Any]:
    """Return ``value`` as a list or raise :class:`PassportIntegrityRuleError`.

    Strings and mappings are rejected even though they are iterable — a field
    list must be an explicit sequence.
    """
    if not isinstance(value, list):
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set {where} must be a list, got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where},
        )
    return value


def _require_str(value: Any, *, field: str, where: str, path: Path) -> str:
    """Return a non-empty string field or raise :class:`PassportIntegrityRuleError`."""
    if not isinstance(value, str) or not value.strip():
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set {where} needs a non-empty '{field}' "
            "string.",
            details={"path": str(path), "where": where, "field": field},
        )
    return value.strip()


def _require_bool(value: Any, *, field: str, where: str, path: Path) -> bool:
    """Return a boolean field or raise :class:`PassportIntegrityRuleError`."""
    if not isinstance(value, bool):
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set {where} needs a boolean '{field}', got "
            f"{type(value).__name__}.",
            details={"path": str(path), "where": where, "field": field},
        )
    return value


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
            raise PassportIntegrityRuleError(
                f"Passport validation rule-set {where} lists a duplicate field "
                f"{name!r}.",
                details={"path": str(path), "where": where, "field": name},
            )
        seen.add(name)
        names.append(name)
    return tuple(names)


def _parse_section(name: str, raw: Any, *, path: Path) -> SectionRule:
    """Validate and build one :class:`SectionRule`."""
    where = f"section '{name}'"
    mapping = _require_mapping(raw, where=where, path=path)

    kind_text = _require_str(mapping.get("kind"), field="kind", where=where, path=path)
    try:
        kind = SectionKind(kind_text)
    except ValueError as exc:
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set {where} names unknown kind "
            f"{kind_text!r}. Allowed: {SectionKind.values()}.",
            details={"path": str(path), "where": where, "field": "kind"},
        ) from exc

    fields: tuple[str, ...] = ()
    confidence_fields: tuple[str, ...] = ()
    if kind is SectionKind.OBJECT:
        fields = _parse_field_names(
            mapping.get("fields"), where=f"{where} 'fields'", path=path
        )
        if not fields:
            raise PassportIntegrityRuleError(
                f"Passport validation rule-set {where} is an object but declares "
                "no 'fields'.",
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
                raise PassportIntegrityRuleError(
                    f"Passport validation rule-set {where} lists confidence "
                    f"field(s) {unknown} not present in the section's 'fields'.",
                    details={"path": str(path), "where": where, "unknown": unknown},
                )
    elif "fields" in mapping:
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set {where} is a {kind.value} but declares "
            "'fields'; only object sections may list fields.",
            details={"path": str(path), "where": where},
        )

    required = True
    if "required" in mapping:
        required = _require_bool(
            mapping.get("required"), field="required", where=where, path=path
        )

    return SectionRule(
        name=name,
        kind=kind,
        fields=fields,
        confidence_fields=confidence_fields,
        required=required,
    )


def _read_rules(path: Path) -> dict[str, Any]:
    """Parse the rule-set file (YAML or JSON) into a mapping.

    Args:
        path: The rule-set file to read.

    Returns:
        The parsed top-level mapping.

    Raises:
        PassportIntegrityRuleError: If the file is missing, unparseable, or not a
            mapping.
    """
    if not path.exists():
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set not found: {path}",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise PassportIntegrityRuleError(
            f"Failed to parse passport validation rule-set '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set is empty: {path}",
            details={"path": str(path)},
        )
    return _require_mapping(raw, where="root", path=path)


def load_rules(path: str | Path) -> IntegrityRuleSet:
    """Load and validate the external passport validation rule-set.

    Reads the YAML (or JSON) rule-set, validates the version and every section
    (known kind, non-empty object field lists, confidence fields drawn from the
    section's own fields, a boolean ``required`` flag) and builds the immutable
    :class:`IntegrityRuleSet` with sections in declaration order.

    Args:
        path: Path to the rule-set file (``.yaml``/``.yml``/``.json``).

    Returns:
        The validated, immutable :class:`IntegrityRuleSet`.

    Raises:
        PassportIntegrityRuleError: If the file is missing/malformed or fails
            validation.
    """
    rules_path = Path(path)
    raw = _read_rules(rules_path)

    version = str(raw.get("version", "")).strip()
    if not version:
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set '{rules_path}' is missing a non-empty "
            "'version'.",
            details={"path": str(rules_path)},
        )

    if "sections" not in raw:
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set '{rules_path}' is missing the required "
            "'sections' mapping.",
            details={"path": str(rules_path)},
        )
    sections_raw = _require_mapping(
        raw.get("sections"), where="'sections'", path=rules_path
    )
    if not sections_raw:
        raise PassportIntegrityRuleError(
            f"Passport validation rule-set '{rules_path}' declares no sections.",
            details={"path": str(rules_path)},
        )

    sections = tuple(
        _parse_section(str(name), definition, path=rules_path)
        for name, definition in sections_raw.items()
    )
    return IntegrityRuleSet(version=version, sections=sections)
