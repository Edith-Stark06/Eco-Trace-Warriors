"""Comprehensive test suite for P5.6 EcoTrace Device Passport & Traceability Read Layer.

Tests:
- Unified DevicePassport read model aggregation (DeviceRecord + DeviceEnrichment + DeviceEvent history).
- Registered and fully enriched device passport inspection.
- Un-enriched device passport with explicit UNAVAILABLE/PENDING facets without synthetic fabrication.
- Domain facet propagation:
  - Identity & Detection
  - Brand intelligence (brand, status, source, OCR raw text)
  - Condition intelligence (condition, status, source, notes)
  - Material intelligence (materials breakdown, mass, recoverability, basis)
  - Carbon intelligence (avoided CO2e, contributing factors, methodology)
  - Lifecycle state (current_state, is_confirmed, is_registered, is_enriched)
  - Audit trail (chronological events, total_events, event metadata)
- Zero mutation guarantee (passport retrieval does NOT mutate DeviceRecord or write storage).
- Zero event emission guarantee (passport GET emits zero new audit events).
- HTTP 404 on missing device.
- Full repository backend parity across:
  - InMemoryDeviceRepository
  - JsonFileDeviceRepository
  - PostgresDeviceRepository
- REST API endpoint integration: GET /devices/{device_id}/passport.
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
from device_ai.configs.settings import Settings
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
from device_ai.devices.passport import DevicePassport, build_device_passport
from device_ai.devices.postgres_repository import PostgresDeviceRepository
from device_ai.devices.repository import (
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from device_ai.devices.service import DeviceRegistrationService
from device_ai.exceptions import DeviceNotFoundError
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.predictor import Detection, DetectionResult, Detector
from device_ai.preprocessing.image_loader import LoadedImage


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _FakeDetector(Detector):
    version = "fake-p56-1.0.0"

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


def _make_loaded_image() -> LoadedImage:
    raw = _make_test_image_bytes()
    pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    return LoadedImage(
        filename="test.png",
        content_type="image/png",
        raw=raw,
        image=pil_img,
    )


@pytest.fixture()
def in_memory_repo() -> InMemoryDeviceRepository:
    return InMemoryDeviceRepository()


@pytest.fixture()
def json_repo(tmp_path: Path) -> JsonFileDeviceRepository:
    return JsonFileDeviceRepository(tmp_path / "json_passport_store")


@pytest.fixture()
def postgres_repo(tmp_path: Path) -> PostgresDeviceRepository:
    db_file = tmp_path / "p56_test.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    return PostgresDeviceRepository(session_factory)


# ---------------------------------------------------------------------------
# 1. Domain Passport Aggregation & Read Model Tests
# ---------------------------------------------------------------------------


def test_build_device_passport_fully_enriched(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Build passport for a confirmed, registered, and enriched device."""
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.92, bounding_box=(10, 20, 300, 200))
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

    # 1. Register, confirm, finalize
    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-pass-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)

    # 2. Enrich
    enr_service.enrich_device(device_id, ocr_text="Dell XPS 15", ocr_confidence=0.95)

    # 3. Retrieve passport via service
    passport = reg_service.get_device_passport(device_id)

    assert passport.device_id == device_id
    assert passport.identity.device_type == "laptop"
    assert passport.identity.class_id == 0
    assert passport.identity.capture_id == "cap-pass-01"

    assert passport.detection.confidence == 0.92
    assert passport.detection.confidence_state == "HIGH_CONFIDENCE"
    assert passport.detection.bounding_box == [10, 20, 300, 200]

    # Brand facet
    assert passport.brand.brand == "Dell"
    assert passport.brand.status == "CONFIRMED"
    assert passport.brand.source == "ocr"
    assert passport.brand.raw_text == "Dell"

    # Condition facet
    assert passport.condition.condition == "UNKNOWN"
    assert passport.condition.status == "UNAVAILABLE"

    # Material facet
    assert len(passport.material.materials) > 0
    assert passport.material.total_mass_g == 1800.0

    # Carbon facet
    assert passport.carbon.carbon_score is not None
    assert passport.carbon.carbon_score > 0.0
    assert len(passport.carbon.contributing_factors) > 0

    # Lifecycle facet
    assert passport.lifecycle.current_state == "REGISTERED"
    assert passport.lifecycle.is_confirmed is True
    assert passport.lifecycle.is_registered is True
    assert passport.lifecycle.is_enriched is True

    # Audit facet
    assert passport.audit.total_events == 4
    event_types = [e["event_type"] for e in passport.audit.events]
    assert event_types == [
        "DEVICE_DETECTED",
        "DEVICE_CONFIRMED",
        "DEVICE_REGISTERED",
        "DEVICE_ENRICHED",
    ]


