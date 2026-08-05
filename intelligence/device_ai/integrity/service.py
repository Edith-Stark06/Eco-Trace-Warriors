"""Device passport validation & integrity service (milestone M2.4).

The thin, injectable façade over the validation & integrity engine: it owns the
loaded validation rule-set and the deterministic validator, drives the check of a
single :class:`~device_ai.passport.models.DevicePassport`, and stamps provenance
(rule-set/engine versions and an optional timestamp) onto every produced
:class:`~device_ai.integrity.models.PassportIntegrityReport`.

Like the passport and circular services it mirrors, every collaborator is
constructor-injected with a sensible default, so production wires nothing while
tests can inject a hand-built rule-set, a fixed clock or a custom config. The
rule-set is loaded exactly once, at construction, and held immutably. The service
is **internal-only**: it exposes no HTTP surface and does not touch the frozen
``/predict`` contract. It performs no inference — it re-validates the passport's
structure and hashes its canonical serialization.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .config import IntegrityConfig
from .rules import IntegrityRuleSet, load_rules
from .validator import PassportIntegrityValidator

if TYPE_CHECKING:
    from ..passport.models import DevicePassport
    from .models import PassportIntegrityReport

#: Version tag stamped onto every produced :class:`PassportIntegrityReport`.
INTEGRITY_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative rule-set path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class IntegrityService:
    """Validate and hash a device passport into an integrity report.

    Args:
        config: The engine configuration (rule-set locator + hash algorithm).
            Defaults to the reference :class:`IntegrityConfig`.
        rules: The loaded validation rule-set. Defaults to loading the rule-set
            named by ``config`` from disk exactly once at construction.
        validator: The deterministic validator. Defaults to a
            :class:`PassportIntegrityValidator` bound to ``config``.
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests. Pass ``None`` to omit ``created_at`` entirely
            (keeping the report a pure function of its inputs).
        engine_version: Version tag stamped onto every produced report.
    """

    def __init__(
        self,
        *,
        config: IntegrityConfig | None = None,
        rules: IntegrityRuleSet | None = None,
        validator: PassportIntegrityValidator | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = INTEGRITY_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else IntegrityConfig()
        self._rules = (
            rules
            if rules is not None
            else load_rules(
                self._config.resolved_rules_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._validator = (
            validator
            if validator is not None
            else PassportIntegrityValidator(self._config)
        )
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> IntegrityConfig:
        """Return the configuration this service validates with."""
        return self._config

    @property
    def rules(self) -> IntegrityRuleSet:
        """Return the loaded validation rule-set."""
        return self._rules

    def validate(self, passport: DevicePassport) -> PassportIntegrityReport:
        """Validate and hash a passport, returning an integrity report.

        Drives the deterministic validator over the passport against the loaded
        rule-set, and stamps provenance (rule-set/engine versions and an optional
        timestamp). The validator re-checks the passport's structure and computes
        a canonical SHA-256 hash — it derives no new score and never mutates the
        passport.

        Args:
            passport: The :class:`~device_ai.passport.models.DevicePassport` to
                check.

        Returns:
            The immutable :class:`PassportIntegrityReport` — its validation
            status, canonical hash, observed versions, checked sections and
            ordered warnings/errors.

        Raises:
            PassportIntegrityError: If the configured hash algorithm is not
                supported (an engine fault, never a passport-data fault).
        """
        created_at = self._clock() if self._clock is not None else None
        return self._validator.validate(
            passport,
            self._rules,
            rules_version=self._rules.version,
            engine_version=self._engine_version,
            created_at=created_at,
        )
