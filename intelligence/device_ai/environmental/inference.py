"""Environmental inference engine (milestone M1.11).

Deterministic arithmetic over a resolved :class:`FactorLibrary`, a fused
:class:`~device_ai.fusion.models.DeviceContext`, its
:class:`~device_ai.recoverability.models.RecoverabilityReport`, its
:class:`~device_ai.components.models.ComponentReport` and its
:class:`~device_ai.materials.models.MaterialReport`. There is no model and no
I/O here — given the same inputs the engine always produces the same
:class:`EnvironmentalImpactReport`, which is what makes the estimate auditable
and reproducible.

The fold keeps three axes strictly apart (per the design):

* **Physical quantities** — carbon (kg CO₂e), energy (MJ), water (L), landfill
  diversion (kg) and critical-material recovery (kg) are real amounts. They are
  the recovered mass times the catalogue's per-kilogram factors, rounded but
  **never** clamped to a unit interval.
* **Unit indices** — the circularity index and hazard-reduction score are
  composite ``[0, 1]`` measures of *how circular* / *how much hazard was
  removed*, independent of the absolute masses.
* **Confidence** — a single separate ``[0, 1]`` axis blending the upstream
  material and recoverability confidences. It never scales a metric.

Only recoverable materials whose own confidence clears the configured floor
contribute to the resource-savings metrics; the material report has already done
the source-component gating, so the environmental engine simply aggregates what
it is handed.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from ..recoverability.models import HazardLevel
from .models import EnvironmentalImpactReport, MaterialContribution

if TYPE_CHECKING:
    from datetime import datetime

    from ..components.models import ComponentReport
    from ..fusion.models import DeviceContext
    from ..materials.models import MaterialReport, RecoveredMaterial
    from ..recoverability.models import RecoverabilityReport
    from .config import EnvironmentalConfig
    from .factors import FactorLibrary

# Decimal places every emitted confidence/index is rounded to. Matches the
# fusion, recoverability, component and material engines so all engines' numbers
# compare cleanly.
_SCORE_PRECISION = 6

# Decimal places every emitted physical metric is rounded to. These are physical
# quantities, not probabilities, so they are rounded but never clamped to [0, 1].
_METRIC_PRECISION = 3

# Grams per kilogram — the conversion factors are per-kilogram, the material
# masses are in grams.
_GRAMS_PER_KG = 1000.0

# Assessed hazard severity mapped to a [0, 1] weight for the hazard-reduction
# score. UNKNOWN sits just above NONE (it signals "needs review" without
# claiming a concrete hazard), mirroring the recoverability engine's ordering.
_HAZARD_SEVERITY: dict[HazardLevel, float] = {
    HazardLevel.NONE: 0.0,
    HazardLevel.UNKNOWN: 0.25,
    HazardLevel.LOW: 0.4,
    HazardLevel.MEDIUM: 0.7,
    HazardLevel.HIGH: 1.0,
}


def _clamp_round(value: float) -> float:
    """Clamp ``value`` to ``[0, 1]`` and round to the score precision."""
    return round(max(0.0, min(1.0, value)), _SCORE_PRECISION)


def _round_metric(value: float) -> float:
    """Round a physical metric to the metric precision (never clamped)."""
    return round(value, _METRIC_PRECISION)


class EnvironmentalInferenceEngine:
    """Estimates the avoided environmental burden of recovering a device."""

    def __init__(self, config: EnvironmentalConfig) -> None:
        self._config = config

    @property
    def config(self) -> EnvironmentalConfig:
        """Return the configuration this engine infers with."""
        return self._config

    def infer(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        components: ComponentReport,
        materials: MaterialReport,
        library: FactorLibrary,
        *,
        factors_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> EnvironmentalImpactReport:
        """Infer the environmental impact of recovering a device.

        Args:
            context: The fused device context (eco_id + provenance).
            recoverability: The device's recoverability report (its recyclability
                feeds the circularity index; its hazard level feeds the
                hazard-reduction score; its confidence feeds the blend).
            components: The device's component report (consumed for provenance
                and to corroborate that a hazardous stream exists).
            materials: The device's material report (its recoverable materials
                and mass totals drive every resource-savings metric).
            library: The resolved conversion-factor library.
            factors_version: Catalogue version stamped onto the report.
            engine_version: Engine version stamped onto the report.
            created_at: Timestamp stamped onto the report, or ``None``.

        Returns:
            The normalized, immutable :class:`EnvironmentalImpactReport`.
        """
        contributions = self._contributions(materials, library)

        carbon = _round_metric(sum(item.carbon_saved_kg for item in contributions))
        energy = _round_metric(sum(item.energy_saved_mj for item in contributions))
        water = _round_metric(sum(item.water_saved_l for item in contributions))
        critical_recovery = _round_metric(
            sum(item.recovered_mass_g for item in contributions if item.critical)
            / _GRAMS_PER_KG
        )

        landfill_diversion = _round_metric(materials.recoverable_mass_g / _GRAMS_PER_KG)

        circularity = self._circularity_index(recoverability, materials)
        hazard_reduction = self._hazard_reduction_score(recoverability, materials)
        confidence = self._overall_confidence(recoverability, materials)

        reasoning, warnings = self._explain(
            recoverability=recoverability,
            materials=materials,
            contributions=contributions,
            carbon=carbon,
        )

        return EnvironmentalImpactReport(
            device_type=materials.device_type,
            contributions=contributions,
            carbon_saved_kg=carbon,
            energy_saved_mj=energy,
            water_saved_l=water,
            landfill_diversion_kg=landfill_diversion,
            critical_material_recovery_kg=critical_recovery,
            circularity_index=circularity,
            hazard_reduction_score=hazard_reduction,
            confidence=confidence,
            reasoning=reasoning,
            warnings=warnings,
            eco_id=context.eco_id,
            engine_version=engine_version,
            factors_version=factors_version,
            created_at=created_at,
        )

    def _contributions(
        self,
        materials: MaterialReport,
        library: FactorLibrary,
    ) -> tuple[MaterialContribution, ...]:
        """Aggregate recoverable materials by category into savings contributions.

        Each recoverable material whose confidence clears the floor adds its
        nominal mass to its category's running total; the category's per-kilogram
        factors then convert that mass into the avoided carbon/energy/water. The
        result is ordered by first appearance in the material report, so the
        breakdown is stable and mirrors the upstream ordering.
        """
        config = self._config
        by_category: OrderedDict[str, list[RecoveredMaterial]] = OrderedDict()
        for material in materials.materials:
            if not material.recoverable:
                continue
            if material.confidence <= config.min_material_confidence:
                continue
            by_category.setdefault(material.category.value, []).append(material)

        contributions: list[MaterialContribution] = []
        for grouped in by_category.values():
            category = grouped[0].category
            factor = library.factor_for(category)
            mass_g = _round_metric(sum(item.mass_g for item in grouped))
            mass_kg = mass_g / _GRAMS_PER_KG
            carbon = _round_metric(mass_kg * factor.carbon_kg_per_kg)
            energy = _round_metric(mass_kg * factor.energy_mj_per_kg)
            water = _round_metric(mass_kg * factor.water_l_per_kg)
            reason = (
                f"{mass_g:.3g} g of recoverable {category.value} avoids virgin "
                f"production at {factor.carbon_kg_per_kg:g} kg CO2e, "
                f"{factor.energy_mj_per_kg:g} MJ and {factor.water_l_per_kg:g} L "
                "per kg."
            )
            contributions.append(
                MaterialContribution(
                    category=category,
                    recovered_mass_g=mass_g,
                    carbon_saved_kg=carbon,
                    energy_saved_mj=energy,
                    water_saved_l=water,
                    critical=factor.critical,
                    reason=reason,
                )
            )
        return tuple(contributions)

    def _circularity_index(
        self,
        recoverability: RecoverabilityReport,
        materials: MaterialReport,
    ) -> float:
        """Blend the recoverable mass fraction with the recyclability score.

        The circularity index answers "how much of this device can re-enter the
        material loop": the share of its mass that is recoverable, weighted
        against the recoverability engine's own recyclability assessment. It is a
        unit index, independent of the absolute masses.
        """
        weight = self._config.circularity_recyclability_weight
        if materials.total_mass_g > 0.0:
            mass_fraction = materials.recoverable_mass_g / materials.total_mass_g
        else:
            mass_fraction = 0.0
        blended = mass_fraction * (1.0 - weight) + recoverability.recyclability * weight
        return _clamp_round(blended)

    def _hazard_reduction_score(
        self,
        recoverability: RecoverabilityReport,
        materials: MaterialReport,
    ) -> float:
        """Blend the assessed hazard severity with the hazardous mass diverted.

        The hazard-reduction score answers "how much hazard does correct handling
        remove from the environment": the assessed hazard severity (a device with
        no hazard yields nothing to reduce) scaled by how much hazardous mass is
        actually present to divert. It is a unit index.
        """
        weight = self._config.hazard_diversion_weight
        severity = _HAZARD_SEVERITY.get(recoverability.hazard_level, 0.0)
        if materials.total_mass_g > 0.0:
            hazardous_fraction = materials.hazardous_mass_g / materials.total_mass_g
        else:
            hazardous_fraction = 0.0
        blended = severity * ((1.0 - weight) + hazardous_fraction * weight)
        return _clamp_round(blended)

    def _overall_confidence(
        self,
        recoverability: RecoverabilityReport,
        materials: MaterialReport,
    ) -> float:
        """Blend the upstream material and recoverability confidences.

        The material report's overall confidence already folds in device-type
        familiarity and fusion conflicts (the material engine damped for both),
        so this engine simply blends it with the recoverability confidence rather
        than re-applying the same damping — which would double-count the signals.
        Confidence is a separate axis and never scales a metric.
        """
        weight = self._config.recoverability_confidence_weight
        blended = (
            materials.overall_confidence * (1.0 - weight)
            + recoverability.confidence * weight
        )
        return _clamp_round(blended)

    def _explain(
        self,
        *,
        recoverability: RecoverabilityReport,
        materials: MaterialReport,
        contributions: tuple[MaterialContribution, ...],
        carbon: float,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Build the ordered report-level reasoning and warnings."""
        reasoning: list[str] = []
        warnings: list[str] = []

        reasoning.append(
            f"Aggregated {len(contributions)} recoverable material "
            f"categor{'y' if len(contributions) == 1 else 'ies'} from the "
            f"material report into an avoided burden of {carbon:g} kg CO2e."
        )
        reasoning.append(
            "Savings are recovered mass times the external per-kilogram carbon, "
            "energy and water factors; masses are physical quantities and are "
            "never scaled by confidence."
        )
        reasoning.append(
            "Recoverability assessment "
            f"(recyclability {recoverability.recyclability:.2f}, hazard "
            f"'{recoverability.hazard_level.value}') shaped the circularity "
            "index and hazard-reduction score; confidence blends the material "
            "and recoverability confidences on a separate axis."
        )

        if not materials.materials:
            warnings.append(
                "Upstream material breakdown is empty; no environmental savings "
                "could be estimated."
            )
        elif not contributions:
            warnings.append(
                "No recoverable materials cleared the confidence floor; the "
                "environmental savings are zero."
            )

        if recoverability.hazard_level not in (
            HazardLevel.NONE,
            HazardLevel.UNKNOWN,
        ):
            warnings.append(
                "Device carries an assessed hazard; the hazard-reduction score "
                "is only realized if the hazardous stream is handled correctly."
            )

        if materials.device_type == "":
            warnings.append(
                "Device type is unresolved; the environmental estimate rests on "
                "a generic material breakdown and should be confirmed."
            )

        return tuple(reasoning), tuple(warnings)