def test_build_device_passport_unenriched(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Build passport for a detected device that has not yet been enriched."""
    detector = _FakeDetector([
        Detection(label="smartphone", confidence=0.75, bounding_box=(5, 5, 50, 100))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    reg_service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-unenr-01")
    device_id = records[0].device_id

    passport = reg_service.get_device_passport(device_id)

    # Verification: Unenriched device has explicit UNAVAILABLE/PENDING values rather than fabricated values
    assert passport.device_id == device_id
    assert passport.brand.brand is None
    assert passport.brand.status == "UNAVAILABLE"
    assert passport.brand.source == "NONE"

    assert passport.condition.condition is None
    assert passport.condition.status == "UNAVAILABLE"

    assert passport.material.materials == []
    assert passport.material.total_mass_g is None
    assert passport.material.source == "NONE"

    assert passport.carbon.carbon_score is None
    assert passport.carbon.contributing_factors == {}
    assert passport.carbon.source == "NONE"

    assert passport.lifecycle.current_state == "DETECTED"
    assert passport.lifecycle.is_confirmed is False
    assert passport.lifecycle.is_registered is False
    assert passport.lifecycle.is_enriched is False

    assert passport.audit.total_events == 1
    assert passport.audit.events[0]["event_type"] == "DEVICE_DETECTED"


# ---------------------------------------------------------------------------
# 2. Immutability & Read-Only Invariants
# ---------------------------------------------------------------------------


def test_passport_generation_does_not_mutate_record_or_emit_events(
    in_memory_repo: InMemoryDeviceRepository,
) -> None:
    """Passport retrieval is strictly read-only and does not mutate record or add events."""
    detector = _FakeDetector([
        Detection(label="mouse", confidence=0.85, bounding_box=(0, 0, 40, 40))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-read-only-1")
    device_id = records[0].device_id

    record_before = in_memory_repo.get(device_id)
    assert record_before is not None
    dict_before = record_before.to_dict()
    events_before_count = in_memory_repo.count_events(device_id)

    # Call get_device_passport multiple times
    for _ in range(5):
        passport = service.get_device_passport(device_id)
        assert passport.device_id == device_id

    record_after = in_memory_repo.get(device_id)
    assert record_after is not None
    assert record_after.to_dict() == dict_before
    assert in_memory_repo.count_events(device_id) == events_before_count


# ---------------------------------------------------------------------------
# 3. Multi-Backend Repository Compatibility Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("repo_fixture", ["in_memory_repo", "json_repo", "postgres_repo"])
def test_passport_multi_backend_parity(repo_fixture: str, request: pytest.FixtureRequest) -> None:
    """Passport aggregation works identically across Memory, JSON, and Postgres repositories."""
    repo = request.getfixturevalue(repo_fixture)
    detector = _FakeDetector([
        Detection(label="printer", confidence=0.89, bounding_box=(10, 10, 120, 120))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    reg_service = DeviceRegistrationService(
        repository=repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-multi-01")
    device_id = records[0].device_id

    passport = reg_service.get_device_passport(device_id)
    assert passport.device_id == device_id
    assert passport.identity.device_type == "printer"
    assert passport.identity.class_id == 4
    assert passport.audit.total_events == 1


def test_passport_with_manual_condition_override(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Passport correctly reflects manual condition inspection override."""
    detector = _FakeDetector([
        Detection(label="headphones", confidence=0.88, bounding_box=(0, 0, 50, 50))
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

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-cond-1")
    device_id = records[0].device_id

    # Enrich with manual condition override
    enr_service.enrich_device(device_id, manual_condition="EXCELLENT")

    passport = reg_service.get_device_passport(device_id)
    assert passport.condition.condition == "EXCELLENT"
    assert passport.condition.status == "AVAILABLE"
    assert passport.condition.source == "manual_inspection"
    assert "manual inspection" in (passport.condition.notes or "")


def test_passport_serialization_dict(in_memory_repo: InMemoryDeviceRepository) -> None:
    """DevicePassport.to_dict() produces a well-formed JSON-serializable dictionary."""
    detector = _FakeDetector([
        Detection(label="camera", confidence=0.83, bounding_box=(5, 5, 80, 80))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    reg_service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ser-1")
    device_id = records[0].device_id

    passport = reg_service.get_device_passport(device_id)
    data = passport.to_dict()

    assert data["device_id"] == device_id
    assert "identity" in data
    assert "detection" in data
    assert "brand" in data
    assert "condition" in data
    assert "material" in data
    assert "carbon" in data
    assert "lifecycle" in data
    assert "audit" in data
    assert "generated_at" in data



# ---------------------------------------------------------------------------
# 4. REST API Endpoint Integration Tests
# ---------------------------------------------------------------------------


def test_passport_api_endpoint() -> None:
    """GET /devices/{id}/passport returns complete aggregated passport payload."""
    app = create_app()
    detector = _FakeDetector([
        Detection(label="tablet", confidence=0.91, bounding_box=(15, 25, 180, 240))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        # 1. Register device
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("tablet.png", _make_test_image_bytes(), "image/png"))],
            data={"capture_id": "cap-api-pass-01"},
            headers={"X-Request-ID": "req-api-pass-01"},
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]

        # 2. Confirm and Enrich
        client.post(f"/devices/{device_id}/confirm")
        client.post(
            f"/devices/{device_id}/enrich",
            json={"ocr_text": "Apple iPad Pro", "ocr_confidence": 0.96},
        )

        # 3. Query Passport endpoint
        pass_resp = client.get(
            f"/devices/{device_id}/passport",
            headers={"X-Request-ID": "req-pass-view-01"},
        )
        assert pass_resp.status_code == 200
        data = pass_resp.json()

        assert data["success"] is True
        assert data["request_id"] == "req-pass-view-01"

        passport_data = data["passport"]
        assert passport_data["device_id"] == device_id
        assert passport_data["identity"]["device_type"] == "tablet"
        assert passport_data["identity"]["class_id"] == 2
        assert passport_data["detection"]["confidence"] == 0.91
        assert passport_data["brand"]["brand"] == "Apple"
        assert passport_data["brand"]["status"] == "CONFIRMED"
        assert passport_data["condition"]["condition"] == "UNKNOWN"
        assert passport_data["carbon"]["carbon_score"] is not None
        assert passport_data["lifecycle"]["is_confirmed"] is True
        assert passport_data["lifecycle"]["is_enriched"] is True
        assert passport_data["audit"]["total_events"] == 3

        # 4. Verify 404 for unknown device
        not_found_resp = client.get("/devices/DEV-NONEXISTENT/passport")
        assert not_found_resp.status_code == 404

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()
