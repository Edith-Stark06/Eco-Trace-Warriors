"""Deterministic passport integrity validator (milestone M2.4).

The engine of the validation & integrity core. `PassportIntegrityValidator`
consumes a single :class:`~device_ai.passport.models.DevicePassport` and produces
an immutable :class:`~device_ai.integrity.models.PassportIntegrityReport`. There
is no model and no inference here: the validator re-checks the passport's
structure against an external :class:`~device_ai.integrity.rules.IntegrityRuleSet`
and computes a deterministic hash over the passport's canonical serialization.
Given the same passport and rule-set it always produces the same report (modulo
the optional timestamp), which is what makes the integrity hash an auditable
anchor.

The check has two independent halves:

1. **Validate** every rule-set section against the passport payload, recording a
   :class:`~device_ai.integrity.models.CheckedSection` per section and appending
   an ordered error (a required section missing/malformed, a field absent, a
   confidence out of range) or a soft warning (an optional section absent). A
   malformed *passport* is never raised — it is reported; only a malformed
   *rule-set* raises, at load time.
2. **Hash** the passport's canonical JSON with the configured algorithm
   (SHA-256 by default), giving a fixed-length hex digest that changes if any
   byte of the document changes.

The overall :class:`~device_ai.integrity.models.ValidationStatus` is ``invalid``
when any error was found, ``valid_with_warnings`` when only soft cautions were
raised, and ``valid`` otherwise.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from ..exceptions import PassportIntegrityError
from ..utils.hashing import hash_bytes
from .models import CheckedSection, PassportIntegrityReport, ValidationStatus
from .rules import IntegrityRuleSet, SectionKind, SectionRule

if TYPE_CHECKING:
    from datetime import datetime

    from ..passport.models import DevicePassport
    from .config import IntegrityConfig


def _is_confidence(value: Any) -> bool:
    """Return whether ``value`` is a numeric confidence within ``[0, 1]``.

    Booleans are rejected (``bool`` is an ``int`` subclass but never a valid
    confidence), matching the passport-core convention.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    return 0.0 <= float(value) <= 1.0


