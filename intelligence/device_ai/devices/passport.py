"""EcoTrace Device Passport & Traceability Domain Read Layer (P5.6).

Aggregates:
- Persistent DeviceRecord
- Multi-facet DeviceEnrichment
- Chronological DeviceEvent audit trail
- Detection and Model metadata

Provides a unified, read-oriented passport model without mutating the underlying domain entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .enrichment_models import DeviceEnrichment
from .models import DeviceEvent, DeviceRecord, RegistrationState


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DeviceIdentityFacet:
    """Device identification facet."""

    device_id: str
    eco_id: str | None
    device_type: str
    class_id: int
    capture_id: str
    registration_timestamp: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "eco_id": self.eco_id,
            "device_type": self.device_type,
            "class_id": self.class_id,
            "capture_id": self.capture_id,
            "registration_timestamp": self.registration_timestamp,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class DetectionFacet:
    """Computer vision detection facet."""

    confidence: float
    confidence_state: str
    bounding_box: list[int]
    inference_mode: str
    model_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "confidence_state": self.confidence_state,
            "bounding_box": self.bounding_box,
            "inference_mode": self.inference_mode,
            "model_version": self.model_version,
        }


@dataclass(frozen=True, slots=True)
class BrandFacet:
    """Brand intelligence facet."""

    brand: str | None
    status: str
    source: str
    confidence: float | None = None
    raw_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "brand": self.brand,
            "status": self.status,
            "source": self.source,
            "confidence": self.confidence,
            "raw_text": self.raw_text,
        }


@dataclass(frozen=True, slots=True)
class ConditionFacet:
    """Condition assessment facet."""

    condition: str | None
    status: str
    source: str
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "status": self.status,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class MaterialItemDetail:
    """Detailed breakdown of an individual material item."""

    material: str
    category: str
    mass_g: float
    recoverable: bool
    hazardous: bool
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "material": self.material,
            "category": self.category,
            "mass_g": self.mass_g,
            "recoverable": self.recoverable,
            "hazardous": self.hazardous,
            "basis": self.basis,
        }


@dataclass(frozen=True, slots=True)
class MaterialFacet:
    """Material composition and recoverability facet."""

    materials: list[MaterialItemDetail]
    total_mass_g: float | None
    source: str
    version: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "materials": [m.to_dict() for m in self.materials],
            "total_mass_g": self.total_mass_g,
            "source": self.source,
            "version": self.version,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class CarbonFacet:
    """Avoided carbon burden scoring facet."""

    carbon_score: float | None
    contributing_factors: dict[str, float]
    methodology: str | None = None
    source: str = "NONE"
    version: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "carbon_score": self.carbon_score,
            "contributing_factors": self.contributing_factors,
            "methodology": self.methodology,
            "source": self.source,
            "version": self.version,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class LifecycleFacet:
    """Lifecycle registration status facet."""

    current_state: str
    is_confirmed: bool
    is_registered: bool
    is_enriched: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_state": self.current_state,
            "is_confirmed": self.is_confirmed,
            "is_registered": self.is_registered,
            "is_enriched": self.is_enriched,
        }


@dataclass(frozen=True, slots=True)
class AuditFacet:
    """Chronological event audit trail facet."""

    total_events: int
    events: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "events": self.events,
        }


@dataclass(frozen=True, slots=True)
class DevicePassport:
    """Aggregated, read-oriented passport for an EcoTrace electronic device."""

    device_id: str
    eco_id: str | None
    identity: DeviceIdentityFacet
    detection: DetectionFacet
    brand: BrandFacet
    condition: ConditionFacet
    material: MaterialFacet
    carbon: CarbonFacet
    lifecycle: LifecycleFacet
    audit: AuditFacet
    generated_at: str = field(default_factory=lambda: _utc_now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert entire passport to JSON-serializable dictionary."""
        return {
            "device_id": self.device_id,
            "eco_id": self.eco_id,
            "identity": self.identity.to_dict(),
            "detection": self.detection.to_dict(),
            "brand": self.brand.to_dict(),
            "condition": self.condition.to_dict(),
            "material": self.material.to_dict(),
            "carbon": self.carbon.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "audit": self.audit.to_dict(),
            "generated_at": self.generated_at,
        }


