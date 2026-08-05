"""Circular decision engine (milestone M2.2).

Deterministic evaluation over a resolved :class:`RuleCatalogue` and the four
upstream inputs (fused :class:`~device_ai.fusion.models.DeviceContext`, the
normalized :class:`~device_ai.decision.models.DecisionKnowledgeReport`, the
:class:`~device_ai.recoverability.models.RecoverabilityReport` and the
:class:`~device_ai.environmental.models.EnvironmentalImpactReport`). There is no
model and no I/O here — given the same inputs the engine always produces the same
:class:`DecisionReport`, which is what makes the recommendation auditable and
reproducible.

The evaluation has three clean stages:

1. **Project** the four upstream inputs onto a fixed set of normalized ``[0, 1]``
   signals (:data:`~device_ai.circular.rules.CANONICAL_SIGNALS`). The
   already-normalized upstream scores pass through; hazard severity and identity
   completeness are derived, and the boolean upstream forces (manual review,
   hazardous disposal, conflict) become ``0.0``/``1.0`` flags.
2. **Match** every catalogue rule against the projected signals. A rule fires
   only when *all* its conditions hold. Because each rule carries a unique
   precedence, the fired rules impose a total order and the lowest-precedence
   one wins the recommendation; the rest are retained as lower-precedence
   alternatives. When nothing fires, the catalogue's required ``default``
   supplies the recommendation.
3. **Aggregate confidence** from the consolidated decision confidence, damped by
   every fired rule's confidence factor, then clamp and round. Confidence is a
   separate axis and never changes which action was recommended.

The engine recommends **what to do** — an action and a triage priority — with the
exact rules that fired and ordered reasoning/warnings. It performs no economic
valuation, no optimization and no marketplace/blockchain concern.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from ..fusion.models import FusionAttribute
from ..recoverability.models import HazardLevel, RecommendedAction
from .models import DecisionReport, Priority, TriggeredRule

if TYPE_CHECKING:
    from datetime import datetime

    from ..decision.models import DecisionKnowledgeReport
    from ..environmental.models import EnvironmentalImpactReport
    from ..fusion.models import DeviceContext
    from ..recoverability.models import RecoverabilityReport
    from .config import CircularConfig
    from .rules import DecisionRule, RuleCatalogue

# Decimal places every emitted confidence is rounded to. Matches the fusion,
# recoverability, decision and environmental engines so all engines' numbers
# compare cleanly.
_SCORE_PRECISION = 6

# Assessed hazard severity mapped to a [0, 1] signal. Mirrors the decision and
# environmental engines' ordering exactly (UNKNOWN sits just above NONE — "needs
# review" without claiming a concrete hazard) so the engines agree on severity.
_HAZARD_SEVERITY: dict[HazardLevel, float] = {
    HazardLevel.NONE: 0.0,
    HazardLevel.UNKNOWN: 0.25,
    HazardLevel.LOW: 0.4,
    HazardLevel.MEDIUM: 0.7,
    HazardLevel.HIGH: 1.0,
}

# The identity attributes whose presence signals a well-identified device. Used
# for the identity-completeness signal (a proxy for how device-specific — rather
# than generic-fallback — the evidence is).
_IDENTITY_ATTRIBUTES: tuple[FusionAttribute, ...] = (
    FusionAttribute.MODEL,
    FusionAttribute.SERIAL_NUMBER,
    FusionAttribute.IMEI,
    FusionAttribute.MAC_ADDRESS,
)


def _clamp_round(value: float) -> float:
    """Clamp ``value`` to ``[0, 1]`` and round to the score precision."""
    return round(max(0.0, min(1.0, value)), _SCORE_PRECISION)


class CircularDecisionEngine:
    """Evaluate the rule catalogue into an actionable decision recommendation."""

    def __init__(self, config: CircularConfig) -> None:
        self._config = config

    @property
    def config(self) -> CircularConfig:
        """Return the configuration this engine evaluates with."""
        return self._config

    def evaluate(
        self,
        context: DeviceContext,
        knowledge: DecisionKnowledgeReport,
        recoverability: RecoverabilityReport,
        environmental: EnvironmentalImpactReport,
        catalogue: RuleCatalogue,
        *,
        rules_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> DecisionReport:
        """Evaluate the rule catalogue into a :class:`DecisionReport`.

        Args:
            context: The fused device context (eco_id, identity, conflicts).
            knowledge: The device's normalized decision-knowledge report.
            recoverability: The device's recoverability report.
            environmental: The device's environmental-impact report.
            catalogue: The resolved rule catalogue.
            rules_version: Catalogue version stamped onto the report.
            engine_version: Engine version stamped onto the report.
            created_at: Timestamp stamped onto the report, or ``None``.

        Returns:
            The actionable, immutable :class:`DecisionReport`.
        """
        signals = self._signals(context, knowledge, recoverability, environmental)
        fired, triggered, winner = self._match(signals, catalogue)
        action, priority = self._recommend(winner, catalogue)
        confidence = self._aggregate_confidence(knowledge, fired)
        reasoning, warnings = self._explain(
            context=context,
            recoverability=recoverability,
            triggered=triggered,
            winner=winner,
            catalogue=catalogue,
            action=action,
            priority=priority,
            confidence=confidence,
        )

        device_type = (
            knowledge.device_type or recoverability.device_type or context.device_type
        )
        return DecisionReport(
            device_type=device_type,
            recommended_action=action,
            priority=priority,
            confidence=confidence,
            triggered_rules=triggered,
            reasoning=reasoning,
            warnings=warnings,
            eco_id=context.eco_id,
            engine_version=engine_version,
            rules_version=rules_version,
            created_at=created_at,
        )

    def _signals(
        self,
        context: DeviceContext,
        knowledge: DecisionKnowledgeReport,
        recoverability: RecoverabilityReport,
        environmental: EnvironmentalImpactReport,
    ) -> dict[str, float]:
        """Project the four upstream inputs onto the canonical normalized signals.

        The already-normalized upstream scores pass through unchanged; hazard
        severity is mapped from the recoverability hazard level; the boolean
        upstream forces and the conflict flag become ``0.0``/``1.0``; identity
        completeness is the fraction of strong identity fields resolved. Every
        returned value is a clamped ``[0, 1]`` signal.
        """
        forced_review = (
            recoverability.recommended_action is RecommendedAction.MANUAL_REVIEW
        )
        forced_hazard = (
            recoverability.recommended_action is RecommendedAction.HAZARDOUS_DISPOSAL
        )
        signals: dict[str, float] = {
            # Consolidated decision-knowledge dimensions (M2.1).
            "repairability": knowledge.repairability_score,
            "reusability": knowledge.reusability_score,
            "recycling": knowledge.recycling_score,
            "hazard_score": knowledge.hazard_score,
            "environmental_priority": knowledge.environmental_priority,
            "material_value": knowledge.material_value_score,
            "decision_confidence": knowledge.overall_confidence,
            # Recoverability assessment (M1.8).
            "hazard_severity": _HAZARD_SEVERITY.get(recoverability.hazard_level, 0.0),
            "recoverability_confidence": recoverability.confidence,
            "upstream_manual_review": 1.0 if forced_review else 0.0,
            "upstream_hazardous_disposal": 1.0 if forced_hazard else 0.0,
            # Environmental impact (M1.11).
            "circularity_index": environmental.circularity_index,
            "hazard_reduction": environmental.hazard_reduction_score,
            "environmental_confidence": environmental.confidence,
            # Fused device context (M1.7).
            "identity_completeness": self._identity_completeness(context),
            "conflict": 1.0 if context.has_conflicts else 0.0,
        }
        return {name: _clamp_round(value) for name, value in signals.items()}

    def _identity_completeness(self, context: DeviceContext) -> float:
        """Return the fraction of strong identity attributes fusion resolved.

        A device with a model, serial, IMEI and MAC scores ``1.0``; one with no
        resolved identity scores ``0.0``. The divisor is the configured field
        count so the projection stays a config-driven, auditable number.
        """
        field_count = self._config.identity_field_count
        if field_count <= 0:
            return 0.0
        present = sum(
            1
            for attribute in _IDENTITY_ATTRIBUTES
            if context.value_of(attribute).strip() != ""
        )
        return present / field_count

    def _match(
        self,
        signals: Mapping[str, float],
        catalogue: RuleCatalogue,
    ) -> tuple[
        tuple[DecisionRule, ...], tuple[TriggeredRule, ...], DecisionRule | None
    ]:
        """Match every rule against the signals, ordered by precedence.

        The catalogue's rules are already sorted by ascending precedence, so the
        first rule that fires is the winner. Every fired rule is recorded (the
        winner flagged) so the precedence decision is fully transparent.

        Returns:
            A ``(fired_rules, triggered_records, winning_rule)`` tuple; the fired
            rules are the raw catalogue rules (carrying their confidence factors)
            in precedence order, the triggered records are their report-facing
            provenance, and ``winning_rule`` is ``None`` when no rule fired.
        """
        fired = tuple(rule for rule in catalogue.rules if rule.matches(signals))
        winner = fired[0] if fired else None
        triggered = tuple(
            TriggeredRule(
                rule_id=rule.rule_id,
                action=rule.action,
                priority=rule.priority,
                precedence=rule.precedence,
                reason=rule.reason,
                won=rule is winner,
            )
            for rule in fired
        )
        return fired, triggered, winner

    def _recommend(
        self,
        winner: DecisionRule | None,
        catalogue: RuleCatalogue,
    ) -> tuple[RecommendedAction, Priority]:
        """Select the recommended action and priority.

        The winning rule (lowest precedence among those that fired) determines
        the recommendation; when no rule fired, the catalogue's required default
        fallback supplies it, so the engine always yields a defined action.
        """
        if winner is not None:
            return winner.action, winner.priority
        return catalogue.default.action, catalogue.default.priority

    def _aggregate_confidence(
        self,
        knowledge: DecisionKnowledgeReport,
        fired: tuple[DecisionRule, ...],
    ) -> float:
        """Blend the decision confidence with every fired rule's factor.

        The aggregation is a plain product: the consolidated decision
        confidence scaled by each fired rule's multiplicative factor (``1.0`` for
        rules that do not damp confidence). Independent damping signals therefore
        compound. Confidence is a separate axis and never changes the recommended
        action.

        Args:
            knowledge: The consolidated decision-knowledge report (its overall
                confidence is the base).
            fired: The catalogue rules that matched, carrying their confidence
                factors.

        Returns:
            The aggregated confidence in ``[0, 1]``.
        """
        confidence = knowledge.overall_confidence
        for rule in fired:
            confidence *= rule.confidence_factor
        return _clamp_round(confidence)

    def _explain(
        self,
        *,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        triggered: tuple[TriggeredRule, ...],
        winner: DecisionRule | None,
        catalogue: RuleCatalogue,
        action: RecommendedAction,
        priority: Priority,
        confidence: float,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Build the ordered report-level reasoning and warnings."""
        reasoning: list[str] = []
        warnings: list[str] = []

        if winner is not None:
            reasoning.append(
                f"Recommended '{action.value}' at {priority.value} priority "
                f"because rule '{winner.rule_id}' matched: {winner.reason}"
            )
        else:
            reasoning.append(
                f"No rule matched the consolidated evidence; applied the "
                f"catalogue default '{action.value}' at {priority.value} "
                f"priority: {catalogue.default.reason}"
            )

        overridden = [record for record in triggered if not record.won]
        if overridden:
            listed = ", ".join(
                f"'{record.rule_id}' (→{record.action.value})" for record in overridden
            )
            reasoning.append(
                "Lower-precedence rules also matched but were overridden by the "
                f"winning rule: {listed}."
            )

        reasoning.append(
            f"Confidence {confidence:g} carries over the consolidated decision "
            "confidence damped by every matched rule; it does not change the "
            "recommended action."
        )

        # Rule-sourced warnings, in precedence order (winner first).
        rule_warnings = {rule.rule_id: rule.warning for rule in catalogue.rules}
        for record in triggered:
            warning = rule_warnings.get(record.rule_id)
            if warning:
                warnings.append(warning)

        if recoverability.hazard_level not in (
            HazardLevel.NONE,
            HazardLevel.UNKNOWN,
        ):
            warnings.append(
                "Device carries an assessed hazard; confirm hazardous handling "
                "before acting on this recommendation."
            )
        if action is RecommendedAction.MANUAL_REVIEW:
            warnings.append(
                "Recommendation is a manual review; a human must decide this "
                "device's disposition before it is routed."
            )
        if confidence <= self._config.min_confidence:
            warnings.append(
                f"Aggregated confidence ({confidence:g}) is at or below the "
                f"configured floor ({self._config.min_confidence:g}); treat the "
                "recommendation as low-confidence."
            )

        return tuple(reasoning), tuple(warnings)