class PassportIntegrityValidator:
    """Validate a device passport against a rule-set and hash it."""

    def __init__(self, config: IntegrityConfig) -> None:
        self._config = config

    @property
    def config(self) -> IntegrityConfig:
        """Return the configuration this validator checks with."""
        return self._config

    def validate(
        self,
        passport: DevicePassport,
        rules: IntegrityRuleSet,
        *,
        rules_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> PassportIntegrityReport:
        """Validate and hash a passport into a :class:`PassportIntegrityReport`.

        Args:
            passport: The :class:`DevicePassport` to check.
            rules: The loaded validation rule-set to check it against.
            rules_version: Rule-set version stamped onto the report.
            engine_version: Integrity-engine version stamped onto the report.
            created_at: Report timestamp stamped onto the report, or ``None``.

        Returns:
            The immutable :class:`PassportIntegrityReport`.

        Raises:
            PassportIntegrityError: If the configured hash algorithm is not
                supported (an engine fault, never a passport-data fault).
        """
        payload = passport.to_dict()
        checked_sections, warnings, errors = self._check_sections(payload, rules)
        status = self._status(warnings=warnings, errors=errors)
        canonical_hash = self._hash(passport)

        return PassportIntegrityReport(
            passport_id=passport.passport_id,
            status=status,
            canonical_hash=canonical_hash,
            hash_algorithm=self._config.hash_algorithm,
            schema_version=passport.metadata.schema_version,
            passport_version=passport.passport_version,
            checked_sections=tuple(checked_sections),
            warnings=tuple(warnings),
            errors=tuple(errors),
            rules_version=rules_version,
            engine_version=engine_version,
            created_at=created_at,
        )

    # -- Structural validation ----------------------------------------------

    def _check_sections(
        self, payload: Mapping[str, Any], rules: IntegrityRuleSet
    ) -> tuple[list[CheckedSection], list[str], list[str]]:
        """Check every rule-set section against the payload.

        Returns the ordered checked-section records, the ordered de-duplicated
        warnings and the ordered de-duplicated errors. Each section contributes
        at most one presence outcome plus any field/kind/confidence errors; a
        section is ``valid`` when it accrued no error.
        """
        checked: list[CheckedSection] = []
        warnings: list[str] = []
        errors: list[str] = []
        seen_warnings: set[str] = set()
        seen_errors: set[str] = set()

        def add_warning(message: str) -> None:
            if message not in seen_warnings:
                seen_warnings.add(message)
                warnings.append(message)

        def add_error(message: str) -> None:
            if message not in seen_errors:
                seen_errors.add(message)
                errors.append(message)

        for rule in rules.sections:
            present = rule.name in payload
            if not present:
                section_valid = self._check_absent(rule, add_warning, add_error)
            else:
                section_valid = self._check_present(rule, payload[rule.name], add_error)
            checked.append(
                CheckedSection(
                    name=rule.name,
                    kind=rule.kind.value,
                    present=present,
                    valid=section_valid,
                )
            )
        return checked, warnings, errors

    def _check_absent(
        self,
        rule: SectionRule,
        add_warning: Callable[[str], None],
        add_error: Callable[[str], None],
    ) -> bool:
        """Record the outcome of a section missing from the payload.

        A missing *required* section is an error (the section is invalid); a
        missing *optional* section is a soft warning (the section stays valid).
        """
        if rule.required:
            add_error(f"Passport is missing required section '{rule.name}'.")
            return False
        add_warning(
            f"Passport is missing optional section '{rule.name}'; it was not "
            "validated."
        )
        return True

    def _check_present(
        self,
        rule: SectionRule,
        value: Any,
        add_error: Callable[[str], None],
    ) -> bool:
        """Check a present section's kind, fields and confidences.

        Returns whether the section passed every applicable check. Each failure
        appends a distinct error; the section is invalid when any error was
        appended for it.
        """
        if rule.kind is SectionKind.STRING:
            if not isinstance(value, str):
                add_error(
                    f"Passport section '{rule.name}' must be a string, got "
                    f"{type(value).__name__}."
                )
                return False
            return True

        if rule.kind is SectionKind.ARRAY:
            if not isinstance(value, list):
                add_error(
                    f"Passport section '{rule.name}' must be an array, got "
                    f"{type(value).__name__}."
                )
                return False
            return True

        # SectionKind.OBJECT
        if not isinstance(value, Mapping):
            add_error(
                f"Passport section '{rule.name}' must be an object, got "
                f"{type(value).__name__}."
            )
            return False

        section_valid = True
        for field in rule.fields:
            if field not in value:
                add_error(
                    f"Passport section '{rule.name}' is missing required field "
                    f"'{field}'."
                )
                section_valid = False
        for field in rule.confidence_fields:
            if field in value and not _is_confidence(value[field]):
                add_error(
                    f"Passport section '{rule.name}' field '{field}' must be a "
                    "numeric confidence within [0, 1]."
                )
                section_valid = False
        return section_valid

    def _status(self, *, warnings: list[str], errors: list[str]) -> ValidationStatus:
        """Derive the overall verdict from the accrued warnings and errors."""
        if errors:
            return ValidationStatus.INVALID
        if warnings:
            return ValidationStatus.VALID_WITH_WARNINGS
        return ValidationStatus.VALID

    # -- Integrity hashing --------------------------------------------------

    def _hash(self, passport: DevicePassport) -> str:
        """Compute the canonical integrity hash of the passport.

        Hashes the passport's canonical JSON (sorted keys, fixed separators, no
        pretty-printing) so the digest is a pure function of the document's
        content — any later mutation of the passport changes the hash.

        Raises:
            PassportIntegrityError: If the configured algorithm is unsupported.
        """
        canonical = passport.to_json().encode("utf-8")
        try:
            return hash_bytes(canonical, algorithm=self._config.hash_algorithm)
        except ValueError as exc:
            raise PassportIntegrityError(
                f"Unsupported integrity hash algorithm "
                f"'{self._config.hash_algorithm}'.",
                details={"algorithm": self._config.hash_algorithm},
            ) from exc
