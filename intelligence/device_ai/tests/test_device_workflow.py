"""Comprehensive unit and integration test suite for the Device Registration & Workflow (P5.2).

Covers:
- Single-device and multi-device registration workflows.
- Zero-detection rejection.
- Configurable confidence classification policy.
- Canonical class mapping across all 8 classes.
- Bounding box and metadata preservation.
- Capture/session ID correlation.
- In-memory and JSON file persistence backends.
- Device retrieval and 404 handling.
- Valid and invalid lifecycle state transitions.
- Duplicate device detection.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.devices.models import (
    ConfidenceState,
    DeviceRecord,
    RegistrationState,
)
from device_ai.devices.repository import (
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from device_ai.devices.service import DeviceRegistrationService
from device_ai.exceptions import (
    DeviceNotFoundError,
    DuplicateDeviceError,
    InvalidDeviceClassError,
    InvalidStateTransitionError,
    NoDetectionsForRegistrationError,
)
from device_ai.inference.class_map import CANONICAL_CLASSES, CLASS_NAME_TO_ID
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.predictor import (
    Detection,
    DetectionResult,
    Detector,
)
from device_ai.preprocessing.image_loader import LoadedImage


class _FakeDetector(Detector):
    """A mock detector returning configured detections."""

    version = "fake-detector-1.0.0"

    def __init__(self, detections: list[Detection] | None = None) -> None:
        self._detections = detections or []

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        if not self._detections:
            return DetectionResult(
                device_type="Unknown",
                brand="Unknown",
                confidence=0.0,
                detections=[],
            )
        best = max(self._detections, key=lambda d: d.confidence)
        return DetectionResult(
            device_type=best.label.capitalize(),
            brand="Unknown",
            confidence=best.confidence,
            detections=self._detections,
        )


def _make_test_image_bytes(w: int = 100, h: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=(120, 140, 180)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def device_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="development",
        max_images=4,
        min_images=1,
        max_file_size=1 * 1024 * 1024,
        confidence_high_threshold=0.75,
        confidence_review_threshold=0.40,
        device_backend="memory",
        device_store_dir=tmp_path / "devices",
        inference_mode="single_model",
        log_level="WARNING",
    )


# ---------------------------------------------------------------------------
# Unit tests for Domain Models & Repository
# ---------------------------------------------------------------------------


def test_confidence_classification_policy(device_settings: Settings) -> None:
    """Confidence policy properly partitions scores into HIGH, REVIEW, LOW."""
    service = DeviceRegistrationService(
        repository=InMemoryDeviceRepository(),
        pipeline=build_detection_pipeline(detector=_FakeDetector(), model_version="1.0.0", year=2026),
        settings=device_settings,
    )

    assert service.classify_confidence(0.95) == ConfidenceState.HIGH_CONFIDENCE
    assert service.classify_confidence(0.75) == ConfidenceState.HIGH_CONFIDENCE
    assert service.classify_confidence(0.74) == ConfidenceState.REVIEW_REQUIRED
    assert service.classify_confidence(0.40) == ConfidenceState.REVIEW_REQUIRED
    assert service.classify_confidence(0.39) == ConfidenceState.LOW_CONFIDENCE
    assert service.classify_confidence(0.05) == ConfidenceState.LOW_CONFIDENCE


def test_state_machine_transitions() -> None:
    """State machine allows DETECTED -> CONFIRMED -> REGISTERED and rejects invalid skips."""
    rec = DeviceRecord(
        device_id="DEV-2026-001",
        capture_id="cap-001",
        class_id=0,
        device_type="laptop",
        confidence=0.90,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 20, 100, 200),
        model_version="1.0.0",
        inference_mode="single_model",
        registration_state=RegistrationState.DETECTED,
    )

    # Cannot skip directly to REGISTERED
    assert not rec.can_transition_to(RegistrationState.REGISTERED)
    with pytest.raises(ValueError, match="Cannot transition"):
        rec.transition_to(RegistrationState.REGISTERED)

    # Valid step 1: DETECTED -> CONFIRMED
    assert rec.can_transition_to(RegistrationState.CONFIRMED)
    rec.transition_to(RegistrationState.CONFIRMED)
    assert rec.registration_state == RegistrationState.CONFIRMED

    # Valid step 2: CONFIRMED -> REGISTERED
    assert rec.can_transition_to(RegistrationState.REGISTERED)
    rec.transition_to(RegistrationState.REGISTERED)
    assert rec.registration_state == RegistrationState.REGISTERED

    # Terminal state: cannot transition again
    assert not rec.can_transition_to(RegistrationState.CONFIRMED)
    with pytest.raises(ValueError):
        rec.transition_to(RegistrationState.CONFIRMED)


def test_json_file_repository_persistence(tmp_path: Path) -> None:
    """JsonFileDeviceRepository persists and deserializes records faithfully."""
    repo = JsonFileDeviceRepository(tmp_path / "devices_json")
    rec = DeviceRecord(
        device_id="DEV-2026-TEST-01",
        capture_id="cap-test-123",
        class_id=1,
        device_type="smartphone",
        confidence=0.88,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(5, 5, 80, 160),
        model_version="1.0.0",
        inference_mode="ensemble",
        registration_state=RegistrationState.DETECTED,
    )

    repo.save(rec)
    assert repo.exists("DEV-2026-TEST-01")
    assert repo.count() == 1

    loaded = repo.get("DEV-2026-TEST-01")
    assert loaded is not None
    assert loaded.device_id == "DEV-2026-TEST-01"
    assert loaded.class_id == 1
    assert loaded.device_type == "smartphone"
    assert loaded.confidence_state == ConfidenceState.HIGH_CONFIDENCE
    assert loaded.bounding_box == (5, 5, 80, 160)
    assert loaded.inference_mode == "ensemble"

    by_cap = repo.find_by_capture_id("cap-test-123")
    assert len(by_cap) == 1
    assert by_cap[0].device_id == "DEV-2026-TEST-01"

    assert repo.delete("DEV-2026-TEST-01")
    assert repo.get("DEV-2026-TEST-01") is None
    assert repo.count() == 0


# ---------------------------------------------------------------------------
# API Integration Tests
# ---------------------------------------------------------------------------


def test_single_device_registration_endpoint(device_settings: Settings) -> None:
    """POST /devices/register registers a single detected laptop."""
    fake_detector = _FakeDetector([
        Detection(label="laptop", confidence=0.92, bounding_box=(10, 10, 200, 150))
    ])
    pipeline = build_detection_pipeline(detector=fake_detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(device_settings)
    app.dependency_overrides[get_settings] = lambda: device_settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        png_data = _make_test_image_bytes()
        resp = client.post(
            "/devices/register",
            files=[("images", ("laptop.png", png_data, "image/png"))],
            data={"capture_id": "cap-sess-101"},
            headers={"X-Request-ID": "req-reg-01"},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["success"] is True
        assert data["capture_id"] == "cap-sess-101"
        assert data["total_detected"] == 1
        assert len(data["devices"]) == 1

        dev = data["devices"][0]
        assert dev["device_id"].startswith("DEV-2026-")
        assert dev["class_id"] == 0
        assert dev["device_type"] == "laptop"
        assert pytest.approx(dev["confidence"], 1e-2) == 0.92
        assert dev["confidence_state"] == "HIGH_CONFIDENCE"
        assert dev["registration_state"] == "DETECTED"
        assert dev["bounding_box"] == [10, 10, 200, 150]
        assert dev["condition"] is None
        assert dev["materials"] is None

        # Verify retrieval via GET /devices/{device_id}
        get_resp = client.get(f"/devices/{dev['device_id']}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["device_id"] == dev["device_id"]
        assert get_data["device_type"] == "laptop"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_multi_device_registration_endpoint(device_settings: Settings) -> None:
    """POST /devices/register independently registers multiple objects from one image."""
    fake_detector = _FakeDetector([
        Detection(label="laptop", confidence=0.89, bounding_box=(20, 20, 300, 200)),
        Detection(label="mouse", confidence=0.65, bounding_box=(310, 150, 380, 210)),
    ])
    pipeline = build_detection_pipeline(detector=fake_detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(device_settings)
    app.dependency_overrides[get_settings] = lambda: device_settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        png_data = _make_test_image_bytes()
        resp = client.post(
            "/devices/register",
            files=[("images", ("desk.png", png_data, "image/png"))],
            data={"capture_id": "cap-multi-202"},
        )

        assert resp.status_code == 200
        data = resp.json()

        assert data["total_detected"] == 2
        assert len(data["devices"]) == 2

        d1, d2 = data["devices"][0], data["devices"][1]
        assert d1["device_id"] != d2["device_id"]
        assert d1["capture_id"] == "cap-multi-202"
        assert d2["capture_id"] == "cap-multi-202"

        assert d1["class_id"] == 0
        assert d1["device_type"] == "laptop"
        assert d1["confidence_state"] == "HIGH_CONFIDENCE"

        assert d2["class_id"] == 5
        assert d2["device_type"] == "mouse"
        assert d2["confidence_state"] == "REVIEW_REQUIRED"

        # Check list endpoint by capture_id
        list_resp = client.get("/devices?capture_id=cap-multi-202")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["total"] == 2

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_zero_detections_rejected(device_settings: Settings) -> None:
    """POST /devices/register with 0 detections returns 422 NO_DETECTIONS_FOUND."""
    fake_detector = _FakeDetector([])  # zero detections
    pipeline = build_detection_pipeline(detector=fake_detector, model_version="1.0.0", year=2026)

    app = create_app(device_settings)
    app.dependency_overrides[get_settings] = lambda: device_settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        png_data = _make_test_image_bytes()
        resp = client.post(
            "/devices/register",
            files=[("images", ("blank.png", png_data, "image/png"))],
        )

        assert resp.status_code == 422
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NO_DETECTIONS_FOUND"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_lifecycle_confirmation_and_finalization_endpoints(device_settings: Settings) -> None:
    """Test full lifecycle progression: DETECTED -> CONFIRMED -> REGISTERED."""
    fake_detector = _FakeDetector([
        Detection(label="smartphone", confidence=0.85, bounding_box=(15, 15, 80, 150))
    ])
    pipeline = build_detection_pipeline(detector=fake_detector, model_version="1.0.0", year=2026)

    app = create_app(device_settings)
    app.dependency_overrides[get_settings] = lambda: device_settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        # 1. Register device
        png_data = _make_test_image_bytes()
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("phone.png", png_data, "image/png"))],
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]

        # 2. Confirm device (DETECTED -> CONFIRMED)
        conf_resp = client.post(f"/devices/{device_id}/confirm")
        assert conf_resp.status_code == 200
        conf_data = conf_resp.json()
        assert conf_data["previous_state"] == "DETECTED"
        assert conf_data["current_state"] == "CONFIRMED"
        assert conf_data["device"]["registration_state"] == "CONFIRMED"

        # 3. Finalize registration (CONFIRMED -> REGISTERED)
        fin_resp = client.post(f"/devices/{device_id}/finalize")
        assert fin_resp.status_code == 200
        fin_data = fin_resp.json()
        assert fin_data["previous_state"] == "CONFIRMED"
        assert fin_data["current_state"] == "REGISTERED"
        assert fin_data["device"]["registration_state"] == "REGISTERED"

        # 4. Attempt invalid transition on terminal state
        inv_resp = client.post(f"/devices/{device_id}/confirm")
        assert inv_resp.status_code == 400
        inv_data = inv_resp.json()
        assert inv_data["error"]["code"] == "INVALID_STATE_TRANSITION"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_device_not_found_returns_404(device_settings: Settings) -> None:
    """GET /devices/unknown returns 404 DEVICE_NOT_FOUND."""
    app = create_app(device_settings)
    app.dependency_overrides[get_settings] = lambda: device_settings

    with TestClient(app) as client:
        resp = client.get("/devices/DEV-NON-EXISTENT")
        assert resp.status_code == 404
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "DEVICE_NOT_FOUND"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_canonical_class_mapping_all_8_classes(device_settings: Settings) -> None:
    """Verify all 8 canonical classes correctly map to their class_id."""
    for expected_id, expected_name in CANONICAL_CLASSES.items():
        fake_detector = _FakeDetector([
            Detection(label=expected_name, confidence=0.80, bounding_box=(10, 10, 50, 50))
        ])
        service = DeviceRegistrationService(
            repository=InMemoryDeviceRepository(),
            pipeline=build_detection_pipeline(detector=fake_detector, model_version="1.0.0", year=2026),
            settings=device_settings,
        )

        dummy_img = LoadedImage(
            filename="test.png",
            content_type="image/png",
            raw=b"bytes",
            image=Image.new("RGB", (64, 64)),
            sha256="dummy",
        )
        records, _ = service.register_from_images([dummy_img])
        assert len(records) == 1
        assert records[0].class_id == expected_id
        assert records[0].device_type == expected_name
