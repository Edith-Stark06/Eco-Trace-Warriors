"""Device Registration and Intelligence Workflow Service (P5.2).

Orchestrates the transition from multi-image computer vision inference to
domain-level device candidates, lifecycle management, and persistence.

Key capabilities:
- Consumes :class:`~device_ai.inference.pipeline.PredictionPipeline` without direct model coupling.
- Supports multi-detection parsing: each physical device detected produces an independent candidate/record.
- Enforces configurable confidence classification policy (HIGH, REVIEW_REQUIRED, LOW).
- Enforces valid lifecycle state machine transitions (DETECTED -> CONFIRMED -> REGISTERED).
- Persists domain records via :class:`~device_ai.devices.repository.DeviceRepository`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import uuid

from loguru import logger

from ..configs.settings import Settings
from ..exceptions import (
    DeviceNotFoundError,
    DuplicateDeviceError,
    InvalidDeviceClassError,
    InvalidStateTransitionError,
    NoDetectionsForRegistrationError,
)
from ..inference.class_map import CANONICAL_CLASSES, CLASS_NAME_TO_ID
from ..inference.pipeline import PredictionPipeline
from ..preprocessing.image_loader import LoadedImage
from .models import (
    ConfidenceState,
    DeviceCandidate,
    DeviceRecord,
    RegistrationState,
)
from .repository import DeviceRepository


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


class DeviceRegistrationService:
    """Orchestration service for device registration and lifecycle workflows.

    Args:
        repository: Persistent repository for DeviceRecord entities.
        pipeline: Prediction pipeline supplying computer-vision inference.
        settings: Application settings with confidence thresholds and mode.
    """

    def __init__(
        self,
        *,
        repository: DeviceRepository,
        pipeline: PredictionPipeline,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._pipeline = pipeline
        self._settings = settings

    def classify_confidence(self, confidence: float) -> ConfidenceState:
        """Classify detection confidence against configured policy thresholds.

        Args:
            confidence: Model confidence score in [0.0, 1.0].

        Returns:
            The policy :class:`ConfidenceState`.
        """
        if confidence >= self._settings.confidence_high_threshold:
            return ConfidenceState.HIGH_CONFIDENCE
        if confidence >= self._settings.confidence_review_threshold:
            return ConfidenceState.REVIEW_REQUIRED
        return ConfidenceState.LOW_CONFIDENCE

    def register_from_images(
        self,
        images: list[LoadedImage],
        capture_id: str | None = None,
    ) -> tuple[list[DeviceRecord], dict[str, float]]:
        """Run inference over capture images and register detected device records.

        Args:
            images: Decoded, validated images from a registration session.
            capture_id: Optional correlation capture/session ID. Generated if omitted.

        Returns:
            A tuple of ``(created_device_records, timing_dict)``.

        Raises:
            NoDetectionsForRegistrationError: If zero electronic devices were detected.
            InvalidDeviceClassError: If a detection has an unmapped class.
            DuplicateDeviceError: If a generated device ID already exists.
        """
        if not capture_id:
            capture_id = f"cap-{uuid.uuid4().hex[:12]}"

        # Execute inference pipeline with timing breakdown.
        result, timing = self._pipeline.predict_with_timing(images)
        detections = result.detection.detections

        if not detections:
            logger.bind(capture_id=capture_id).warning(
                "Registration rejected: zero electronic devices detected in capture."
            )
            raise NoDetectionsForRegistrationError(
                f"No electronic devices detected in capture session '{capture_id}'.",
                details={"capture_id": capture_id},
            )

        year = _utc_now().year
        created_records: list[DeviceRecord] = []

        for idx, det in enumerate(detections, start=1):
            canonical_label = det.label.lower()
            class_id = CLASS_NAME_TO_ID.get(canonical_label)

            if class_id is None:
                raise InvalidDeviceClassError(
                    f"Unsupported device class '{det.label}'.",
                    details={"label": det.label, "canonical_classes": CANONICAL_CLASSES},
                )

            conf_state = self.classify_confidence(det.confidence)
            # Deterministic, unique device ID keyed by year, capture session, and index.
            device_id = f"DEV-{year}-{capture_id[-8:].upper()}-{idx:02d}"

            if self._repository.exists(device_id):
                raise DuplicateDeviceError(
                    f"Device record '{device_id}' already exists.",
                    details={"device_id": device_id, "capture_id": capture_id},
                )

            record = DeviceRecord(
                device_id=device_id,
                capture_id=capture_id,
                class_id=class_id,
                device_type=canonical_label,
                confidence=round(det.confidence, 4),
                confidence_state=conf_state,
                bounding_box=det.bounding_box,
                model_version=result.model_version,
                inference_mode=self._settings.inference_mode,
                registration_state=RegistrationState.DETECTED,
                condition=None,      # Pending condition subsystem (P5.2 Step 7)
                materials=None,      # Pending material subsystem (P5.2 Step 7)
                carbon_score=None,   # Pending carbon subsystem (P5.2 Step 7)
                metadata={
                    "eco_id": result.eco_id,
                    "image_count": len(images),
                },
            )

            self._repository.save(record)
            if hasattr(self._repository, "record_event"):
                self._repository.record_event(
                    event_type="DEVICE_DETECTED",
                    device_id=record.device_id,
                    capture_id=record.capture_id,
                    metadata={"confidence": record.confidence, "device_type": record.device_type},
                )
            created_records.append(record)

        logger.bind(
            capture_id=capture_id,
            devices_created=len(created_records),
            inference_mode=self._settings.inference_mode,
        ).info("Device registration session processed successfully")

        return created_records, timing

    def get_device(self, device_id: str) -> DeviceRecord:
        """Retrieve a device record by its ID.

        Args:
            device_id: Public device identifier.

        Returns:
            The stored :class:`DeviceRecord`.

        Raises:
            DeviceNotFoundError: If no record matches ``device_id``.
        """
        record = self._repository.get(device_id)
        if record is None:
            raise DeviceNotFoundError(
                f"Device '{device_id}' not found.",
                details={"device_id": device_id},
            )
        return record

    def find_by_capture(self, capture_id: str) -> list[DeviceRecord]:
        """Return all devices created from a specific capture session."""
        return self._repository.find_by_capture_id(capture_id)

    def list_devices(self, limit: int = 100, offset: int = 0) -> list[DeviceRecord]:
        """Return paginated device records."""
        return self._repository.list_all(limit=limit, offset=offset)

    def confirm_device(self, device_id: str) -> DeviceRecord:
        """Transition a device from DETECTED to CONFIRMED.

        Args:
            device_id: Public device identifier.

        Returns:
            The updated :class:`DeviceRecord`.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            InvalidStateTransitionError: If the transition is not allowed.
        """
        record = self.get_device(device_id)
        try:
            record.transition_to(RegistrationState.CONFIRMED)
        except ValueError as exc:
            raise InvalidStateTransitionError(
                str(exc),
                details={
                    "device_id": device_id,
                    "current_state": record.registration_state.value,
                    "target_state": RegistrationState.CONFIRMED.value,
                },
            ) from exc

        self._repository.save(record)
        if hasattr(self._repository, "record_event"):
            self._repository.record_event(
                event_type="DEVICE_CONFIRMED",
                device_id=record.device_id,
                capture_id=record.capture_id,
                metadata={"state": record.registration_state.value},
            )
        logger.bind(device_id=device_id, state=record.registration_state.value).info(
            "Device confirmed by user"
        )
        return record

    def finalize_registration(self, device_id: str) -> DeviceRecord:
        """Transition a device from CONFIRMED to REGISTERED.

        Args:
            device_id: Public device identifier.

        Returns:
            The updated :class:`DeviceRecord`.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            InvalidStateTransitionError: If the transition is not allowed.
        """
        record = self.get_device(device_id)
        try:
            record.transition_to(RegistrationState.REGISTERED)
        except ValueError as exc:
            raise InvalidStateTransitionError(
                str(exc),
                details={
                    "device_id": device_id,
                    "current_state": record.registration_state.value,
                    "target_state": RegistrationState.REGISTERED.value,
                },
            ) from exc

        self._repository.save(record)
        if hasattr(self._repository, "record_event"):
            self._repository.record_event(
                event_type="DEVICE_REGISTERED",
                device_id=record.device_id,
                capture_id=record.capture_id,
                metadata={"state": record.registration_state.value},
            )
        logger.bind(device_id=device_id, state=record.registration_state.value).info(
            "Device finalized and registered"
        )
        return record
