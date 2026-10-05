"""Environmental domain models (milestone M1.11).

The Environmental Intelligence Engine turns an immutable
:class:`~device_ai.fusion.models.DeviceContext` (fusion, M1.7), a
:class:`~device_ai.recoverability.models.RecoverabilityReport` (recoverability,
M1.8), a :class:`~device_ai.components.models.ComponentReport` (components, M1.9)
and a :class:`~device_ai.materials.models.MaterialReport` (materials, M1.10) into
an explainable :class:`EnvironmentalImpactReport`: the avoided environmental
burden of recovering the device rather than sending it to landfill.

The value objects here are the vocabulary that makes that estimate auditable:

* :class:`MaterialContribution` — the per-material-category breakdown of the
  resource-savings metrics: how much recovered mass of one category is, and the
  carbon/energy/water it avoids by displacing virgin production. Summing the
  contributions yields the report's carbon/energy/water totals, so the estimate
  is transparent rather than a black-box number.
* :class:`EnvironmentalImpactReport` — the normalized, immutable outcome: the
  seven headline metrics (carbon saved, energy saved, water saved, landfill
  diversion, critical-material recovery, circularity index and hazard-reduction
  score), a **separate** confidence axis, ordered human-readable reasoning and
  provenance (EcoID, device type, engine and factor-catalogue versions,
  timestamp).

The seven metrics fall on two axes the engine keeps strictly apart:

* **Physical quantities** — carbon (kg CO₂e), energy (MJ), water (L), landfill
  diversion (kg) and critical-material recovery (kg) are real amounts, rounded
  but **never** clamped to a unit interval.
* **Unit indices** — the circularity index and the hazard-reduction score are
  normalized ``[0, 1]`` measures.

Confidence is a third, wholly independent axis: it never scales a metric, so the
"how much was saved" and the "how sure are we" questions stay separable.

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the fusion,
recoverability, component and material domain layers it builds on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..materials.models import MaterialCategory


@dataclass(frozen=True, slots=True)
class MaterialContribution:
    """One material category's contribution to the resource-savings metrics.

    A device's recovered materials are grouped by :class:`MaterialCategory`; each
    group contributes an avoided burden equal to its recovered mass times that
    category's per-kilogram conversion factors from the external catalogue. The
    report's carbon/energy/water totals are exactly the sum of these
    contributions, which is what makes those metrics explainable.

    Attributes:
        category: The :class:`MaterialCategory` this contribution aggregates.
        recovered_mass_g: Recovered mass in grams of this category (the sum of
            the recoverable materials of this category in the material report).
        carbon_saved_kg: Carbon avoided (kg CO₂e) by recovering this mass rather
            than producing the material from virgin feedstock.
        energy_saved_mj: Primary energy avoided (megajoules) by this recovery.
        water_saved_l: Freshwater avoided (litres) by this recovery.
        critical: Whether this category counts toward critical-material recovery
            (precious metals, critical materials and rare earths).
        reason: Human-readable explanation of how the contribution was derived
            (the recovered mass and the per-kilogram factors applied).
    """

    category: MaterialCategory
    recovered_mass_g: float
    carbon_saved_kg: float
    energy_saved_mj: float
    water_saved_l: float
    critical: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the contribution."""
        return {
            "category": self.category.value,
            "recovered_mass_g": self.recovered_mass_g,
            "carbon_saved_kg": self.carbon_saved_kg,
            "energy_saved_mj": self.energy_saved_mj,
            "water_saved_l": self.water_saved_l,
            "critical": self.critical,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class EnvironmentalImpactReport:
    """The normalized, immutable environmental-impact estimate of one device.

    Produced by the
    :class:`~device_ai.environmental.service.EnvironmentalService` from a fused
    :class:`~device_ai.fusion.models.DeviceContext`, its
    :class:`~device_ai.recoverability.models.RecoverabilityReport`, its
    :class:`~device_ai.components.models.ComponentReport` and its
    :class:`~device_ai.materials.models.MaterialReport`. Downstream modules
    (passport, reporting) and operators consume this rather than re-deriving the
    avoided burden from raw masses.

    The five physical metrics (``carbon_saved_kg``, ``energy_saved_mj``,
    ``water_saved_l``, ``landfill_diversion_kg``, ``critical_material_recovery_kg``)
    are real quantities, rounded but never clamped. The two indices
    (``circularity_index``, ``hazard_reduction_score``) are normalized
    ``[0, 1]``. :attr:`confidence` is a separate axis and never scales a metric.

    Attributes:
        device_type: The resolved device type the estimate is for (may be empty
            when fusion could not determine it).
        contributions: The per-material-category resource-savings breakdown, in
            material-report order (may be empty when nothing is recoverable).
        carbon_saved_kg: Total carbon avoided (kg CO₂e) — the sum of the
            contributions' ``carbon_saved_kg``.
        energy_saved_mj: Total primary energy avoided (megajoules).
        water_saved_l: Total freshwater avoided (litres).
        landfill_diversion_kg: Recoverable mass (kilograms) diverted from
            landfill.
        critical_material_recovery_kg: Recovered mass (kilograms) of the
            critical categories (precious metal, critical material, rare earth).
        circularity_index: Normalized ``[0, 1]`` index blending the recoverable
            mass fraction with the recyclability score.
        hazard_reduction_score: Normalized ``[0, 1]`` score blending the assessed
            hazard severity with the hazardous mass fraction diverted.
        confidence: Aggregated confidence ``[0, 1]`` in the estimate as a whole,
            kept wholly separate from the metric values.
        reasoning: Ordered, human-readable reasons behind the estimate.
        warnings: Ordered operator-facing cautions (may be empty).
        eco_id: Public EcoID carried over from the device context (empty when
            the context had no fingerprint).
        engine_version: Version of the environmental engine that produced this.
        factors_version: Version of the external conversion-factor catalogue used.
        created_at: UTC timestamp the report was produced (``None`` when the
            service was constructed without a clock).
    """

    device_type: str
    contributions: tuple[MaterialContribution, ...]
    carbon_saved_kg: float
    energy_saved_mj: float
    water_saved_l: float
    landfill_diversion_kg: float
    critical_material_recovery_kg: float
    circularity_index: float
    hazard_reduction_score: float
    confidence: float
    reasoning: tuple[str, ...]
    warnings: tuple[str, ...]
    eco_id: str = ""
    engine_version: str = ""
    factors_version: str = ""
    created_at: datetime | None = None

    @property
    def contribution_count(self) -> int:
        """Return the number of material-category contributions."""
        return len(self.contributions)

    @property
    def total_recovered_mass_g(self) -> float:
        """Return the total recovered mass (grams) across all contributions."""
        return round(
            sum(contribution.recovered_mass_g for contribution in self.contributions),
            3,
        )

    @property
    def critical_contributions(self) -> tuple[MaterialContribution, ...]:
        """Return only the contributions that count as critical-material recovery."""
        return tuple(
            contribution for contribution in self.contributions if contribution.critical
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report.

        Returns:
            A plain ``dict`` with the ordered contribution breakdown, the seven
            headline metrics, the separate confidence, the reasoning/warnings,
            provenance and an ISO-8601 ``created_at`` (or ``None``).
        """
        return {
            "eco_id": self.eco_id,
            "device_type": self.device_type,
            "contributions": [
                contribution.to_dict() for contribution in self.contributions
            ],
            "contribution_count": self.contribution_count,
            "carbon_saved_kg": self.carbon_saved_kg,
            "energy_saved_mj": self.energy_saved_mj,
            "water_saved_l": self.water_saved_l,
            "landfill_diversion_kg": self.landfill_diversion_kg,
            "critical_material_recovery_kg": self.critical_material_recovery_kg,
            "circularity_index": self.circularity_index,
            "hazard_reduction_score": self.hazard_reduction_score,
            "confidence": self.confidence,
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
            "engine_version": self.engine_version,
            "factors_version": self.factors_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }
