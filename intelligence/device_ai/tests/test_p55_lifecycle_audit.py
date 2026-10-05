"""Comprehensive test suite for P5.5 Device Lifecycle & Audit Intelligence.

Tests:
- Formal domain events (DeviceEvent, DeviceEventType).
- Lifecycle operations appending audit events:
  - DETECTED creates DEVICE_DETECTED
  - CONFIRMED creates DEVICE_CONFIRMED
  - REGISTERED creates DEVICE_REGISTERED
  - ENRICHED creates DEVICE_ENRICHED
- Chronological ordering (oldest -> newest).
- Idempotency for repeated confirmation and finalization.
- Invalid state transition rejection (HTTP 400) without state or event mutation.
- 404 on event query for non-existent device.
- Full event parity across InMemoryDeviceRepository, JsonFileDeviceRepository, and PostgresDeviceRepository.
- Transaction rollback safety for atomic state & event persistence.
- REST API endpoints: GET /devices/{device_id}/events and GET /devices/{device_id}/history.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.database.base import Base
from device_ai.database.session import get_session_factory
from device_ai.devices.brand import RuleBasedBrandIntelligence
from device_ai.devices.carbon import EstimatedBurdenCarbonIntelligence
from device_ai.devices.condition import BaselineConditionIntelligence
from device_ai.devices.enrichment_service import DeviceIntelligenceService
from device_ai.devices.material import ProfileBasedMaterialIntelligence
from device_ai.devices.models import (
    ConfidenceState,
    DeviceEvent,
    DeviceEventType,
    DeviceRecord,
    RegistrationState,
)
from device_ai.devices.postgres_repository import PostgresDeviceRepository
from device_ai.devices.repository import (
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from device_ai.devices.service import DeviceRegistrationService
from device_ai.exceptions import (
    DeviceNotFoundError,
    InvalidStateTransitionError,
)
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.predictor import Detection, DetectionResult, Detector
from device_ai.preprocessing.image_loader import LoadedImage


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _FakeDetector(Detector):
    version = "fake-p55-1.0.0"

    def __init__(self, detections: list[Detection] | None = None) -> None:
        self._detections = detections or []

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        best = max(self._detections, key=lambda d: d.confidence) if self._detections else None
        return DetectionResult(
            device_type=best.label.capitalize() if best else "Unknown",
            brand="Unknown",
            confidence=best.confidence if best else 0.0,
            detections=self._detections,
        )


def _make_test_image_bytes(w: int = 100, h: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=(100, 120, 140)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def in_memory_repo() -> InMemoryDeviceRepository:
    return InMemoryDeviceRepository()


@pytest.fixture()
def json_repo(tmp_path: Path) -> JsonFileDeviceRepository:
    return JsonFileDeviceRepository(tmp_path / "json_events_store")


@pytest.fixture()
def postgres_repo(tmp_path: Path) -> PostgresDeviceRepository:
    db_file = tmp_path / "p55_test.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    return PostgresDeviceRepository(session_factory)


# ---------------------------------------------------------------------------
# 1. Repository Event Protocol Parity Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("repo_fixture", ["in_memory_repo", "json_repo", "postgres_repo"])
def test_repository_event_parity(repo_fixture: str, request: pytest.FixtureRequest) -> None:
    """All repository backends support append_event, list_events, get_latest_event, count_events."""
    repo = request.getfixturevalue(repo_fixture)

    t1 = _utc_now() - timedelta(seconds=20)
    t2 = _utc_now() - timedelta(seconds=10)
    t3 = _utc_now()

    e1 = DeviceEvent(event_id="evt-01", device_id="DEV-001", event_type=DeviceEventType.DEVICE_DETECTED, timestamp=t1, capture_id="cap-1")
    e2 = DeviceEvent(event_id="evt-02", device_id="DEV-001", event_type=DeviceEventType.DEVICE_CONFIRMED, timestamp=t2, capture_id="cap-1")
    e3 = DeviceEvent(event_id="evt-03", device_id="DEV-002", event_type=DeviceEventType.DEVICE_DETECTED, timestamp=t3, capture_id="cap-2")

    repo.append_event(e1)
    repo.append_event(e2)
    repo.append_event(e3)

    assert repo.count_events("DEV-001") == 2
    assert repo.count_events("DEV-002") == 1
    assert repo.count_events() == 3

    events_001 = repo.list_events("DEV-001")
    assert len(events_001) == 2
    assert events_001[0].event_id == "evt-01"
    assert events_001[0].event_type == DeviceEventType.DEVICE_DETECTED
    assert events_001[1].event_id == "evt-02"
    assert events_001[1].event_type == DeviceEventType.DEVICE_CONFIRMED

    latest = repo.get_latest_event("DEV-001")
    assert latest is not None
    assert latest.event_id == "evt-02"

    assert repo.list_events("DEV-NONEXISTENT") == []
    assert repo.get_latest_event("DEV-NONEXISTENT") is None


# ---------------------------------------------------------------------------
# 2. Lifecycle Progression & Audit Event Generation Tests
# ---------------------------------------------------------------------------


def _make_loaded_image() -> LoadedImage:
    raw = _make_test_image_bytes()
    pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    return LoadedImage(
        filename="test.png",
        content_type="image/png",
        raw=raw,
        image=pil_img,
    )


def test_lifecycle_event_generation(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Registration, Confirmation, Finalization, and Enrichment emit sequential events."""
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.88, bounding_box=(10, 20, 200, 150))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    reg_service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )
    enr_service = DeviceIntelligenceService(
        repository=in_memory_repo,
        brand_intelligence=RuleBasedBrandIntelligence(),
        condition_intelligence=BaselineConditionIntelligence(),
        material_intelligence=ProfileBasedMaterialIntelligence(),
        carbon_intelligence=EstimatedBurdenCarbonIntelligence(),
        settings=Settings(log_level="WARNING"),
    )

    # 1. DETECTED
    images = [_make_loaded_image()]
    records, _ = reg_service.register_from_images(images, capture_id="cap-sess-p55")
    assert len(records) == 1
    device_id = records[0].device_id

    events = reg_service.get_device_events(device_id)
    assert len(events) == 1
    assert events[0].event_type == DeviceEventType.DEVICE_DETECTED

    # 2. CONFIRMED
    confirmed = reg_service.confirm_device(device_id)
    assert confirmed.registration_state == RegistrationState.CONFIRMED

    events = reg_service.get_device_events(device_id)
    assert len(events) == 2
    assert events[1].event_type == DeviceEventType.DEVICE_CONFIRMED

    # 3. REGISTERED
    registered = reg_service.finalize_registration(device_id)
    assert registered.registration_state == RegistrationState.REGISTERED

    events = reg_service.get_device_events(device_id)
    assert len(events) == 3
    assert events[2].event_type == DeviceEventType.DEVICE_REGISTERED

    # 4. ENRICHED
    enriched_rec, _ = enr_service.enrich_device(device_id, ocr_text="Lenovo ThinkPad", ocr_confidence=0.92)
    assert enriched_rec.carbon_score is not None

    events = reg_service.get_device_events(device_id)
    assert len(events) == 4
    assert events[3].event_type == DeviceEventType.DEVICE_ENRICHED

    # Chronological ordering verification
    for i in range(len(events) - 1):
        assert events[i].timestamp <= events[i + 1].timestamp


