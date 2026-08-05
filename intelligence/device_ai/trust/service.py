"""Trust & provenance service (milestone M2.5).

The thin, injectable façade over the trust & provenance engine: it owns the
loaded trust catalogue and the scoring engine, and stamps provenance
(engine/catalogue versions and an optional timestamp) onto every
:class:`~device_ai.trust.models.PassportTrustReport`.

Like the integrity and circular services it mirrors, every collaborator is
constructor-injected with a sensible default, so production wires nothing while
tests can inject a hand-built trust catalogue, a fixed clock or a custom config.
The catalogue is loaded exactly once, at construction, and held immutably. The
service is **internal-only**: it exposes no HTTP surface and does not touch the
frozen ``/predict`` contract. It performs no inference — it reads the four
upstream reports' existing confidence and consistency signals, blends them into
a trust score, and maps that score to a trust level.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .config import TrustConfig
from .engine import TrustEngine
from .rules import TrustRuleSet, load_rules

if TYPE_CHECKING:
    from ..circular.models import DecisionReport
    from ..decision.models import DecisionKnowledgeReport
    from ..integrity.models import PassportIntegrityReport
    from ..passport.models import DevicePassport
    from .models import PassportTrustReport

#: Version tag stamped onto every produced :class:`PassportTrustReport`.
TRUST_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative catalogue path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class TrustService:
    """Score and level a passport's trustworthiness into a trust report.

    Args:
        config: The engine configuration (catalogue locator + projection knobs).
            Defaults to the reference :class:`TrustConfig`.
        rules: The loaded trust catalogue. Defaults to loading the catalogue
            named by ``config`` from disk exactly once at construction.
        engine: The scoring engine. Defaults to a :class:`TrustEngine` bound to
            ``config``.
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests. Pass ``None`` to omit ``created_at`` entirely
            (keeping the report a pure function of its inputs).
        engine_version: Version tag stamped onto every produced report.
    """

    def __init__(
        self,
        *,
        config: TrustConfig | None = None,
        rules: TrustRuleSet | None = None,
        engine: TrustEngine | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = TRUST_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else TrustConfig()
        self._rules = (
            rules
            if rules is not None
            else load_rules(
                self._config.resolved_rules_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._engine = engine if engine is not None else TrustEngine(self._config)
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> TrustConfig:
        """Return the configuration this service scores with."""
        return self._config

    @property
    def rules(self) -> TrustRuleSet:
        """Return the loaded trust catalogue."""
        return self._rules

    def assess(
        self,
        passport: DevicePassport,
        integrity: PassportIntegrityReport,
        knowledge: DecisionKnowledgeReport,
        decision: DecisionReport,
    ) -> PassportTrustReport:
        """Assess how trustworthy a passport is as a representation of the device.

        Runs the scoring engine over the passport and its three upstream reports
        against the loaded trust catalogue, and stamps provenance. The engine
        reads only the reports' existing confidence and consistency signals — it
        derives no new inference and collects no new evidence — and produces a
        normalized trust score, a mapped trust level, the four sub-axes and the
        ordered reasoning/warnings.

        Args:
            passport: The :class:`~device_ai.passport.models.DevicePassport` to
                assess.
            integrity: The passport's
                :class:`~device_ai.integrity.models.PassportIntegrityReport`.
            knowledge: The device's
                :class:`~device_ai.decision.models.DecisionKnowledgeReport`.
            decision: The device's
                :class:`~device_ai.circular.models.DecisionReport`.

        Returns:
            The immutable, auditable :class:`PassportTrustReport`.
        """
        created_at = self._clock() if self._clock is not None else None
        return self._engine.evaluate(
            passport,
            integrity,
            knowledge,
            decision,
            self._rules,
            rules_version=self._rules.version,
            engine_version=self._engine_version,
            created_at=created_at,
        )
