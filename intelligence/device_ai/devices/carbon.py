"""Carbon intelligence interface and deterministic avoided-burden scoring (P5.3).

Computes estimated lifecycle avoided CO₂e based on nominal recoverable material mass
and established avoided-burden LCA conversion factors.

Adheres strictly to the principles:
- Clearly identify source as 'estimated_project_model'.
- Maintain deterministic, testable, and versioned calculations.
- Expose contributing factor breakdown per material category.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .enrichment_models import CarbonAssessment, MaterialAssessment

#: Avoided CO2e emissions (kg CO2e saved per kg of recovered material)
CATEGORY_CO2E_FACTORS_KG_PER_KG: dict[str, float] = {
    "metals": 5.0,           # Avoided smelting/refining of Al/Cu/Steel
    "circuit_boards": 18.0,   # Avoided high-intensity extraction of precious metals
    "battery": 8.5,          # Avoided extraction of Li, Co, Ni
    "plastics": 1.8,         # Avoided petrochemical polymer synthesis
    "glass": 0.7,            # Avoided virgin glass furnace melting
    "other": 0.5,            # Default fallback factor
}


@runtime_checkable
class CarbonIntelligence(Protocol):
    """Protocol interface for carbon scoring intelligence."""

    def assess_carbon(
        self,
        material_assessment: MaterialAssessment,
        version: str = "v1.0.0",
        methodology: str = "avoided_burden_co2e",
    ) -> CarbonAssessment:
        """Assess avoided carbon from material composition."""
        ...


class EstimatedBurdenCarbonIntelligence:
    """Deterministic carbon assessor computing avoided CO2e burden."""

    def __init__(
        self,
        factors: dict[str, float] | None = None,
    ) -> None:
        self._factors = factors or CATEGORY_CO2E_FACTORS_KG_PER_KG

    def assess_carbon(
        self,
        material_assessment: MaterialAssessment,
        version: str = "v1.0.0",
        methodology: str = "avoided_burden_co2e",
    ) -> CarbonAssessment:
        """Compute avoided carbon emissions in kg CO2e from recoverable materials.

        Args:
            material_assessment: Material assessment holding component specs.
            version: Model/calculation version.
            methodology: Methodological label.

        Returns:
            A :class:`CarbonAssessment` with full category contribution breakdown.
        """
        contributing_factors: dict[str, float] = {}
        total_co2e = 0.0

        for item in material_assessment.materials:
            if not item.recoverable:
                continue

            factor = self._factors.get(item.category.lower(), self._factors.get("other", 0.5))
            mass_kg = item.mass_g / 1000.0
            avoided_kg = mass_kg * factor

            cat = item.category.lower()
            contributing_factors[cat] = contributing_factors.get(cat, 0.0) + avoided_kg
            total_co2e += avoided_kg

        return CarbonAssessment(
            carbon_score=round(total_co2e, 4),
            methodology=methodology,
            version=version,
            source="estimated_project_model",
            contributing_factors={
                k: round(v, 4) for k, v in contributing_factors.items()
            },
            notes="Estimated avoided CO2e based on nominal recoverable material profile.",
        )
