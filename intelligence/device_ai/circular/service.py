"""Circular decision service (milestone M2.2).

The thin, injectable façade over the circular decision engine: it owns the loaded
rule catalogue and the evaluation engine, and stamps provenance (engine/catalogue
versions and an optional timestamp) onto every
:class:`~device_ai.circular.models.DecisionReport`.

Like the decision-knowledge service it mirrors, every collaborator is
constructor-injected with a sensible default, so production wires nothing while
tests can inject a hand-built rule catalogue, a fixed clock or a custom config.
The catalogue is loaded exactly once, at construction, and held immutably. The
service is **internal-only**: it exposes no HTTP surface and does not touch the
frozen ``/predict`` contract.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .config import CircularConfig
from .engine import CircularDecisionEngine
from .rules import RuleCatalogue, load_rules

if TYPE_CHECKING:
    from ..decision.models import DecisionKnowledgeReport
    from ..environmental.models import EnvironmentalImpactReport
    from ..fusion.models import DeviceContext
    from ..recoverability.models import RecoverabilityReport
    from .models import DecisionReport

#: Version tag stamped onto every produced :class:`DecisionReport`.
CIRCULAR_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative catalogue path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class CircularService:
    """Turn the consolidated device evidence into an actionable recommendation.

    Args:
        config: The engine configuration (catalogue locator + knobs). Defaults
            to the reference :class:`CircularConfig`.
        catalogue: The loaded rule catalogue. Defaults to loading the catalogue
            named by ``config`` from disk exactly once at construction.
        engine: The evaluation engine. Defaults to a
            :class:`CircularDecisionEngine` bound to ``config``.
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests. Pass ``None`` to omit ``created_at`` entirely
            (keeping the report a pure function of its inputs).
        engine_version: Version tag stamped onto every produced report.
    """

    def __init__(
        self,
        *,
        config: CircularConfig | None = None,
        catalogue: RuleCatalogue | None = None,
        engine: CircularDecisionEngine | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = CIRCULAR_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else CircularConfig()
        self._catalogue = (
            catalogue
            if catalogue is not None
            else load_rules(
                self._config.resolved_rules_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._engine = (
            engine if engine is not None else CircularDecisionEngine(self._config)
        )
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> CircularConfig:
        """Return the configuration this service decides with."""
        return self._config

    @property
    def catalogue(self) -> RuleCatalogue:
        """Return the loaded rule catalogue."""
        return self._catalogue

    def decide(
        self,
        context: DeviceContext,
        knowledge: DecisionKnowledgeReport,
        recoverability: RecoverabilityReport,
        environmental: EnvironmentalImpactReport,
    ) -> DecisionReport:
        """Recommend a circular disposition for a device.

        Runs the evaluation engine over the fused context and its three
        consolidated reports against the loaded rule catalogue, and stamps
        provenance. The evaluation reads only the reports' aggregate quantities
        (scores, hazard, confidences, conflict flag) — never any raw image or
        model — and produces a recommended action, a priority, an aggregated
        confidence and the exact rules that fired.

        Args:
            context: The fused :class:`~device_ai.fusion.models.DeviceContext`.
            knowledge: The device's
                :class:`~device_ai.decision.models.DecisionKnowledgeReport`.
            recoverability: The device's
                :class:`~device_ai.recoverability.models.RecoverabilityReport`.
            environmental: The device's
                :class:`~device_ai.environmental.models.EnvironmentalImpactReport`.

        Returns:
            The actionable, immutable :class:`DecisionReport`.
        """
        created_at = self._clock() if self._clock is not None else None
        return self._engine.evaluate(
            context,
            knowledge,
            recoverability,
            environmental,
            self._catalogue,
            rules_version=self._catalogue.version,
            engine_version=self._engine_version,
            created_at=created_at,
        )
