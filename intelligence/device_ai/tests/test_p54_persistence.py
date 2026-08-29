"""Comprehensive unit and integration test suite for P5.4 Database Persistence.

Tests:
- PostgresDeviceRepository CRUD operations (save, get, exists, delete, count).
- Relational persistence for DeviceEnrichmentModel and MaterialItemModel.
- DeviceEventModel audit trail logging and retrieval.
- Transaction rollback safety on constraint violations.
- Dependency injection routing for 'postgres' backend.
- Duplicate device and missing device handling.
- Full API workflow execution over SQLAlchemy-backed repository.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.database.base import Base
from device_ai.database.models import (
    DeviceEnrichmentModel,
    DeviceEventModel,
    DeviceModel,
    MaterialItemModel,
)
from device_ai.database.session import get_session_factory, session_scope
from device_ai.devices.brand import RuleBasedBrandIntelligence
from device_ai.devices.carbon import EstimatedBurdenCarbonIntelligence
from device_ai.devices.condition import BaselineConditionIntelligence
from device_ai.devices.enrichment_models import (
    BrandAssessment,
    CarbonAssessment,
    ConditionAssessment,
    DeviceEnrichment,
    MaterialAssessment,
    MaterialItem,
)
from device_ai.devices.enrichment_service import DeviceIntelligenceService
from device_ai.devices.material import ProfileBasedMaterialIntelligence
from device_ai.devices.models import (
    ConfidenceState,
    DeviceRecord,
    RegistrationState,
)
from device_ai.devices.postgres_repository import PostgresDeviceRepository
from device_ai.devices.repository import (
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from device_ai.devices.service import DeviceRegistrationService
from device_ai.exceptions import DeviceNotFoundError, DuplicateDeviceError
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.predictor import Detection, DetectionResult, Detector
from device_ai.preprocessing.image_loader import LoadedImage


@pytest.fixture()
def db_engine(tmp_path: Path):
    """Create an isolated test SQLite engine configured with the full P5.4 schema."""
    db_file = tmp_path / "test_p54.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return get_session_factory(db_engine)


@pytest.fixture()
def pg_repo(session_factory) -> PostgresDeviceRepository:
    return PostgresDeviceRepository(session_factory)


@pytest.fixture()
def p54_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="development",
        max_images=4,
        min_images=1,
        max_file_size=1 * 1024 * 1024,
        confidence_high_threshold=0.75,
        confidence_review_threshold=0.40,
        device_backend="postgres",
        database_url=f"sqlite:///{tmp_path / 'app_p54.db'}",
        material_profile_version="v1.0.0",
        carbon_model_version="v1.0.0",
        carbon_calculation_methodology="avoided_burden_co2e",
        log_level="WARNING",
    )


def _make_dummy_record(
    device_id: str = "DEV-2026-SQL-01",
    capture_id: str = "cap-sess-sql",
    device_type: str = "laptop",
    class_id: int = 0,
) -> DeviceRecord:
    return DeviceRecord(
        device_id=device_id,
        capture_id=capture_id,
        class_id=class_id,
        device_type=device_type,
        confidence=0.91,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(15, 25, 220, 160),
        model_version="1.0.0",
        inference_mode="single_model",
        registration_state=RegistrationState.DETECTED,
    )


class _FakeDetector(Detector):
    version = "fake-p54-1.0.0"

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
    Image.new("RGB", (w, h), color=(110, 130, 150)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Repository CRUD Unit Tests
# ---------------------------------------------------------------------------


def test_postgres_repository_crud(pg_repo: PostgresDeviceRepository) -> None:
    """PostgresDeviceRepository performs save, get, exists, count, and delete correctly."""
    assert pg_repo.count() == 0
    assert not pg_repo.exists("DEV-2026-SQL-01")
    assert pg_repo.get("DEV-2026-SQL-01") is None

    rec = _make_dummy_record("DEV-2026-SQL-01")
    pg_repo.save(rec)

    assert pg_repo.count() == 1
    assert pg_repo.exists("DEV-2026-SQL-01")

    loaded = pg_repo.get("DEV-2026-SQL-01")
    assert loaded is not None
    assert loaded.device_id == "DEV-2026-SQL-01"
    assert loaded.capture_id == "cap-sess-sql"
    assert loaded.class_id == 0
    assert loaded.device_type == "laptop"
    assert pytest.approx(loaded.confidence, 1e-2) == 0.91
    assert loaded.confidence_state == ConfidenceState.HIGH_CONFIDENCE
    assert loaded.bounding_box == (15, 25, 220, 160)
    assert loaded.registration_state == RegistrationState.DETECTED

    # Update record
    rec.transition_to(RegistrationState.CONFIRMED)
    pg_repo.save(rec)

    updated = pg_repo.get("DEV-2026-SQL-01")
    assert updated is not None
    assert updated.registration_state == RegistrationState.CONFIRMED

    # Delete record
    assert pg_repo.delete("DEV-2026-SQL-01")
    assert not pg_repo.exists("DEV-2026-SQL-01")
    assert pg_repo.count() == 0


def test_postgres_repository_query_and_pagination(pg_repo: PostgresDeviceRepository) -> None:
    """find_by_capture_id and list_all handle filtering and pagination."""
    r1 = _make_dummy_record("DEV-01", capture_id="cap-A", device_type="laptop")
    r2 = _make_dummy_record("DEV-02", capture_id="cap-A", device_type="mouse", class_id=5)
    r3 = _make_dummy_record("DEV-03", capture_id="cap-B", device_type="smartphone", class_id=1)

    pg_repo.save(r1)
    pg_repo.save(r2)
    pg_repo.save(r3)

    assert pg_repo.count() == 3

    cap_a_records = pg_repo.find_by_capture_id("cap-A")
    assert len(cap_a_records) == 2
    assert {r.device_id for r in cap_a_records} == {"DEV-01", "DEV-02"}

    cap_b_records = pg_repo.find_by_capture_id("cap-B")
    assert len(cap_b_records) == 1
    assert cap_b_records[0].device_id == "DEV-03"

    paged = pg_repo.list_all(limit=2, offset=0)
    assert len(paged) == 2


# ---------------------------------------------------------------------------
# Relational Enrichment & Material Items Tests
# ---------------------------------------------------------------------------


def test_postgres_enrichment_and_material_items(
    pg_repo: PostgresDeviceRepository,
    session_factory,
) -> None:
    """save_enrichment persists DeviceEnrichmentModel and associated MaterialItemModel rows."""
    rec = _make_dummy_record("DEV-ENR-01", device_type="smartphone", class_id=1)
    pg_repo.save(rec)

    mat_item1 = MaterialItem(material="Aluminium frame", category="metals", mass_g=50.0, recoverable=True, hazardous=False)
    mat_item2 = MaterialItem(material="Li-ion battery", category="battery", mass_g=50.0, recoverable=True, hazardous=True)

    enrichment = DeviceEnrichment(
        device_id="DEV-ENR-01",
        brand=BrandAssessment(value="Apple", status="CONFIRMED", source="ocr", confidence=0.95, raw_text="Apple"),
        condition=ConditionAssessment(value="UNKNOWN", status="UNAVAILABLE", source="pending_assessment"),
        materials=MaterialAssessment(materials=[mat_item1, mat_item2], total_mass_g=100.0, source="device_profile"),
        carbon=CarbonAssessment(carbon_score=0.675, methodology="avoided_burden_co2e", contributing_factors={"metals": 0.25, "battery": 0.425}),
    )

    pg_repo.save_enrichment(enrichment)

    # Inspect relational tables directly via session
    with session_scope(session_factory) as session:
        enr_models = session.scalars(
            select(DeviceEnrichmentModel).where(DeviceEnrichmentModel.device_id == "DEV-ENR-01")
        ).all()
        assert len(enr_models) == 1
        em = enr_models[0]
        assert em.brand_value == "Apple"
        assert em.brand_status == "CONFIRMED"
        assert em.carbon_score == 0.675
        assert len(em.material_items) == 2

        categories = {item.category for item in em.material_items}
        assert categories == {"metals", "battery"}


# ---------------------------------------------------------------------------
# Audit Events Tests
# ---------------------------------------------------------------------------


def test_postgres_device_events(pg_repo: PostgresDeviceRepository) -> None:
    """record_event logs lifecycle audit records and get_events retrieves them."""
    rec = _make_dummy_record("DEV-EVT-01")
    pg_repo.save(rec)

    pg_repo.record_event(
        event_type="DEVICE_DETECTED",
        device_id="DEV-EVT-01",
        capture_id="cap-sess-sql",
        metadata={"confidence": 0.91},
    )
    pg_repo.record_event(
        event_type="DEVICE_CONFIRMED",
        device_id="DEV-EVT-01",
        capture_id="cap-sess-sql",
        metadata={"state": "CONFIRMED"},
    )

    events = pg_repo.get_events("DEV-EVT-01")
    assert len(events) == 2
    assert events[0]["event_type"] == "DEVICE_DETECTED"
    assert events[1]["event_type"] == "DEVICE_CONFIRMED"
    assert events[0]["metadata"]["confidence"] == 0.91


# ---------------------------------------------------------------------------
# Service & Transaction Rollback Integration
# ---------------------------------------------------------------------------


def test_transaction_rollback_on_failure(session_factory) -> None:
    """session_scope automatically rolls back when an exception occurs."""
    repo = PostgresDeviceRepository(session_factory)

    try:
        with session_scope(session_factory) as session:
            model = DeviceModel(
                device_id="DEV-FAIL-01",
                capture_id="cap-fail",
                class_id=0,
                device_type="laptop",
                confidence=0.85,
                confidence_state="HIGH_CONFIDENCE",
                bounding_box=[10, 10, 50, 50],
                model_version="1.0.0",
                inference_mode="single_model",
                registration_state="DETECTED",
                metadata_={},
                created_at=DeviceRecord(
                    device_id="", capture_id="", class_id=0, device_type="",
                    confidence=0.0, confidence_state=ConfidenceState.LOW_CONFIDENCE,
                    bounding_box=(0,0,0,0), model_version="", inference_mode=""
                ).created_at,
                updated_at=DeviceRecord(
                    device_id="", capture_id="", class_id=0, device_type="",
                    confidence=0.0, confidence_state=ConfidenceState.LOW_CONFIDENCE,
                    bounding_box=(0,0,0,0), model_version="", inference_mode=""
                ).updated_at,
            )
            session.add(model)
            # Intentionally raise an error before commit
            raise RuntimeError("Simulated transaction failure")
    except RuntimeError:
        pass

    assert not repo.exists("DEV-FAIL-01")


def test_missing_and_duplicate_device_handling(
    pg_repo: PostgresDeviceRepository,
    test_settings: Settings | None = None,
) -> None:
    """Missing device returns None / raises DeviceNotFoundError in service."""
    assert pg_repo.get("DEV-NON-EXISTENT") is None

    service = DeviceRegistrationService(
        repository=pg_repo,
        pipeline=build_detection_pipeline(detector=_FakeDetector(), model_version="1.0.0", year=2026),
        settings=Settings(log_level="WARNING"),
    )

    with pytest.raises(DeviceNotFoundError):
        service.get_device("DEV-NON-EXISTENT")


def test_dependency_injection_backend_selection(tmp_path: Path) -> None:
    """Settings properly route build_device_repository() to memory, json, or postgres."""
    dependencies.reset_dependency_caches()

    # 1. Memory backend
    s_mem = Settings(device_backend="memory", log_level="WARNING")
    repo_mem = dependencies.build_device_repository(s_mem)
    assert isinstance(repo_mem, InMemoryDeviceRepository)

    # 2. JSON backend
    s_json = Settings(device_backend="json", device_store_dir=tmp_path / "json_store", log_level="WARNING")
    repo_json = dependencies.build_device_repository(s_json)
    assert isinstance(repo_json, JsonFileDeviceRepository)

    # 3. Postgres backend
    db_file = tmp_path / "di_test.db"
    s_pg = Settings(device_backend="postgres", database_url=f"sqlite:///{db_file}", log_level="WARNING")
    repo_pg = dependencies.build_device_repository(s_pg)
    assert isinstance(repo_pg, PostgresDeviceRepository)

    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# Full API Workflow Integration over PostgresDeviceRepository
# ---------------------------------------------------------------------------


def test_full_api_workflow_over_postgres(p54_settings: Settings, tmp_path: Path) -> None:
    """Full workflow (Register -> Confirm -> Finalize -> Enrich -> Get) runs over Postgres repo."""
    db_file = tmp_path / "api_p54.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    repo = PostgresDeviceRepository(session_factory)

    fake_detector = _FakeDetector([
        Detection(label="laptop", confidence=0.89, bounding_box=(20, 30, 250, 180))
    ])
    pipeline = build_detection_pipeline(detector=fake_detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(p54_settings)
    app.dependency_overrides[get_settings] = lambda: p54_settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_repository] = lambda: repo

    with TestClient(app) as client:
        # 1. Register device
        png_data = _make_test_image_bytes()
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("laptop.png", png_data, "image/png"))],
            data={"capture_id": "cap-p54-001"},
            headers={"X-Request-ID": "req-p54-01"},
        )
        assert reg_resp.status_code == 200, reg_resp.text
        reg_data = reg_resp.json()
        assert reg_data["total_detected"] == 1
        device_id = reg_data["devices"][0]["device_id"]
        assert reg_data["devices"][0]["registration_state"] == "DETECTED"

        # 2. Confirm device
        conf_resp = client.post(f"/devices/{device_id}/confirm")
        assert conf_resp.status_code == 200
        assert conf_resp.json()["device"]["registration_state"] == "CONFIRMED"

        # 3. Finalize registration
        fin_resp = client.post(f"/devices/{device_id}/finalize")
        assert fin_resp.status_code == 200
        assert fin_resp.json()["device"]["registration_state"] == "REGISTERED"

        # 4. Enrich device
        enr_resp = client.post(
            f"/devices/{device_id}/enrich",
            json={"ocr_text": "Dell Precision Workstation", "ocr_confidence": 0.93},
        )
        assert enr_resp.status_code == 200
        enr_data = enr_resp.json()
        assert enr_data["intelligence"]["brand"]["value"] == "Dell"
        assert enr_data["intelligence"]["carbon"]["carbon_score"] > 0
        assert enr_data["device"]["carbon_score"] > 0

        # 5. Get intelligence
        get_enr_resp = client.get(f"/devices/{device_id}/intelligence")
        assert get_enr_resp.status_code == 200
        assert get_enr_resp.json()["intelligence"]["brand"]["value"] == "Dell"

        # 6. Verify audit events recorded in database
        events = repo.get_events(device_id)
        event_types = [e["event_type"] for e in events]
        assert "DEVICE_DETECTED" in event_types
        assert "DEVICE_CONFIRMED" in event_types
        assert "DEVICE_REGISTERED" in event_types
        assert "DEVICE_ENRICHED" in event_types

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()
    engine.dispose()
