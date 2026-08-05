"""Device-passport integrity domain models (milestone M2.4).

The Device Passport Validation & Integrity Engine is a **checker**, not an
inference engine and not an assembler. It consumes the immutable
:class:`~device_ai.passport.models.DevicePassport` the passport core (M2.3)
produced and emits a single, immutable :class:`PassportIntegrityReport` that
answers two questions about that document:

* **Is it structurally sound?** — re-validating every section against an
  external, versioned rule-set (sections present, kinds correct, required object
  fields present, normalized confidences within ``[0, 1]``) and reporting the
  outcome as ordered errors and warnings rather than raising.
* **What is its integrity anchor?** — a deterministic **SHA-256** hash over the
  passport's canonical serialization, so any later mutation of the document is
  detectable by re-hashing.

The value objects here are the vocabulary of that report. Each is a small,
frozen, slotted dataclass with its own ``to_dict`` so the report serializes
deterministically:

* :class:`ValidationStatus` — the overall verdict (``valid`` /
  ``valid_with_warnings`` / ``invalid``). A ``str`` enum so it serializes to its
  wire value directly.
* :class:`CheckedSection` — the per-section outcome: the section name, its
  declared kind, whether it was present, and whether it passed its checks.
  Retaining one record per checked section is what makes the verdict auditable.
* :class:`PassportIntegrityReport` — the whole outcome: the validation status,
  the canonical integrity hash (and the algorithm that produced it), the observed
  schema and passport versions, the ordered checked sections, the ordered
  warnings and errors, and provenance (the checked passport id, the rule-set
  version, the engine version and an optional timestamp).

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the fusion,
circular, environmental and passport domain layers it builds on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "CheckedSection",
    "PassportIntegrityReport",
    "ValidationStatus",
]


class ValidationStatus(str, Enum):
    """The overall verdict of a passport integrity check.

    A ``str`` enum so members serialize to their wire value directly and can be
    compared to a plain string. The three states are ordered by severity:

    * ``VALID`` — every checked section passed and no caution was raised.
    * ``VALID_WITH_WARNINGS`` — no error was found, but at least one soft caution
      was raised (e.g. an optional section was absent).
    * ``INVALID`` — at least one structural error was found; the passport does
      not satisfy its rule-set.
    """

    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    INVALID = "invalid"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every status, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class CheckedSection:
    """The outcome of checking one passport section against the rule-set.

    Attributes:
        name: The section name (a key in the passport's serialized form).
        kind: The declared section kind (``string`` / ``object`` / ``array``).
        present: Whether the section was present in the passport payload.
        valid: Whether the section satisfied every applicable check (a present
            section of the right kind with all required fields and in-range
            confidences; ``False`` when any check for the section failed).
    """

    name: str
    kind: str
    present: bool
    valid: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the checked section."""
        return {
            "name": self.name,
            "kind": self.kind,
            "present": self.present,
            "valid": self.valid,
        }


@dataclass(frozen=True, slots=True)
class PassportIntegrityReport:
    """The immutable outcome of validating and hashing one device passport.

    Produced by the
    :class:`~device_ai.integrity.service.IntegrityService` from a single
    :class:`~device_ai.passport.models.DevicePassport`. It is a **verdict plus an
    anchor**: it re-validates the passport's structure against an external
    rule-set and reports the outcome, and it stamps a deterministic SHA-256 hash
    over the passport's canonical serialization so tampering is detectable.

    Attributes:
        passport_id: The id of the passport that was checked (provenance).
        status: The overall :class:`ValidationStatus` verdict.
        canonical_hash: Hex digest of the passport's canonical serialization,
            computed with :attr:`hash_algorithm`. Always present, even for an
            invalid passport — it anchors whatever document was checked.
        hash_algorithm: The digest algorithm the hash was computed with (e.g.
            ``sha256``).
        schema_version: The schema version observed on the passport's metadata
            (the contract it was assembled under), echoed for the consumer.
        passport_version: The passport's own structural version, echoed for the
            consumer.
        checked_sections: One :class:`CheckedSection` per rule-set section, in
            rule-set declaration order.
        warnings: Ordered, de-duplicated operator-facing cautions (soft issues
            that did not invalidate the passport).
        errors: Ordered, de-duplicated structural errors (empty when the
            passport is valid).
        rules_version: Version of the external validation rule-set used.
        engine_version: Version of the integrity engine that produced this.
        created_at: UTC timestamp the report was produced (``None`` when the
            service was constructed without a clock).
    """

    passport_id: str
    status: ValidationStatus
    canonical_hash: str
    hash_algorithm: str
    schema_version: str
    passport_version: str
    checked_sections: tuple[CheckedSection, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    rules_version: str = ""
    engine_version: str = ""
    created_at: datetime | None = None

    @property
    def is_valid(self) -> bool:
        """Return whether the passport carried no structural errors.

        ``True`` for both :attr:`ValidationStatus.VALID` and
        :attr:`ValidationStatus.VALID_WITH_WARNINGS` — a passport with only soft
        cautions is still structurally sound.
        """
        return self.status is not ValidationStatus.INVALID

    @property
    def checked_count(self) -> int:
        """Return the number of sections that were checked."""
        return len(self.checked_sections)

    @property
    def warning_count(self) -> int:
        """Return the number of warnings raised."""
        return len(self.warnings)

    @property
    def error_count(self) -> int:
        """Return the number of structural errors found."""
        return len(self.errors)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report.

        The keys are emitted in a fixed, logical order, so the mapping is a
        deterministic function of the inputs (the only source of variation is the
        optional ``created_at`` timestamp).

        Returns:
            A plain ``dict`` with the verdict, the canonical hash and algorithm,
            the observed versions, the checked sections, the ordered
            warnings/errors, provenance and an ISO-8601 ``created_at`` (or
            ``None``).
        """
        return {
            "passport_id": self.passport_id,
            "status": self.status.value,
            "canonical_hash": self.canonical_hash,
            "hash_algorithm": self.hash_algorithm,
            "schema_version": self.schema_version,
            "passport_version": self.passport_version,
            "checked_sections": [
                section.to_dict() for section in self.checked_sections
            ],
            "checked_count": self.checked_count,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "rules_version": self.rules_version,
            "engine_version": self.engine_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the report.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same report always serializes to the exact
        same bytes. Because :meth:`to_dict` is a pure function of the inputs, the
        only source of variation is the optional ``created_at`` timestamp.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )
