"""Domain models for Device Intelligence Enrichment (P5.3).

Defines explicit assessment value objects for:
- :class:`BrandAssessment`: OCR-derived or unknown brand identity.
- :class:`ConditionAssessment`: Baseline conservative condition assessment.
- :class:`MaterialAssessment` & :class:`MaterialItem`: Deterministic category material profiles.
- :class:`CarbonAssessment`: Deterministic avoided-burden carbon scoring.
- :class:`DeviceEnrichment`: Aggregate container for all enrichment facets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class BrandAssessment:
    """Assessment of device brand/manufacturer identity.

    Attributes:
        value: Canonical brand name (e.g. 'Dell', 'Apple') or None if unknown.
        status: Assessment status ('CONFIRMED' | 'UNKNOWN').
        source: Provenance source ('ocr' | 'none').
        confidence: Recognition confidence score in [0.0, 1.0] if OCR matched, else None.
        raw_text: The matched OCR text token, if available.
    """

    value: str | None
    status: str = "UNKNOWN"
    source: str = "none"
    confidence: float | None = None
    raw_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert assessment to dictionary."""
        return {
            "value": self.value,
            "status": self.status,
            "source": self.source,
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
            "raw_text": self.raw_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrandAssessment:
        """Construct from dictionary."""
        return cls(
            value=data.get("value"),
            status=data.get("status", "UNKNOWN"),
            source=data.get("source", "none"),
            confidence=data.get("confidence"),
            raw_text=data.get("raw_text"),
        )


@dataclass(frozen=True, slots=True)
class ConditionAssessment:
    """Assessment of device physical wear/condition.

    Attributes:
        value: Condition state ('EXCELLENT' | 'GOOD' | 'FAIR' | 'POOR' | 'UNKNOWN').
        status: Availability status ('AVAILABLE' | 'UNAVAILABLE').
        source: Provenance source (e.g. 'pending_assessment', 'manual_inspection').
        confidence: Confidence score if evaluated, else None.
        notes: Contextual notes regarding assessment methodology.
    """

    value: str = "UNKNOWN"
    status: str = "UNAVAILABLE"
    source: str = "pending_assessment"
    confidence: float | None = None
    notes: str = "Baseline condition policy: visual condition assessment model pending."

    def to_dict(self) -> dict[str, Any]:
        """Convert assessment to dictionary."""
        return {
            "value": self.value,
            "status": self.status,
            "source": self.source,
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConditionAssessment:
        """Construct from dictionary."""
        return cls(
            value=data.get("value", "UNKNOWN"),
            status=data.get("status", "UNAVAILABLE"),
            source=data.get("source", "pending_assessment"),
            confidence=data.get("confidence"),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True, slots=True)
class MaterialItem:
    """An individual estimated material component.

    Attributes:
        material: Descriptive material name (e.g. 'Aluminium chassis').
        category: Coarse material category ('metals' | 'plastics' | 'glass' | 'battery' | 'circuit_boards' | 'other').
        mass_g: Nominal mass in grams.
        recoverable: Whether the material is recyclable/recoverable.
        hazardous: Whether the material requires specialized hazardous handling.
        basis: Methodological basis ('device_profile').
    """

    material: str
    category: str
    mass_g: float
    recoverable: bool = True
    hazardous: bool = False
    basis: str = "device_profile"

    def to_dict(self) -> dict[str, Any]:
        """Convert material item to dictionary."""
        return {
            "material": self.material,
            "category": self.category,
            "mass_g": round(self.mass_g, 2),
            "recoverable": self.recoverable,
            "hazardous": self.hazardous,
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MaterialItem:
        """Construct from dictionary."""
        return cls(
            material=data["material"],
            category=data["category"],
            mass_g=float(data["mass_g"]),
            recoverable=bool(data.get("recoverable", True)),
            hazardous=bool(data.get("hazardous", False)),
            basis=data.get("basis", "device_profile"),
        )


@dataclass(frozen=True, slots=True)
class MaterialAssessment:
    """Assessment of recoverable materials in a device.

    Attributes:
        materials: List of individual material components.
        total_mass_g: Total estimated nominal mass in grams.
        source: Provenance source ('device_profile').
        version: Profile catalogue version (e.g. 'v1.0.0').
        notes: Explanatory notes.
    """

    materials: list[MaterialItem] = field(default_factory=list)
    total_mass_g: float = 0.0
    source: str = "device_profile"
    version: str = "v1.0.0"
    notes: str = "Estimated composition from deterministic device-category profile."

    def to_dict(self) -> dict[str, Any]:
        """Convert assessment to dictionary."""
        return {
            "materials": [m.to_dict() for m in self.materials],
            "total_mass_g": round(self.total_mass_g, 2),
            "source": self.source,
            "version": self.version,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MaterialAssessment:
        """Construct from dictionary."""
        items = [MaterialItem.from_dict(m) for m in data.get("materials", [])]
        return cls(
            materials=items,
            total_mass_g=float(data.get("total_mass_g", sum(m.mass_g for m in items))),
            source=data.get("source", "device_profile"),
            version=data.get("version", "v1.0.0"),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True, slots=True)
class CarbonAssessment:
    """Assessment of carbon recovery potential / avoided burden.

    Attributes:
        carbon_score: Avoided burden in kg CO₂e.
        methodology: Calculation method ('avoided_burden_co2e').
        version: Model version ('v1.0.0').
        source: Provenance source ('estimated_project_model').
        contributing_factors: Avoided kg CO₂e breakdown by material category.
        notes: Explanatory notes.
    """

    carbon_score: float = 0.0
    methodology: str = "avoided_burden_co2e"
    version: str = "v1.0.0"
    source: str = "estimated_project_model"
    contributing_factors: dict[str, float] = field(default_factory=dict)
    notes: str = "Estimated avoided CO2e based on nominal recoverable material profile."

    def to_dict(self) -> dict[str, Any]:
        """Convert assessment to dictionary."""
        return {
            "carbon_score": round(self.carbon_score, 4),
            "methodology": self.methodology,
            "version": self.version,
            "source": self.source,
            "contributing_factors": {
                k: round(v, 4) for k, v in self.contributing_factors.items()
            },
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CarbonAssessment:
        """Construct from dictionary."""
        return cls(
            carbon_score=float(data.get("carbon_score", 0.0)),
            methodology=data.get("methodology", "avoided_burden_co2e"),
            version=data.get("version", "v1.0.0"),
            source=data.get("source", "estimated_project_model"),
            contributing_factors=dict(data.get("contributing_factors", {})),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True, slots=True)
class DeviceEnrichment:
    """Aggregated intelligence enrichment for an EcoTrace device.

    Attributes:
        device_id: Public device identifier.
        brand: Brand assessment facet.
        condition: Condition assessment facet.
        materials: Material composition facet.
        carbon: Carbon avoided burden facet.
        enriched_at: Timestamp when enrichment occurred.
    """

    device_id: str
    brand: BrandAssessment
    condition: ConditionAssessment
    materials: MaterialAssessment
    carbon: CarbonAssessment
    enriched_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Convert aggregate enrichment to dictionary."""
        return {
            "device_id": self.device_id,
            "brand": self.brand.to_dict(),
            "condition": self.condition.to_dict(),
            "materials": self.materials.to_dict(),
            "carbon": self.carbon.to_dict(),
            "enriched_at": self.enriched_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceEnrichment:
        """Construct from dictionary."""
        return cls(
            device_id=data["device_id"],
            brand=BrandAssessment.from_dict(data.get("brand", {})),
            condition=ConditionAssessment.from_dict(data.get("condition", {})),
            materials=MaterialAssessment.from_dict(data.get("materials", {})),
            carbon=CarbonAssessment.from_dict(data.get("carbon", {})),
            enriched_at=datetime.fromisoformat(data["enriched_at"])
            if "enriched_at" in data
            else _utc_now(),
        )
