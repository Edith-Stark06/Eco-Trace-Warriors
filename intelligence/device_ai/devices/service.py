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
    DeviceEvent,
    DeviceEventType,
    DeviceRecord,
    RegistrationState,
)
from .passport import DevicePassport, build_device_passport
from .passport_verification import PassportVerificationResult, verify_passport
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

            detect_event = DeviceEvent(
                event_id=f"evt-{uuid.uuid4().hex[:12]}",
                device_id=record.device_id,
                event_type=DeviceEventType.DEVICE_DETECTED,
                timestamp=_utc_now(),
                capture_id=record.capture_id,
                metadata={"confidence": record.confidence, "device_type": record.device_type},
            )

            if hasattr(self._repository, "save_with_event"):
                self._repository.save_with_event(record, detect_event)
            else:
                self._repository.save(record)
                self._repository.append_event(detect_event)

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

        Idempotent: if already CONFIRMED, returns the current record without
        emitting duplicate events.

        Args:
            device_id: Public device identifier.

        Returns:
            The updated :class:`DeviceRecord`.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            InvalidStateTransitionError: If the transition is not allowed.
        """
        record = self.get_device(device_id)
        if record.registration_state == RegistrationState.CONFIRMED:
            logger.bind(device_id=device_id).info("Device already confirmed; returning existing state")
            return record

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

        event = DeviceEvent(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            device_id=record.device_id,
            event_type=DeviceEventType.DEVICE_CONFIRMED,
            timestamp=_utc_now(),
            capture_id=record.capture_id,
            metadata={"state": record.registration_state.value},
        )

        if hasattr(self._repository, "save_with_event"):
            self._repository.save_with_event(record, event)
        else:
            self._repository.save(record)
            self._repository.append_event(event)

        logger.bind(device_id=device_id, state=record.registration_state.value).info(
            "Device confirmed by user"
        )
        return record

    def finalize_registration(self, device_id: str) -> DeviceRecord:
        """Transition a device from CONFIRMED to REGISTERED.

        Idempotent: if already REGISTERED, returns the current record without
        emitting duplicate events.

        Args:
            device_id: Public device identifier.

        Returns:
            The updated :class:`DeviceRecord`.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            InvalidStateTransitionError: If the transition is not allowed.
        """
        record = self.get_device(device_id)
        if record.registration_state == RegistrationState.REGISTERED:
            logger.bind(device_id=device_id).info("Device already registered; returning existing state")
            return record

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

        event = DeviceEvent(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            device_id=record.device_id,
            event_type=DeviceEventType.DEVICE_REGISTERED,
            timestamp=_utc_now(),
            capture_id=record.capture_id,
            metadata={"state": record.registration_state.value},
        )

        if hasattr(self._repository, "save_with_event"):
            self._repository.save_with_event(record, event)
        else:
            self._repository.save(record)
            self._repository.append_event(event)

        logger.bind(device_id=device_id, state=record.registration_state.value).info(
            "Device finalized and registered"
        )
        return record

    def get_device_events(self, device_id: str) -> list[DeviceEvent]:
        """Retrieve all chronological audit events for a device.

        Args:
            device_id: Public device identifier.

        Returns:
            List of :class:`DeviceEvent` objects ordered oldest -> newest.

        Raises:
            DeviceNotFoundError: If the device does not exist.
        """
        self.get_device(device_id)  # Validate existence
        return self._repository.list_events(device_id)

    def get_device_passport(self, device_id: str) -> DevicePassport:
        """Construct and return the aggregated DevicePassport read model.

        Strictly read-only: does not mutate DeviceRecord, write to storage, or emit audit events.

        Args:
            device_id: Public device identifier.

        Returns:
            The aggregated :class:`DevicePassport`.

        Raises:
            DeviceNotFoundError: If the device does not exist.
        """
        record = self.get_device(device_id)
        events = self._repository.list_events(device_id)
        return build_device_passport(record, events)

    def verify_device_passport(self, device_id: str) -> PassportVerificationResult:
        """Verify integrity, lifecycle consistency, and provenance of a device passport.

        Strictly read-only: does not mutate DeviceRecord, write to storage, or emit audit events.

        Args:
            device_id: Public device identifier.

        Returns:
            A :class:`PassportVerificationResult`.

        Raises:
            DeviceNotFoundError: If the device does not exist.
        """
        record = self.get_device(device_id)
        events = self._repository.list_events(device_id)
        passport = build_device_passport(record, events)
        return verify_passport(record=record, events=events, passport=passport)
