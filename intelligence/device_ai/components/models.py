"""Component domain models (milestone M1.9).

The Component Intelligence Engine turns an immutable
:class:`~device_ai.fusion.models.DeviceContext` (fusion, M1.7) and a
:class:`~device_ai.recoverability.models.RecoverabilityReport` (recoverability,
M1.8) into an explainable :class:`ComponentReport`: the likely internal
electronic components of the device, each with a presence confidence, plus a
single overall confidence and ordered human-readable reasoning.

The value objects here are the vocabulary that makes that inventory auditable:

* :class:`ComponentCategory` — the coarse family a component belongs to
  (battery, circuit board, display, …). A ``str`` enum so it serializes to its
  wire value directly and is the single source of truth the external profile
  library is validated against.
* :class:`InferredComponent` — one component the engine believes is present:
  its name, category, presence confidence, hazard/recovery flags and the
  human-readable reason it was inferred.
* :class:`ComponentReport` — the normalized, immutable outcome: the ordered
  component list, an aggregated overall confidence, the reasoning/warnings and
  provenance (EcoID, device type, engine and catalogue versions, timestamp).

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the fusion
and recoverability domain layers it builds on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ComponentCategory(str, Enum):
    """The coarse family an inferred component belongs to.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a catalogue string (e.g. ``"circuit_board"``). This enum is
    the single source of truth the external component-profile library is
    validated against on load — a catalogue entry naming a category outside this
    set is rejected.
    """

    BATTERY = "battery"
    CIRCUIT_BOARD = "circuit_board"
    PROCESSOR = "processor"
    MEMORY = "memory"
    STORAGE = "storage"
    DISPLAY = "display"
    CONNECTIVITY = "connectivity"
    INPUT = "input"
    CAMERA = "camera"
    SENSOR = "sensor"
    POWER = "power"
    AUDIO = "audio"
    OPTICS = "optics"
    OPTICAL_MEDIA = "optical_media"
    CABLING = "cabling"
    HOUSING = "housing"
    OTHER = "other"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every category, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class InferredComponent:
    """One internal component the engine infers is present in the device.

    Attributes:
        name: Human-readable component name (e.g. ``"Lithium-ion battery"``).
        category: The coarse :class:`ComponentCategory` the component belongs to.
        presence_confidence: Normalized ``[0, 1]`` confidence the component is
            actually present in this device, after identity/recoverability
            corroboration is applied to the catalogue prior.
        hazardous: Whether the component needs hazardous handling (batteries,
            CRT leaded glass, backlight lamps).
        recoverable: Whether the component carries meaningful reuse/material
            recovery value.
        reason: Human-readable explanation of how the presence confidence was
            derived (the prior and any corroboration applied).
    """

    name: str
    category: ComponentCategory
    presence_confidence: float
    hazardous: bool
    recoverable: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the component."""
        return {
            "name": self.name,
            "category": self.category.value,
            "presence_confidence": self.presence_confidence,
            "hazardous": self.hazardous,
            "recoverable": self.recoverable,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ComponentReport:
    """The normalized, immutable component inventory of one device.

    Produced by the
    :class:`~device_ai.components.service.ComponentService` from a fused
    :class:`~device_ai.fusion.models.DeviceContext` and its
    :class:`~device_ai.recoverability.models.RecoverabilityReport`. Downstream
    modules (material, carbon, passport) and operators consume this rather than
    re-deriving a component list from raw identity fields.

    Attributes:
        device_type: The resolved device type the inventory is for (may be empty
            when fusion could not determine it).
        components: The inferred components, in catalogue order, each with its
            own presence confidence and reason (may be empty).
        overall_confidence: Aggregated confidence ``[0, 1]`` in the inventory as
            a whole (driven by device-type identification, profile familiarity,
            fusion conflicts and the recoverability assessment).
        reasoning: Ordered, human-readable reasons behind the inventory.
        warnings: Ordered operator-facing cautions (may be empty).
        eco_id: Public EcoID carried over from the device context (empty when
            the context had no fingerprint).
        engine_version: Version of the component engine that produced this.
        profile_version: Version of the external component catalogue used.
        created_at: UTC timestamp the report was produced (``None`` when the
            service was constructed without a clock).
    """

    device_type: str
    components: tuple[InferredComponent, ...]
    overall_confidence: float
    reasoning: tuple[str, ...]
    warnings: tuple[str, ...]
    eco_id: str = ""
    engine_version: str = ""
    profile_version: str = ""
    created_at: datetime | None = None

    @property
    def component_count(self) -> int:
        """Return the number of inferred components in the inventory."""
        return len(self.components)

    @property
    def hazardous_components(self) -> tuple[InferredComponent, ...]:
        """Return only the components flagged as needing hazardous handling."""
        return tuple(component for component in self.components if component.hazardous)

    @property
    def recoverable_components(self) -> tuple[InferredComponent, ...]:
        """Return only the components flagged as carrying recovery value."""
        return tuple(
            component for component in self.components if component.recoverable
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report.

        Returns:
            A plain ``dict`` with the ordered component list, the overall
            confidence, the reasoning/warnings, provenance and an ISO-8601
            ``created_at`` (or ``None``).
        """
        return {
            "eco_id": self.eco_id,
            "device_type": self.device_type,
            "components": [component.to_dict() for component in self.components],
            "component_count": self.component_count,
            "overall_confidence": self.overall_confidence,
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
            "engine_version": self.engine_version,
            "profile_version": self.profile_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }
