"""Recoverability scoring engine (milestone M1.8).

:class:`ScoringEngine` is the deterministic fold that turns the flat list of
:class:`~device_ai.recoverability.models.RuleOutcome` s produced by the rule
engine into a normalized :class:`~device_ai.recoverability.models.RecoverabilityReport`.
It does no domain reasoning of its own — every judgement lives in a rule — so
its job is purely arithmetic and therefore fully predictable:

* **Dimensions** — each score is the clamped, rounded sum of that dimension's
  deltas (the baseline rule contributes the profile baseline as the first delta).
* **Hazard** — the most severe hazard floor any rule asserted.
* **Confidence aggregation** — the context's own confidence multiplied by every
  rule's confidence factor, then clamped and rounded.
* **Recommended action** — a single, explicit, ordered decision table over the
  hazard level, any forced actions and the score thresholds from the config.
* **Explanations** — the rules' reasons and warnings, preserved in rule order.

All numeric outputs are clamped to ``[0, 1]`` and rounded to six decimals,
matching the fusion engine's precision so the two engines' numbers compose
cleanly.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from .config import RecoverabilityConfig
from .models import (
    HazardLevel,
    RecommendedAction,
    RecoverabilityReport,
    RuleOutcome,
    max_hazard,
)

if TYPE_CHECKING:  # Type-only import: scoring reads a context's confidence and
    # identity anchor but never couples to the fusion layer at runtime.
    from ..fusion.models import DeviceContext
    from .profiles import DeviceProfile

# Decimal places every emitted score is rounded to. Matches the fusion engine's
# ``_CONFIDENCE_PRECISION`` so recoverability and fusion numbers compare cleanly.
_SCORE_PRECISION = 6


def _clamp_round(value: float) -> float:
    """Clamp ``value`` to ``[0, 1]`` and round to the score precision."""
    return round(max(0.0, min(1.0, value)), _SCORE_PRECISION)


class ScoringEngine:
    """Fold rule outcomes into a normalized recoverability report.

    Args:
        config: The engine configuration whose thresholds drive the
            recommended-action decision. Weights are consumed by the rules; the
            scoring engine only needs the decision thresholds, but it holds the
            whole config so callers configure the engine in one place.
    """

    def __init__(self, config: RecoverabilityConfig) -> None:
        self._config = config

    @property
    def config(self) -> RecoverabilityConfig:
        """Return the configuration this engine scores with."""
        return self._config

    def score(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        outcomes: Sequence[RuleOutcome],
        *,
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> RecoverabilityReport:
        """Fold ``outcomes`` into a :class:`RecoverabilityReport`.

        Args:
            context: The fused device context being assessed (its confidence
                and EcoID feed the report).
            profile: The resolved device-type profile (its ``device_type``
                labels the report).
            outcomes: The rule outcomes to fold, in rule order.
            engine_version: Version stamped onto the report (provenance).
            created_at: Timestamp stamped onto the report, or ``None``.

        Returns:
            The normalized, immutable :class:`RecoverabilityReport`.
        """
        repairability = _clamp_round(
            sum(outcome.repairability_delta for outcome in outcomes)
        )
        reusability = _clamp_round(
            sum(outcome.reusability_delta for outcome in outcomes)
        )
        recyclability = _clamp_round(
            sum(outcome.recyclability_delta for outcome in outcomes)
        )
        hazard_level = max_hazard(*(outcome.hazard_floor for outcome in outcomes))
        confidence = self._aggregate_confidence(context.confidence, outcomes)
        action = self._decide_action(
            hazard_level=hazard_level,
            repairability=repairability,
            reusability=reusability,
            recyclability=recyclability,
            outcomes=outcomes,
        )
        reasoning = tuple(outcome.reason for outcome in outcomes if outcome.reason)
        warnings = tuple(outcome.warning for outcome in outcomes if outcome.warning)
        return RecoverabilityReport(
            device_type=profile.device_type,
            repairability=repairability,
            reusability=reusability,
            recyclability=recyclability,
            hazard_level=hazard_level,
            confidence=confidence,
            recommended_action=action,
            reasoning=reasoning,
            warnings=warnings,
            eco_id=context.eco_id,
            engine_version=engine_version,
            created_at=created_at,
        )

    @staticmethod
    def _aggregate_confidence(
        base_confidence: float,
        outcomes: Sequence[RuleOutcome],
    ) -> float:
        """Combine the context confidence with every rule's factor.

        The aggregation is a plain product: the fused device confidence scaled
        by each rule's multiplicative factor (``1.0`` for rules that do not
        touch confidence). Independent damping signals therefore compound —
        conflicts *and* low confidence reduce the result more than either alone.

        Args:
            base_confidence: The fused context's own aggregate confidence.
            outcomes: The rule outcomes contributing confidence factors.

        Returns:
            The aggregated confidence in ``[0, 1]``.
        """
        confidence = base_confidence
        for outcome in outcomes:
            confidence *= outcome.confidence_factor
        return _clamp_round(confidence)

    def _decide_action(
        self,
        *,
        hazard_level: HazardLevel,
        repairability: float,
        reusability: float,
        recyclability: float,
        outcomes: Sequence[RuleOutcome],
    ) -> RecommendedAction:
        """Select the recommended action from an explicit, ordered table.

        The order encodes the engine's priorities, most binding first:

        1. A ``HIGH`` hazard (or a rule forcing it) overrides everything →
           ``HAZARDOUS_DISPOSAL``.
        2. Any rule forcing manual review (low confidence, unknown type) →
           ``MANUAL_REVIEW``.
        3. Otherwise the score ladder: reusable enough → ``REFURBISH``; else
           repairable enough → ``REPAIR``; else recyclable enough → ``RECYCLE``.
        4. If nothing clears its threshold → ``MANUAL_REVIEW``.

        Args:
            hazard_level: The combined hazard severity.
            repairability: The folded repairability score.
            reusability: The folded reusability score.
            recyclability: The folded recyclability score.
            outcomes: The rule outcomes (read for forced actions).

        Returns:
            The chosen :class:`RecommendedAction`.
        """
        forced = {
            outcome.force_action
            for outcome in outcomes
            if outcome.force_action is not None
        }
        config = self._config
        if (
            hazard_level is HazardLevel.HIGH
            or RecommendedAction.HAZARDOUS_DISPOSAL in forced
        ):
            return RecommendedAction.HAZARDOUS_DISPOSAL
        if RecommendedAction.MANUAL_REVIEW in forced:
            return RecommendedAction.MANUAL_REVIEW
        if reusability >= config.refurbish_min_reusability:
            return RecommendedAction.REFURBISH
        if repairability >= config.repair_min_repairability:
            return RecommendedAction.REPAIR
        if recyclability >= config.recycle_min_recyclability:
            return RecommendedAction.RECYCLE
        return RecommendedAction.MANUAL_REVIEW
