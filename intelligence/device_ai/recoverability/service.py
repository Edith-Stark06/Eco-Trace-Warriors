"""Recoverability service: orchestration facade for the engine (milestone M1.8).

:class:`RecoverabilityService` is the single collaborator downstream code
depends on to assess a device. It wires together the injected configuration,
rule engine and scoring engine into the one operation the engine exposes:

* :meth:`assess` — resolve the device-type profile for a fused
  :class:`~device_ai.fusion.models.DeviceContext`, run the rule engine, fold the
  outcomes with the scoring engine and stamp provenance, yielding an immutable
  :class:`~device_ai.recoverability.models.RecoverabilityReport`.

Every collaborator (config, rule engine, scoring engine, clock) is injected, so
the whole engine is exercised deterministically in tests with a hand-built
context — no fusion run, no models, no filesystem. Like the fusion engine it
builds on, the service is **internal-only**: it exposes no HTTP surface and does
not touch the frozen ``/predict`` contract.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .config import RecoverabilityConfig
from .models import RecoverabilityReport
from .profiles import profile_for
from .rules import RuleEngine
from .scoring import ScoringEngine

if TYPE_CHECKING:  # Type-only import keeps the recoverability core free of a
    # hard runtime coupling to the fusion layer (the context is passed in).
    from ..fusion.models import DeviceContext

#: Version tag stamped onto every produced :class:`RecoverabilityReport`.
RECOVERABILITY_ENGINE_VERSION = "1.0.0"


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class RecoverabilityService:
    """High-level orchestration of the recoverability assessment.

    Args:
        config: The engine configuration (thresholds + weights). Defaults to
            the reference :class:`RecoverabilityConfig`.
        rule_engine: The rule engine producing outcomes. Defaults to a
            :class:`RuleEngine` over the reference rule set.
        scoring_engine: The scoring engine folding outcomes into a report.
            Defaults to a :class:`ScoringEngine` bound to ``config``.
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests. Pass ``None`` to omit ``created_at`` entirely
            (keeping the report a pure function of its inputs).
        engine_version: Version tag stamped onto every produced report.
    """

    def __init__(
        self,
        *,
        config: RecoverabilityConfig | None = None,
        rule_engine: RuleEngine | None = None,
        scoring_engine: ScoringEngine | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = RECOVERABILITY_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else RecoverabilityConfig()
        self._rules = rule_engine if rule_engine is not None else RuleEngine()
        self._scoring = (
            scoring_engine
            if scoring_engine is not None
            else ScoringEngine(self._config)
        )
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> RecoverabilityConfig:
        """Return the configuration this service assesses with."""
        return self._config

    def assess(self, context: DeviceContext) -> RecoverabilityReport:
        """Assess the recoverability of a fused device context.

        Resolves the device-type profile, runs the rule engine over the context
        and profile, folds the outcomes into a report and stamps provenance.
        The assessment reads only the context's identity attributes, aggregate
        confidence and conflict flag — never any condition or material data
        (which the context does not carry).

        Args:
            context: The fused :class:`~device_ai.fusion.models.DeviceContext`
                to assess.

        Returns:
            The normalized, immutable :class:`RecoverabilityReport`.
        """
        profile = profile_for(context.device_type)
        outcomes = self._rules.run(context, profile, self._config)
        created_at = self._clock() if self._clock is not None else None
        return self._scoring.score(
            context,
            profile,
            outcomes,
            engine_version=self._engine_version,
            created_at=created_at,
        )
