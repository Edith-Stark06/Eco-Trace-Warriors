"""Material domain models (milestone M1.10).

The Material Intelligence Engine turns an immutable
:class:`~device_ai.fusion.models.DeviceContext` (fusion, M1.7), a
:class:`~device_ai.recoverability.models.RecoverabilityReport` (recoverability,
M1.8) and a :class:`~device_ai.components.models.ComponentReport` (components,
M1.9) into an explainable :class:`MaterialReport`: the recoverable and hazardous
materials the device is made of, each with an estimated mass and confidence,
plus recoverable/hazardous weight totals and ordered human-readable reasoning.

The value objects here are the vocabulary that makes that estimate auditable:

* :class:`MaterialCategory` — the coarse family a material belongs to (ferrous
  metal, precious metal, plastic, glass, battery material, …). A ``str`` enum so
  it serializes to its wire value directly and is the single source of truth the
  external profile library is validated against.
* :class:`RecoveredMaterial` — one material the engine estimates is recoverable
  from the device: its name, category, estimated mass, confidence,
  recovery/hazard flags, the source component categories it was derived from and
  the human-readable reason it was inferred.
* :class:`MaterialReport` — the normalized, immutable outcome: the ordered
  material list, the total/recoverable/hazardous mass totals, an aggregated
  overall confidence, the reasoning/warnings and provenance (EcoID, device type,
  engine and catalogue versions, timestamp).

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the fusion,
recoverability and component domain layers it builds on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MaterialCategory(str, Enum):
    """The coarse family a recovered material belongs to.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a catalogue string (e.g. ``"precious_metal"``). This enum is
    the single source of truth the external material-profile library is validated
    against on load — a catalogue entry naming a category outside this set is
    rejected.
    """

    FERROUS_METAL = "ferrous_metal"
    NON_FERROUS_METAL = "non_ferrous_metal"
    PRECIOUS_METAL = "precious_metal"
    CRITICAL_MATERIAL = "critical_material"
    RARE_EARTH = "rare_earth"
    PLASTIC = "plastic"
    GLASS = "glass"
    CERAMIC = "ceramic"
    BATTERY_MATERIAL = "battery_material"
    HAZARDOUS = "hazardous"
    OTHER = "other"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every category, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class RecoveredMaterial:
    """One material the engine estimates is recoverable from the device.

    Attributes:
        name: Human-readable material name (e.g. ``"Aluminium chassis"``).
        category: The coarse :class:`MaterialCategory` the material belongs to.
        mass_g: Estimated nominal mass in grams the device contains of this
            material (the catalogue nominal, never scaled by confidence).
        confidence: Normalized ``[0, 1]`` confidence the material is actually
            recoverable in the estimated amount, derived from the presence
            confidence of its source components and the overall inventory
            confidence.
        recoverable: Whether the material carries meaningful material-recovery
            value.
        hazardous: Whether the material needs hazardous handling (leaded glass,
            battery electrolyte, solder lead).
        source_components: The component-category wire values (from the consumed
            :class:`~device_ai.components.models.ComponentReport`) this material
            was derived from (empty for unconditional structural materials).
        reason: Human-readable explanation of how the estimate was derived (the
            source components and the confidence linkage applied).
    """

    name: str
    category: MaterialCategory
    mass_g: float
    confidence: float
    recoverable: bool
    hazardous: bool
    source_components: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the material."""
        return {
            "name": self.name,
            "category": self.category.value,
            "mass_g": self.mass_g,
            "confidence": self.confidence,
            "recoverable": self.recoverable,
            "hazardous": self.hazardous,
            "source_components": list(self.source_components),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class MaterialReport:
    """The normalized, immutable material estimate of one device.

    Produced by the
    :class:`~device_ai.materials.service.MaterialService` from a fused
    :class:`~device_ai.fusion.models.DeviceContext`, its
    :class:`~device_ai.recoverability.models.RecoverabilityReport` and its
    :class:`~device_ai.components.models.ComponentReport`. Downstream modules
    (carbon, passport) and operators consume this rather than re-deriving a
    material breakdown from raw identity fields.

    Attributes:
        device_type: The resolved device type the estimate is for (may be empty
            when fusion could not determine it).
        materials: The recovered materials, in catalogue order, each with its own
            estimated mass, confidence and reason (may be empty).
        total_mass_g: Sum of the estimated mass of every listed material (grams).
        recoverable_mass_g: Sum of the estimated mass of the materials flagged
            recoverable (grams).
        hazardous_mass_g: Sum of the estimated mass of the materials flagged
            hazardous (grams).
        overall_confidence: Aggregated confidence ``[0, 1]`` in the estimate as a
            whole (driven by device-type identification, profile familiarity,
            fusion conflicts and the recoverability assessment).
        reasoning: Ordered, human-readable reasons behind the estimate.
        warnings: Ordered operator-facing cautions (may be empty).
        eco_id: Public EcoID carried over from the device context (empty when
            the context had no fingerprint).
        engine_version: Version of the material engine that produced this.
        profile_version: Version of the external material catalogue used.
        created_at: UTC timestamp the report was produced (``None`` when the
            service was constructed without a clock).
    """

    device_type: str
    materials: tuple[RecoveredMaterial, ...]
    total_mass_g: float
    recoverable_mass_g: float
    hazardous_mass_g: float
    overall_confidence: float
    reasoning: tuple[str, ...]
    warnings: tuple[str, ...]
    eco_id: str = ""
    engine_version: str = ""
    profile_version: str = ""
    created_at: datetime | None = None

    @property
    def material_count(self) -> int:
        """Return the number of recovered materials in the estimate."""
        return len(self.materials)

    @property
    def recoverable_materials(self) -> tuple[RecoveredMaterial, ...]:
        """Return only the materials flagged as carrying recovery value."""
        return tuple(material for material in self.materials if material.recoverable)

    @property
    def hazardous_materials(self) -> tuple[RecoveredMaterial, ...]:
        """Return only the materials flagged as needing hazardous handling."""
        return tuple(material for material in self.materials if material.hazardous)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report.

        Returns:
            A plain ``dict`` with the ordered material list, the mass totals, the
            overall confidence, the reasoning/warnings, provenance and an
            ISO-8601 ``created_at`` (or ``None``).
        """
        return {
            "eco_id": self.eco_id,
            "device_type": self.device_type,
            "materials": [material.to_dict() for material in self.materials],
            "material_count": self.material_count,
            "total_mass_g": self.total_mass_g,
            "recoverable_mass_g": self.recoverable_mass_g,
            "hazardous_mass_g": self.hazardous_mass_g,
            "overall_confidence": self.overall_confidence,
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
            "engine_version": self.engine_version,
            "profile_version": self.profile_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }
