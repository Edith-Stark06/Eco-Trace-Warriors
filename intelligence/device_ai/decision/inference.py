"""Decision inference engine (milestone M2.1).

Deterministic arithmetic over a resolved :class:`KnowledgeBase` and the five
upstream reports (fused :class:`~device_ai.fusion.models.DeviceContext`, its
:class:`~device_ai.recoverability.models.RecoverabilityReport`, its
:class:`~device_ai.components.models.ComponentReport`, its
:class:`~device_ai.materials.models.MaterialReport` and its
:class:`~device_ai.environmental.models.EnvironmentalImpactReport`). There is no
model and no I/O here — given the same inputs the engine always produces the same
:class:`DecisionKnowledgeReport`, which is what makes the evidence auditable and
reproducible.

The fold has three clean stages:

1. **Project** the upstream reports onto a fixed set of normalized ``[0, 1]``
   input signals (:data:`~device_ai.decision.knowledge.CANONICAL_SIGNALS`). The
   already-normalized upstream scores pass through; the environmental engine's
   unbounded physical amounts are divided by the catalogue's saturation
   constants and clamped.
2. **Blend** each of the six decision dimensions as the weighted average of its
   signals, using the per-dimension weights from the knowledge catalogue. Every
   dimension score is therefore a transparent weighted mean in ``[0, 1]``.
3. **Aggregate confidence** on a wholly separate axis by blending the five
   upstream confidences with the catalogue's confidence weights. Confidence never
   scales a dimension score.

The engine computes **normalized evidence only** — no recommended action, no
economic valuation, no optimization. It consolidates what the upstream engines
already found into one comparable, explainable surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..fusion.models import FusionAttribute
from ..recoverability.models import HazardLevel
from .models import (
    DecisionDimension,
    DecisionKnowledgeReport,
    DimensionEvidence,
    EvidenceSignal,
)

if TYPE_CHECKING:
    from datetime import datetime

    from ..components.models import ComponentReport
    from ..environmental.models import EnvironmentalImpactReport
    from ..fusion.models import DeviceContext
    from ..materials.models import MaterialReport
    from ..recoverability.models import RecoverabilityReport
    from .config import DecisionConfig
    from .knowledge import KnowledgeBase

# Decimal places every emitted score/confidence is rounded to. Matches the
# fusion, recoverability, component, material and environmental engines so all
# engines' numbers compare cleanly.
_SCORE_PRECISION = 6

# Assessed hazard severity mapped to a [0, 1] signal. Mirrors the environmental
# engine's ordering exactly (UNKNOWN sits just above NONE — "needs review"
# without claiming a concrete hazard) so the two engines agree on severity.
_HAZARD_SEVERITY: dict[HazardLevel, float] = {
    HazardLevel.NONE: 0.0,
    HazardLevel.UNKNOWN: 0.25,
    HazardLevel.LOW: 0.4,
    HazardLevel.MEDIUM: 0.7,
    HazardLevel.HIGH: 1.0,
}

# The identity attributes whose presence signals a well-identified device. Used
# for the identity-completeness signal (a proxy for how much the evidence can be
# trusted to be device-specific rather than a generic fallback).
_IDENTITY_ATTRIBUTES: tuple[FusionAttribute, ...] = (
    FusionAttribute.MODEL,
    FusionAttribute.SERIAL_NUMBER,
    FusionAttribute.IMEI,
    FusionAttribute.MAC_ADDRESS,
)


def _clamp_round(value: float) -> float:
    """Clamp ``value`` to ``[0, 1]`` and round to the score precision."""
    return round(max(0.0, min(1.0, value)), _SCORE_PRECISION)


def _saturate(value: float, ceiling: float) -> float:
    """Map a non-negative physical amount onto ``[0, 1]`` by saturation.

    ``value / ceiling`` clamped to ``[0, 1]``. The ceiling is the amount at which
    the signal is considered maximal; it is always strictly positive (the loader
    enforces it), so this never divides by zero.
    """
    if ceiling <= 0.0:
        return 0.0
    return max(0.0, min(1.0, value / ceiling))


class DecisionInferenceEngine:
    """Consolidates the upstream reports into normalized decision evidence."""

    def __init__(self, config: DecisionConfig) -> None:
        self._config = config

    @property
    def config(self) -> DecisionConfig:
        """Return the configuration this engine infers with."""
        return self._config

    def infer(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        components: ComponentReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
        knowledge: KnowledgeBase,
        *,
        knowledge_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> DecisionKnowledgeReport:
        """Infer normalized decision evidence for a device.

        Args:
            context: The fused device context (eco_id, identity, conflicts).
            recoverability: The device's recoverability report.
            components: The device's component report.
            materials: The device's material report.
            environmental: The device's environmental-impact report.
            knowledge: The resolved knowledge catalogue.
            knowledge_version: Catalogue version stamped onto the report.
            engine_version: Engine version stamped onto the report.
            created_at: Timestamp stamped onto the report, or ``None``.

        Returns:
            The normalized, immutable :class:`DecisionKnowledgeReport`.
        """
        signals = self._signals(
            context, recoverability, components, materials, environmental, knowledge
        )
        dimensions = self._dimensions(signals, knowledge)
        confidence = self._overall_confidence(
            recoverability, components, materials, environmental, context, knowledge
        )

        by_dimension = {evidence.dimension: evidence for evidence in dimensions}
        reasoning, warnings = self._explain(
            context=context,
            recoverability=recoverability,
            materials=materials,
            environmental=environmental,
            by_dimension=by_dimension,
        )

        return DecisionKnowledgeReport(
            device_type=materials.device_type or context.device_type,
            repairability_score=by_dimension[DecisionDimension.REPAIRABILITY].score,
            reusability_score=by_dimension[DecisionDimension.REUSABILITY].score,
            recycling_score=by_dimension[DecisionDimension.RECYCLING].score,
            hazard_score=by_dimension[DecisionDimension.HAZARD].score,
            environmental_priority=by_dimension[
                DecisionDimension.ENVIRONMENTAL_PRIORITY
            ].score,
            material_value_score=by_dimension[DecisionDimension.MATERIAL_VALUE].score,
            overall_confidence=confidence,
            dimensions=dimensions,
            reasoning=reasoning,
            warnings=warnings,
            eco_id=context.eco_id,
            engine_version=engine_version,
            knowledge_version=knowledge_version,
            created_at=created_at,
        )

    def _signals(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        components: ComponentReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
        knowledge: KnowledgeBase,
    ) -> dict[str, float]:
        """Project the upstream reports onto the canonical normalized signals.

        The already-normalized upstream scores pass through unchanged; the
        environmental engine's unbounded physical amounts are saturated against
        the catalogue constants; mass fractions are computed from the material
        report's own totals. Every returned value is a clamped ``[0, 1]`` signal.
        """
        norm = knowledge.normalization

        total_mass = materials.total_mass_g
        if total_mass > 0.0:
            recoverable_fraction = materials.recoverable_mass_g / total_mass
            hazardous_fraction = materials.hazardous_mass_g / total_mass
        else:
            recoverable_fraction = 0.0
            hazardous_fraction = 0.0

        # The environmental savings signal is the mean of the three saturated
        # resource-savings axes — a single normalized proxy for "how much avoided
        # burden rides on this device".
        environmental_savings = (
            _saturate(environmental.carbon_saved_kg, norm.carbon_saturation_kg)
            + _saturate(environmental.energy_saved_mj, norm.energy_saturation_mj)
            + _saturate(environmental.water_saved_l, norm.water_saturation_l)
        ) / 3.0

        signals: dict[str, float] = {
            "repairability": recoverability.repairability,
            "reusability": recoverability.reusability,
            "recyclability": recoverability.recyclability,
            "circularity_index": environmental.circularity_index,
            "hazard_severity": _HAZARD_SEVERITY.get(recoverability.hazard_level, 0.0),
            "hazard_reduction": environmental.hazard_reduction_score,
            "hazardous_mass_fraction": hazardous_fraction,
            "critical_material_presence": _saturate(
                environmental.critical_material_recovery_kg,
                norm.critical_recovery_saturation_kg,
            ),
            "recoverable_mass_fraction": recoverable_fraction,
            "environmental_savings": environmental_savings,
            "identity_completeness": self._identity_completeness(context),
        }
        return {name: _clamp_round(value) for name, value in signals.items()}

    def _identity_completeness(self, context: DeviceContext) -> float:
        """Return the fraction of strong identity attributes fusion resolved.

        A device with a model, serial, IMEI and MAC scores ``1.0``; one with no
        resolved identity scores ``0.0``. This is a proxy for how device-specific
        (rather than generic-fallback) the upstream evidence is.
        """
        present = sum(
            1
            for attribute in _IDENTITY_ATTRIBUTES
            if context.value_of(attribute).strip() != ""
        )
        return present / len(_IDENTITY_ATTRIBUTES)

    def _dimensions(
        self,
        signals: dict[str, float],
        knowledge: KnowledgeBase,
    ) -> tuple[DimensionEvidence, ...]:
        """Blend each dimension as the weighted average of its signals.

        For every dimension the engine walks its catalogue weights in order,
        records each ``(signal, value, weight)`` for auditability, and divides the
        weight-value sum by the total weight. A dimension whose weights are all
        zero (which the loader forbids for the shipped catalogue) scores ``0``.
        """
        dimensions: list[DimensionEvidence] = []
        for dimension in DecisionDimension:
            weights = knowledge.weights_for(dimension)
            evidence_signals: list[EvidenceSignal] = []
            weighted_sum = 0.0
            total_weight = 0.0
            for name, weight in weights.items():
                value = signals.get(name, 0.0)
                evidence_signals.append(
                    EvidenceSignal(name=name, value=value, weight=weight)
                )
                weighted_sum += value * weight
                total_weight += weight
            score = _clamp_round(weighted_sum / total_weight) if total_weight else 0.0
            dimensions.append(
                DimensionEvidence(
                    dimension=dimension,
                    score=score,
                    signals=tuple(evidence_signals),
                    reason=self._dimension_reason(dimension, score, evidence_signals),
                )
            )
        return tuple(dimensions)

    def _dimension_reason(
        self,
        dimension: DecisionDimension,
        score: float,
        signals: list[EvidenceSignal],
    ) -> str:
        """Build the human-readable reason for one dimension's score."""
        if not signals:
            return (
                f"{dimension.value} scored {score:g}: no weighted signals were "
                "configured for this dimension."
            )
        top = max(signals, key=lambda signal: signal.value * signal.weight)
        parts = ", ".join(
            f"{signal.name}={signal.value:g}×{signal.weight:g}" for signal in signals
        )
        return (
            f"{dimension.value} scored {score:g} as the weighted mean of "
            f"[{parts}]; strongest contributor was {top.name}."
        )

    def _overall_confidence(
        self,
        recoverability: RecoverabilityReport,
        components: ComponentReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
        context: DeviceContext,
        knowledge: KnowledgeBase,
    ) -> float:
        """Blend the five upstream confidences on a separate axis.

        Each upstream confidence is weighted by the catalogue's confidence
        weights. A source whose confidence is at or below the configured floor is
        dropped from the blend entirely (its weight removed), so a genuinely
        absent upstream signal neither anchors nor inflates the result. No
        re-damping for conflicts or unknown types is applied here: every upstream
        confidence already folds those in, so re-applying would double-count.
        Confidence is a separate axis and never scales a dimension score.
        """
        available = {
            "recoverability": recoverability.confidence,
            "components": components.overall_confidence,
            "materials": materials.overall_confidence,
            "environmental": environmental.confidence,
            "fusion": context.confidence,
        }
        floor = self._config.min_confidence
        weighted_sum = 0.0
        total_weight = 0.0
        for source, confidence in available.items():
            weight = knowledge.confidence_weights.get(source, 0.0)
            if weight <= 0.0 or confidence <= floor:
                continue
            weighted_sum += confidence * weight
            total_weight += weight
        if total_weight <= 0.0:
            return 0.0
        return _clamp_round(weighted_sum / total_weight)

    def _explain(
        self,
        *,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
        by_dimension: dict[DecisionDimension, DimensionEvidence],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Build the ordered report-level reasoning and warnings."""
        reasoning: list[str] = []
        warnings: list[str] = []

        reasoning.append(
            "Consolidated the recoverability, component, material and "
            "environmental reports into six normalized decision dimensions; each "
            "score is a weighted mean of upstream signals on a [0, 1] scale."
        )
        reasoning.append(
            "Repairability "
            f"{by_dimension[DecisionDimension.REPAIRABILITY].score:g}, reusability "
            f"{by_dimension[DecisionDimension.REUSABILITY].score:g}, recycling "
            f"{by_dimension[DecisionDimension.RECYCLING].score:g}, hazard "
            f"{by_dimension[DecisionDimension.HAZARD].score:g}, environmental "
            f"priority "
            f"{by_dimension[DecisionDimension.ENVIRONMENTAL_PRIORITY].score:g}, "
            f"material value "
            f"{by_dimension[DecisionDimension.MATERIAL_VALUE].score:g}."
        )
        reasoning.append(
            "This report is normalized evidence only — it ranks the decision "
            "dimensions for this device and does not itself recommend an action "
            "or assign a monetary value."
        )

        if recoverability.hazard_level not in (HazardLevel.NONE, HazardLevel.UNKNOWN):
            warnings.append(
                "Device carries an assessed hazard; the hazard dimension is "
                "elevated and should gate any downstream disposition."
            )
        if not materials.materials:
            warnings.append(
                "Upstream material breakdown is empty; the recycling and "
                "material-value evidence rests on little signal."
            )
        if environmental.confidence <= self._config.min_confidence:
            warnings.append(
                "Environmental confidence is at or below the floor; its signals "
                "were down-weighted in the overall confidence."
            )
        if (materials.device_type or context.device_type) == "":
            warnings.append(
                "Device type is unresolved; the evidence rests on generic "
                "upstream fallbacks and should be confirmed."
            )

        return tuple(reasoning), tuple(warnings)
