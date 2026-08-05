"""Decision knowledge service (milestone M2.1).

The thin, injectable façade over the decision engine: it owns the loaded
knowledge catalogue and the inference engine, and stamps provenance
(engine/catalogue versions and an optional timestamp) onto every
:class:`~device_ai.decision.models.DecisionKnowledgeReport`.

Like the environmental service it mirrors, every collaborator is
constructor-injected with a sensible default, so production wires nothing while
tests can inject a hand-built knowledge base, a fixed clock or a custom config.
The catalogue is loaded exactly once, at construction, and held immutably.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .config import DecisionConfig
from .inference import DecisionInferenceEngine
from .knowledge import KnowledgeBase, load_knowledge

if TYPE_CHECKING:
    from ..components.models import ComponentReport
    from ..environmental.models import EnvironmentalImpactReport
    from ..fusion.models import DeviceContext
    from ..materials.models import MaterialReport
    from ..recoverability.models import RecoverabilityReport
    from .models import DecisionKnowledgeReport

#: Version tag stamped onto every produced :class:`DecisionKnowledgeReport`.
DECISION_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative catalogue path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class DecisionService:
    """Consolidates the upstream reports into normalized decision evidence."""

    def __init__(
        self,
        *,
        config: DecisionConfig | None = None,
        knowledge: KnowledgeBase | None = None,
        inference_engine: DecisionInferenceEngine | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = DECISION_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else DecisionConfig()
        self._knowledge = (
            knowledge
            if knowledge is not None
            else load_knowledge(
                self._config.resolved_knowledge_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._inference = (
            inference_engine
            if inference_engine is not None
            else DecisionInferenceEngine(self._config)
        )
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> DecisionConfig:
        """Return the configuration this service analyzes with."""
        return self._config

    @property
    def knowledge(self) -> KnowledgeBase:
        """Return the loaded knowledge catalogue."""
        return self._knowledge

    def analyze(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        components: ComponentReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
    ) -> DecisionKnowledgeReport:
        """Consolidate the upstream reports into normalized decision evidence.

        Runs the inference engine over the fused context and its four downstream
        reports against the loaded knowledge catalogue, and stamps provenance. The
        inference reads only the reports' aggregate quantities (scores, hazard,
        masses, confidences) — never any raw image or model — and produces
        normalized evidence only (no recommended action, no valuation).

        Args:
            context: The fused :class:`~device_ai.fusion.models.DeviceContext`.
            recoverability: The device's
                :class:`~device_ai.recoverability.models.RecoverabilityReport`.
            components: The device's
                :class:`~device_ai.components.models.ComponentReport`.
            materials: The device's
                :class:`~device_ai.materials.models.MaterialReport`.
            environmental: The device's
                :class:`~device_ai.environmental.models.EnvironmentalImpactReport`.

        Returns:
            The normalized, immutable :class:`DecisionKnowledgeReport`.
        """
        created_at = self._clock() if self._clock is not None else None
        return self._inference.infer(
            context,
            recoverability,
            components,
            materials,
            environmental,
            self._knowledge,
            knowledge_version=self._knowledge.version,
            engine_version=self._engine_version,
            created_at=created_at,
        )