def build_device_passport(record: DeviceRecord, events: list[DeviceEvent]) -> DevicePassport:
    """Construct a DevicePassport from a DeviceRecord and its audit events.

    Pure function: does not modify record or events, and performs zero I/O.
    """
    eco_id = record.metadata.get("eco_id")

    identity = DeviceIdentityFacet(
        device_id=record.device_id,
        eco_id=eco_id,
        device_type=record.device_type,
        class_id=record.class_id,
        capture_id=record.capture_id,
        registration_timestamp=record.created_at.isoformat(),
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )

    detection = DetectionFacet(
        confidence=round(record.confidence, 4),
        confidence_state=record.confidence_state.value,
        bounding_box=list(record.bounding_box),
        inference_mode=record.inference_mode,
        model_version=record.model_version,
    )

    # Check for enrichment snapshot in metadata
    enrichment_data = record.metadata.get("enrichment")
    is_enriched = enrichment_data is not None or record.carbon_score is not None

    if enrichment_data and isinstance(enrichment_data, dict):
        try:
            enrichment = DeviceEnrichment.from_dict(enrichment_data)
        except Exception:
            enrichment = None

        if enrichment is not None:
            brand = BrandFacet(
                brand=enrichment.brand.value,
                status=enrichment.brand.status,
                source=enrichment.brand.source,
                confidence=enrichment.brand.confidence,
                raw_text=enrichment.brand.raw_text,
            )

            condition = ConditionFacet(
                condition=enrichment.condition.value,
                status=enrichment.condition.status,
                source=enrichment.condition.source,
                notes=enrichment.condition.notes,
            )

            material_items = [
                MaterialItemDetail(
                    material=m.material,
                    category=m.category,
                    mass_g=m.mass_g,
                    recoverable=m.recoverable,
                    hazardous=m.hazardous,
                    basis=m.basis,
                )
                for m in enrichment.materials.materials
            ]
            material = MaterialFacet(
                materials=material_items,
                total_mass_g=enrichment.materials.total_mass_g,
                source=enrichment.materials.source,
                version=enrichment.materials.version,
                notes=enrichment.materials.notes,
            )

            carbon = CarbonFacet(
                carbon_score=enrichment.carbon.carbon_score,
                contributing_factors=dict(enrichment.carbon.contributing_factors),
                methodology=enrichment.carbon.methodology,
                source=enrichment.carbon.source,
                version=enrichment.carbon.version,
                notes=enrichment.carbon.notes,
            )
        else:
            brand = BrandFacet(brand=None, status="UNAVAILABLE", source="NONE")
            condition = ConditionFacet(condition=record.condition, status="UNAVAILABLE" if record.condition is None else "BASELINE", source="NONE")
            material = MaterialFacet(materials=[], total_mass_g=None, source="NONE", notes="Malformed enrichment data")
            carbon = CarbonFacet(carbon_score=record.carbon_score, contributing_factors={}, source="NONE", notes="Malformed enrichment data")
    else:
        # Device exists but has not undergone intelligence enrichment
        brand = BrandFacet(
            brand=None,
            status="UNAVAILABLE",
            source="NONE",
            confidence=None,
            raw_text=None,
        )
        condition = ConditionFacet(
            condition=record.condition,
            status="UNAVAILABLE" if record.condition is None else "BASELINE",
            source="NONE" if record.condition is None else "device_record",
            notes=None,
        )
        material = MaterialFacet(
            materials=[],
            total_mass_g=None,
            source="NONE",
            version=None,
            notes="Enrichment pending",
        )
        carbon = CarbonFacet(
            carbon_score=record.carbon_score,
            contributing_factors={},
            methodology=None,
            source="NONE" if record.carbon_score is None else "device_record",
            version=None,
            notes="Enrichment pending" if record.carbon_score is None else None,
        )

    is_confirmed = record.registration_state in (RegistrationState.CONFIRMED, RegistrationState.REGISTERED)
    is_registered = record.registration_state == RegistrationState.REGISTERED

    lifecycle = LifecycleFacet(
        current_state=record.registration_state.value,
        is_confirmed=is_confirmed,
        is_registered=is_registered,
        is_enriched=is_enriched,
    )

    # Sort events chronologically (oldest -> newest)
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    audit = AuditFacet(
        total_events=len(sorted_events),
        events=[e.to_dict() for e in sorted_events],
    )

    return DevicePassport(
        device_id=record.device_id,
        eco_id=eco_id,
        identity=identity,
        detection=detection,
        brand=brand,
        condition=condition,
        material=material,
        carbon=carbon,
        lifecycle=lifecycle,
        audit=audit,
    )
