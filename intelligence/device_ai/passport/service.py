"""Device passport service (milestone M2.3).

The thin, injectable façade over the passport core: it owns the loaded schema and
the deterministic builder, drives the assembly of the five upstream reports into a
:class:`~device_ai.passport.models.DevicePassport`, stamps provenance
(schema/engine versions and an optional timestamp), and **validates the assembled
passport against the schema before returning it** — so a malformed passport never
leaves the service.

Like the circular and decision services it mirrors, every collaborator is
constructor-injected with a sensible default, so production wires nothing while
tests can inject a hand-built schema, a fixed clock or a custom config. The schema
is loaded exactly once, at construction, and held immutably. The service is
**internal-only**: it exposes no HTTP surface and does not touch the frozen
``/predict`` contract. It performs no inference — every value on the passport is
copied or plainly summarized from an upstream report.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .builder import PassportBuilder
from .config import PassportConfig
from .schema import PassportSchema, load_schema, validate_passport

if TYPE_CHECKING:
    from ..circular.models import DecisionReport
    from ..environmental.models import EnvironmentalImpactReport
    from ..fingerprint.models import DeviceFingerprint
    from ..fusion.models import DeviceContext
    from ..materials.models import MaterialReport
    from .models import DevicePassport

#: Version tag stamped onto every produced :class:`DevicePassport`'s metadata.
PASSPORT_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative schema path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class PassportService:
    """Compose the upstream reports into a validated device passport.

    Args:
        config: The passport configuration (schema locator + presentation caps).
            Defaults to the reference :class:`PassportConfig`.
        schema: The loaded passport schema. Defaults to loading the schema named
            by ``config`` from disk exactly once at construction.
        builder: The deterministic passport builder. Defaults to a
            :class:`PassportBuilder` bound to ``config``.
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests. Pass ``None`` to omit ``created_at`` entirely
            (keeping the passport a pure function of its inputs).
        engine_version: Version tag stamped onto every produced passport's
            metadata.
    """

    def __init__(
        self,
        *,
        config: PassportConfig | None = None,
        schema: PassportSchema | None = None,
        builder: PassportBuilder | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = PASSPORT_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else PassportConfig()
        self._schema = (
            schema
            if schema is not None
            else load_schema(
                self._config.resolved_schema_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._builder = (
            builder if builder is not None else PassportBuilder(self._config)
        )
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> PassportConfig:
        """Return the configuration this service assembles with."""
        return self._config

    @property
    def schema(self) -> PassportSchema:
        """Return the loaded passport schema."""
        return self._schema

    def build(
        self,
        context: DeviceContext,
        decision: DecisionReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
        fingerprint: DeviceFingerprint | None = None,
    ) -> DevicePassport:
        """Compose a validated device passport from the upstream reports.

        Drives the deterministic builder over the five upstream inputs, stamps
        provenance (schema/engine versions and an optional timestamp), then
        validates the assembled passport's serialized form against the loaded
        schema before returning it. The builder derives no new scores — every
        value is copied or plainly summarized from an input.

        Args:
            context: The fused :class:`~device_ai.fusion.models.DeviceContext`.
            decision: The device's
                :class:`~device_ai.circular.models.DecisionReport`.
            materials: The device's
                :class:`~device_ai.materials.models.MaterialReport`.
            environmental: The device's
                :class:`~device_ai.environmental.models.EnvironmentalImpactReport`.
            fingerprint: The device's
                :class:`~device_ai.fingerprint.models.DeviceFingerprint`, or
                ``None`` when no fingerprint is available.

        Returns:
            The immutable, schema-validated :class:`DevicePassport`.

        Raises:
            PassportValidationError: If the assembled passport fails schema
                validation (a defensive guard; the builder is deterministic and
                schema-conformant by construction).
        """
        created_at = self._clock() if self._clock is not None else None
        passport = self._builder.build(
            context,
            decision,
            materials,
            environmental,
            fingerprint,
            schema_version=self._schema.version,
            passport_version=self._config.passport_version,
            engine_version=self._engine_version,
            created_at=created_at,
        )
        validate_passport(passport.to_dict(), self._schema)
        return passport
