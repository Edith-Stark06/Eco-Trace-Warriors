"""Domain models and lifecycle states for the EcoTrace Device Registration Workflow (P5.2).

Defines:
- :class:`ConfidenceState`: Confidence classification policy (HIGH, REVIEW_REQUIRED, LOW).
- :class:`RegistrationState`: Explicit lifecycle stages (DETECTED -> CONFIRMED -> REGISTERED).
- :class:`DeviceCandidate`: An individual device candidate detected from a capture session.
- :class:`DeviceRecord`: Normalized, persistent domain record for a device.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ..inference.class_map import CANONICAL_CLASSES, CLASS_NAME_TO_ID


class ConfidenceState(str, Enum):
    """Confidence classification policy for detected device candidates."""

    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class RegistrationState(str, Enum):
    """Explicit domain lifecycle states for an EcoTrace device."""

    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    REGISTERED = "REGISTERED"


# Allowed state transitions in the domain lifecycle.
VALID_STATE_TRANSITIONS: dict[RegistrationState, set[RegistrationState]] = {
    RegistrationState.DETECTED: {RegistrationState.CONFIRMED},
    RegistrationState.CONFIRMED: {RegistrationState.REGISTERED},
    RegistrationState.REGISTERED: set(),  # Terminal state for P5.2
}


def _utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DeviceCandidate:
    """An individual device candidate detected in an image capture.

    Attributes:
        candidate_id: Unique candidate identifier.
        capture_id: Correlation ID for the image capture session.
        class_id: Canonical taxonomy class index (0..7).
        device_type: Canonical class label (e.g. 'laptop').
        confidence: Detection confidence score [0.0, 1.0].
        confidence_state: Policy-classified confidence state.
        bounding_box: (x1, y1, x2, y2) pixel bounding box coordinates.
        model_version: Underlying model version string.
        inference_mode: Active inference strategy ('single_model' | 'ensemble').
        created_at: Timestamp when candidate was identified.
    """

    candidate_id: str
    capture_id: str
    class_id: int
    device_type: str
    confidence: float
    confidence_state: ConfidenceState
    bounding_box: tuple[int, int, int, int]
    model_version: str
    inference_mode: str
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class DeviceRecord:
    """Persistent domain record for an EcoTrace device.

    Attributes:
        device_id: Unique public device identifier (e.g. DEV-YYYY-XXXXXXXX).
        capture_id: Correlation ID for the capture session that originated this device.
        class_id: Canonical taxonomy class index (0..7).
        device_type: Canonical class label (e.g. 'laptop').
        confidence: Detection confidence score [0.0, 1.0].
        confidence_state: Policy-classified confidence state.
        bounding_box: (x1, y1, x2, y2) pixel bounding box coordinates.
        model_version: Underlying model version string.
        inference_mode: Active inference strategy ('single_model' | 'ensemble').
        registration_state: Current domain lifecycle state.
        condition: Optional assessed condition label (null/pending in P5.2).
        materials: Optional recoverable materials composition (null/pending in P5.2).
        carbon_score: Optional carbon recovery score (null/pending in P5.2).
        metadata: Structured diagnostic and contextual metadata.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    device_id: str
    capture_id: str
    class_id: int
    device_type: str
    confidence: float
    confidence_state: ConfidenceState
    bounding_box: tuple[int, int, int, int]
    model_version: str
    inference_mode: str
    registration_state: RegistrationState = RegistrationState.DETECTED
    condition: str | None = None
    materials: dict[str, float] | None = None
    carbon_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def can_transition_to(self, new_state: RegistrationState) -> bool:
        """Check if transitioning to ``new_state`` is valid from the current state."""
        return new_state in VALID_STATE_TRANSITIONS.get(self.registration_state, set())

    def transition_to(self, new_state: RegistrationState) -> None:
        """Transition this device record to ``new_state``.

        Args:
            new_state: Target RegistrationState.

        Raises:
            ValueError: If the transition is not permitted.
        """
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"Cannot transition device '{self.device_id}' from "
                f"'{self.registration_state.value}' to '{new_state.value}'."
            )
        self.registration_state = new_state
        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "device_id": self.device_id,
            "capture_id": self.capture_id,
            "class_id": self.class_id,
            "device_type": self.device_type,
            "confidence": round(self.confidence, 4),
            "confidence_state": self.confidence_state.value,
            "bounding_box": list(self.bounding_box),
            "model_version": self.model_version,
            "inference_mode": self.inference_mode,
            "registration_state": self.registration_state.value,
            "condition": self.condition,
            "materials": self.materials,
            "carbon_score": self.carbon_score,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceRecord:
        """Construct a DeviceRecord from a serialized dictionary."""
        return cls(
            device_id=data["device_id"],
            capture_id=data["capture_id"],
            class_id=int(data["class_id"]),
            device_type=data["device_type"],
            confidence=float(data["confidence"]),
            confidence_state=ConfidenceState(data["confidence_state"]),
            bounding_box=tuple(data["bounding_box"])[:4],  # type: ignore[arg-type]
            model_version=data["model_version"],
            inference_mode=data["inference_mode"],
            registration_state=RegistrationState(data["registration_state"]),
            condition=data.get("condition"),
            materials=data.get("materials"),
            carbon_score=data.get("carbon_score"),
            metadata=dict(data.get("metadata", {})),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


class DeviceEventType(str, Enum):
    """Supported domain event types for the device audit trail."""

    DEVICE_DETECTED = "DEVICE_DETECTED"
    DEVICE_CONFIRMED = "DEVICE_CONFIRMED"
    DEVICE_REGISTERED = "DEVICE_REGISTERED"
    DEVICE_ENRICHED = "DEVICE_ENRICHED"
    DEVICE_EXTERNALLY_ANCHORED = "DEVICE_EXTERNALLY_ANCHORED"


@dataclass(frozen=True, slots=True)
class DeviceEvent:
    """Immutable domain representation of a device lifecycle/audit event.

    Attributes:
        event_id: Unique event identifier (e.g. 'evt-...').
        device_id: Identifier of the device this event belongs to.
        event_type: Type of the lifecycle/audit event.
        timestamp: Time at which the event occurred (UTC).
        capture_id: Optional correlation ID for the capture session.
        metadata: Additional contextual structured details.
    """

    event_id: str
    device_id: str
    event_type: DeviceEventType
    timestamp: datetime = field(default_factory=_utc_now)
    capture_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to a JSON-serializable dictionary."""
        return {
            "event_id": self.event_id,
            "device_id": self.device_id,
            "event_type": self.event_type.value if isinstance(self.event_type, DeviceEventType) else str(self.event_type),
            "timestamp": self.timestamp.isoformat(),
            "capture_id": self.capture_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceEvent:
        """Construct a DeviceEvent from a serialized dictionary."""
        raw_ts = data["timestamp"]
        ts = datetime.fromisoformat(raw_ts) if isinstance(raw_ts, str) else raw_ts
        return cls(
            event_id=data["event_id"],
            device_id=data["device_id"],
            event_type=DeviceEventType(data["event_type"]),
            timestamp=ts,
            capture_id=data.get("capture_id"),
            metadata=dict(data.get("metadata", {})),
        )