# ---------------------------------------------------------------------------
# 3. Idempotency & Invalid Transition Invariant Tests
# ---------------------------------------------------------------------------


def test_idempotent_lifecycle_transitions(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Repeated confirm or finalize calls do not duplicate events or corrupt state."""
    detector = _FakeDetector([
        Detection(label="mouse", confidence=0.82, bounding_box=(5, 5, 50, 50))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    images = [_make_loaded_image()]
    records, _ = service.register_from_images(images, capture_id="cap-idem-1")
    device_id = records[0].device_id

    # Confirm once
    service.confirm_device(device_id)
    assert len(service.get_device_events(device_id)) == 2

    # Duplicate confirm call
    service.confirm_device(device_id)
    events_after_dup_confirm = service.get_device_events(device_id)
    assert len(events_after_dup_confirm) == 2  # No duplicate event

    # Finalize once
    service.finalize_registration(device_id)
    assert len(service.get_device_events(device_id)) == 3

    # Duplicate finalize call
    service.finalize_registration(device_id)
    events_after_dup_finalize = service.get_device_events(device_id)
    assert len(events_after_dup_finalize) == 3  # No duplicate event


def test_invalid_lifecycle_transition_rejection(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Direct DETECTED -> REGISTERED transition raises InvalidStateTransitionError with no event mutation."""
    detector = _FakeDetector([
        Detection(label="printer", confidence=0.79, bounding_box=(10, 10, 80, 80))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    images = [_make_loaded_image()]
    records, _ = service.register_from_images(images, capture_id="cap-inv-1")
    device_id = records[0].device_id

    with pytest.raises(InvalidStateTransitionError):
        service.finalize_registration(device_id)

    # State and event log remain unmodified
    current = service.get_device(device_id)
    assert current.registration_state == RegistrationState.DETECTED
    events = service.get_device_events(device_id)
    assert len(events) == 1
    assert events[0].event_type == DeviceEventType.DEVICE_DETECTED


# ---------------------------------------------------------------------------
# 4. REST API Endpoint Integration Tests
# ---------------------------------------------------------------------------


def test_events_and_history_api_endpoints() -> None:
    """GET /devices/{id}/events and GET /devices/{id}/history return chronological audit history."""
    app = create_app()
    detector = _FakeDetector([
        Detection(label="smartphone", confidence=0.94, bounding_box=(10, 15, 80, 140))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        # 1. Register device
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("phone.png", _make_test_image_bytes(), "image/png"))],
            data={"capture_id": "cap-api-hist-01"},
            headers={"X-Request-ID": "req-api-hist-01"},
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]

        # 2. Confirm and Finalize
        client.post(f"/devices/{device_id}/confirm")
        client.post(f"/devices/{device_id}/finalize")

        # 3. Query events endpoint
        evts_resp = client.get(f"/devices/{device_id}/events", headers={"X-Request-ID": "req-hist-02"})
        assert evts_resp.status_code == 200
        data = evts_resp.json()
        assert data["success"] is True
        assert data["device_id"] == device_id
        assert data["current_state"] == "REGISTERED"
        assert data["total_events"] == 3
        assert data["request_id"] == "req-hist-02"

        types = [e["event_type"] for e in data["events"]]
        assert types == ["DEVICE_DETECTED", "DEVICE_CONFIRMED", "DEVICE_REGISTERED"]

        # 4. Query history endpoint (alias)
        hist_resp = client.get(f"/devices/{device_id}/history")
        assert hist_resp.status_code == 200
        assert hist_resp.json()["total_events"] == 3

        # 5. Query non-existent device
        not_found_resp = client.get("/devices/DEV-UNKNOWN/events")
        assert not_found_resp.status_code == 404

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# 5. PostgreSQL Atomic Transactions & Rollback Tests
# ---------------------------------------------------------------------------


def test_postgres_save_with_event_atomic(postgres_repo: PostgresDeviceRepository) -> None:
    """PostgresDeviceRepository.save_with_event persists device updates and audit events in a single transaction."""
    rec = DeviceRecord(
        device_id="DEV-PG-001",
        capture_id="cap-pg-1",
        class_id=0,
        device_type="laptop",
        confidence=0.91,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 100, 100),
        model_version="1.0.0",
        inference_mode="ensemble",
        registration_state=RegistrationState.DETECTED,
    )
    evt1 = DeviceEvent(
        event_id="evt-pg-1",
        device_id=rec.device_id,
        event_type=DeviceEventType.DEVICE_DETECTED,
        timestamp=_utc_now(),
        capture_id=rec.capture_id,
    )
    postgres_repo.save_with_event(rec, evt1)

    loaded = postgres_repo.get("DEV-PG-001")
    assert loaded is not None
    assert loaded.registration_state == RegistrationState.DETECTED
    assert postgres_repo.count_events("DEV-PG-001") == 1

    # Transition and update atomically
    rec.transition_to(RegistrationState.CONFIRMED)
    evt2 = DeviceEvent(
        event_id="evt-pg-2",
        device_id=rec.device_id,
        event_type=DeviceEventType.DEVICE_CONFIRMED,
        timestamp=_utc_now(),
        capture_id=rec.capture_id,
    )
    postgres_repo.save_with_event(rec, evt2)

    loaded2 = postgres_repo.get("DEV-PG-001")
    assert loaded2 is not None
    assert loaded2.registration_state == RegistrationState.CONFIRMED
    assert postgres_repo.count_events("DEV-PG-001") == 2

    evts = postgres_repo.list_events("DEV-PG-001")
    assert [e.event_type for e in evts] == [DeviceEventType.DEVICE_DETECTED, DeviceEventType.DEVICE_CONFIRMED]


def test_postgres_transaction_rollback(tmp_path: Path) -> None:
    """Session failure during lifecycle operation rolls back state mutation without orphan records."""
    db_file = tmp_path / "p55_rollback_test.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    repo = PostgresDeviceRepository(session_factory)

    rec = DeviceRecord(
        device_id="DEV-ROLLBACK-1",
        capture_id="cap-rb-1",
        class_id=1,
        device_type="smartphone",
        confidence=0.85,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(0, 0, 50, 50),
        model_version="1.0.0",
        inference_mode="single_model",
        registration_state=RegistrationState.DETECTED,
    )
    evt = DeviceEvent(
        event_id="evt-rb-1",
        device_id=rec.device_id,
        event_type=DeviceEventType.DEVICE_DETECTED,
        timestamp=_utc_now(),
    )
    repo.save_with_event(rec, evt)

    # Attempt save_with_event with an invalid event_id collision or forced error
    bad_evt = DeviceEvent(
        event_id="evt-rb-1",  # Primary key conflict with existing event
        device_id=rec.device_id,
        event_type=DeviceEventType.DEVICE_CONFIRMED,
        timestamp=_utc_now(),
    )
    rec.transition_to(RegistrationState.CONFIRMED)

    with pytest.raises(Exception):
        repo.save_with_event(rec, bad_evt)

    # Verification: Device state in DB rolled back and remains DETECTED
    fresh_rec = repo.get("DEV-ROLLBACK-1")
    assert fresh_rec is not None
    assert fresh_rec.registration_state == RegistrationState.DETECTED
    assert repo.count_events("DEV-ROLLBACK-1") == 1


# ---------------------------------------------------------------------------
# 6. Domain Serialization Tests
# ---------------------------------------------------------------------------


def test_domain_device_event_serialization() -> None:
    """DeviceEvent correctly round-trips to and from dict serialization."""
    now = _utc_now()
    evt = DeviceEvent(
        event_id="evt-ser-1",
        device_id="DEV-SER-1",
        event_type=DeviceEventType.DEVICE_ENRICHED,
        timestamp=now,
        capture_id="cap-ser-1",
        metadata={"brand": "Dell", "carbon_score": 12.4},
    )
    data = evt.to_dict()
    assert data["event_id"] == "evt-ser-1"
    assert data["event_type"] == "DEVICE_ENRICHED"
    assert data["metadata"]["brand"] == "Dell"

    restored = DeviceEvent.from_dict(data)
    assert restored.event_id == evt.event_id
    assert restored.device_id == evt.device_id
    assert restored.event_type == DeviceEventType.DEVICE_ENRICHED
    assert restored.timestamp == now
    assert restored.metadata == evt.metadata
