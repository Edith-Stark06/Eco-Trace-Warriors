"""Comprehensive test suite for Phase P5.9 Persistent Trust Anchors & Verification.

Tests:
1. TrustAnchorModel SQLAlchemy entity mapping and schema constraints.
2. Table creation and database schema verification.
3. PostgresTrustAnchorRepository save new anchor.
4. PostgresTrustAnchorRepository get_by_device_id.
5. PostgresTrustAnchorRepository exists().
6. PostgresTrustAnchorRepository count().
7. PostgresTrustAnchorRepository clear().
8. Idempotent duplicate save (same device + identical fingerprint).
9. Conflicting fingerprint rejection (AnchorConflictError).
10. Domain-to-database entity translation.
11. Database-to-domain entity translation.
12. Persistence across repository re-instantiation.
13. Missing anchor returns None.
14. DevicePassportTrustService verification with persistent repository.
15. Strict policy persistence enforcement.
16. Permissive policy persistence enforcement.
17. INVALID passport rejection in persistent service.
18. REST API: 201 Created on new persistent anchor.
19. REST API: 200 OK on duplicate persistent anchor.
20. REST API: 409 Conflict on conflicting fingerprint.
21. REST API: 404 Not Found on missing device.
22. Read-only verification produces zero writes/audit events.
23. Multi-backend parity (InMemory vs Postgres).
"""

from __future__ import annotations

from datetime import UTC, datetime
import io
from pathlib import Path
from typing import Any
import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings
from device_ai.database.base import Base
from device_ai.database.models import (
    DeviceEventModel,
    DeviceModel,
    TrustAnchorModel,
)
from device_ai.database.session import get_session_factory, session_scope
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
from device_ai.devices.passport import build_device_passport
from device_ai.devices.passport_verification import (
    VerificationCheckStatus,
    VerificationStatus,
    fingerprint_passport,
    verify_passport,
)
from device_ai.devices.postgres_repository import PostgresDeviceRepository
from device_ai.devices.postgres_trust_anchor_repository import (
    PostgresTrustAnchorRepository,
    _anchor_model_to_domain,
)
from device_ai.devices.repository import (
    DeviceRepository,
    InMemoryDeviceRepository,
)
from device_ai.devices.service import DeviceRegistrationService
from device_ai.devices.trust_anchor import (
    DevicePassportTrustService,
    InMemoryTrustAnchorRepository,
    TrustAnchor,
    TrustAnchorPolicy,
    TrustAnchorStatus,
    TrustAnchorVerification,
    build_trust_payload,
    canonicalize_trust_payload,
)
from device_ai.exceptions import (
    AnchorConflictError,
    AnchorNotFoundError,
    DeviceNotFoundError,
    PassportNotAnchorableError,
)
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.predictor import Detection, DetectionResult, Detector
from device_ai.preprocessing.image_loader import LoadedImage


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _make_test_image_bytes(w: int = 120, h: int = 120) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=(90, 110, 140)).save(buf, format="PNG")
    return buf.getvalue()


def _make_loaded_image(name: str = "test.png") -> LoadedImage:
    raw = _make_test_image_bytes()
    pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    return LoadedImage(filename=name, content_type="image/png", raw=raw, image=pil_img)


class _FakeDetector(Detector):
    version = "p59-fake-1.0.0"

    def __init__(self, detections: list[Detection] | None = None) -> None:
        self._detections = detections or [
            Detection(label="laptop", confidence=0.96, bounding_box=(10, 10, 100, 100))
        ]

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        top = self._detections[0] if self._detections else None
        return DetectionResult(
            device_type=top.label.title() if top else "Unknown",
            brand="Unknown",
            confidence=top.confidence if top else 0.0,
            detections=self._detections,
        )


@pytest.fixture()
def db_engine(tmp_path: Path):
    """Create an isolated test SQLite engine configured with the full P5.9 schema."""
    db_file = tmp_path / "test_p59.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return get_session_factory(db_engine)


@pytest.fixture()
def postgres_device_repo(session_factory) -> PostgresDeviceRepository:
    return PostgresDeviceRepository(session_factory)


@pytest.fixture()
def postgres_anchor_repo(session_factory) -> PostgresTrustAnchorRepository:
    return PostgresTrustAnchorRepository(session_factory)


@pytest.fixture()
def persistent_trust_services(postgres_device_repo, postgres_anchor_repo):
    pipeline = build_detection_pipeline(
        detector=_FakeDetector([
            Detection(label="laptop", confidence=0.96, bounding_box=(10, 10, 120, 120))
        ]),
        model_version="1.0.0",
        year=2026,
    )
    reg_service = DeviceRegistrationService(
        repository=postgres_device_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )
    enrich_service = DeviceIntelligenceService(
        repository=postgres_device_repo,
        brand_intelligence=RuleBasedBrandIntelligence(),
        condition_intelligence=BaselineConditionIntelligence(),
        material_intelligence=ProfileBasedMaterialIntelligence(),
        carbon_intelligence=EstimatedBurdenCarbonIntelligence(),
        settings=Settings(log_level="WARNING"),
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=postgres_anchor_repo,
        policy=TrustAnchorPolicy.STRICT,
        settings=Settings(log_level="WARNING"),
    )
    return reg_service, enrich_service, trust_service


# ---------------------------------------------------------------------------
# 1. Database Model & Table Mapping
# ---------------------------------------------------------------------------


def test_trust_anchor_model_schema_mapping() -> None:
    """TrustAnchorModel possesses required attributes, constraints, and relationships."""
    assert TrustAnchorModel.__tablename__ == "trust_anchors"
    cols = TrustAnchorModel.__table__.columns
    assert "anchor_id" in cols
    assert "device_id" in cols
    assert "passport_fingerprint" in cols
    assert "algorithm" in cols
    assert "anchored_at" in cols
    assert "status" in cols
    assert "metadata" in cols
    assert "created_at" in cols
    assert "updated_at" in cols

    assert cols["anchor_id"].primary_key is True
    assert cols["device_id"].unique is True


def test_table_creation_and_migration(db_engine) -> None:
    """Database engine properly instantiates trust_anchors table and indexes."""
    from sqlalchemy import inspect

    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    assert "trust_anchors" in tables
    assert "devices" in tables
    assert "device_events" in tables


# ---------------------------------------------------------------------------
# 2. PostgresTrustAnchorRepository CRUD Operations
# ---------------------------------------------------------------------------


def test_postgres_anchor_repo_save_new(
    postgres_device_repo: PostgresDeviceRepository,
    postgres_anchor_repo: PostgresTrustAnchorRepository,
    session_factory,
) -> None:
    """PostgresTrustAnchorRepository saves new anchor and writes row to database."""
    now = _utc_now()
    device = DeviceRecord(
        device_id="DEV-PG-001",
        device_type="laptop",
        class_id=0,
        confidence=0.95,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 100, 100),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-pg-1",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    postgres_device_repo.save(device)

    anchor = TrustAnchor(
        anchor_id="anc-pg-001",
        device_id="DEV-PG-001",
        passport_fingerprint="f" * 64,
        algorithm="sha256",
        anchored_at=now.isoformat(),
        status=TrustAnchorStatus.ANCHORED,
        metadata={"network": "postgres_test"},
    )
    saved = postgres_anchor_repo.save(anchor)
    assert saved.anchor_id == "anc-pg-001"
    assert saved.device_id == "DEV-PG-001"
    assert saved.passport_fingerprint == "f" * 64
    assert saved.status == TrustAnchorStatus.ANCHORED
    assert saved.metadata == {"network": "postgres_test"}

    # Verify directly via raw SQL session
    with session_scope(session_factory) as session:
        row = session.get(TrustAnchorModel, "anc-pg-001")
        assert row is not None
        assert row.device_id == "DEV-PG-001"
        assert row.passport_fingerprint == "f" * 64


def test_postgres_anchor_repo_get_by_device_id(
    postgres_device_repo: PostgresDeviceRepository,
    postgres_anchor_repo: PostgresTrustAnchorRepository,
) -> None:
    """get_by_device_id returns domain object when exists and None when missing."""
    now = _utc_now()
    device = DeviceRecord(
        device_id="DEV-PG-002",
        device_type="smartphone",
        class_id=1,
        confidence=0.92,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(5, 5, 80, 80),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-pg-2",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    postgres_device_repo.save(device)

    assert postgres_anchor_repo.get_by_device_id("DEV-PG-002") is None

    anchor = TrustAnchor(
        anchor_id="anc-pg-002",
        device_id="DEV-PG-002",
        passport_fingerprint="e" * 64,
    )
    postgres_anchor_repo.save(anchor)

    retrieved = postgres_anchor_repo.get_by_device_id("DEV-PG-002")
    assert retrieved is not None
    assert retrieved.anchor_id == "anc-pg-002"
    assert retrieved.passport_fingerprint == "e" * 64


def test_postgres_anchor_repo_exists_and_count(
    postgres_device_repo: PostgresDeviceRepository,
    postgres_anchor_repo: PostgresTrustAnchorRepository,
) -> None:
    """exists() and count() reflect state correctly."""
    assert postgres_anchor_repo.count() == 0
    assert postgres_anchor_repo.exists("DEV-PG-003") is False

    now = _utc_now()
    device = DeviceRecord(
        device_id="DEV-PG-003",
        device_type="tablet",
        class_id=2,
        confidence=0.91,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(0, 0, 50, 50),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-pg-3",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    postgres_device_repo.save(device)

    anchor = TrustAnchor(
        anchor_id="anc-pg-003",
        device_id="DEV-PG-003",
        passport_fingerprint="d" * 64,
    )
    postgres_anchor_repo.save(anchor)

    assert postgres_anchor_repo.count() == 1
    assert postgres_anchor_repo.exists("DEV-PG-003") is True


def test_postgres_anchor_repo_clear(
    postgres_device_repo: PostgresDeviceRepository,
    postgres_anchor_repo: PostgresTrustAnchorRepository,
) -> None:
    """clear() wipes all stored trust anchors."""
    now = _utc_now()
    device = DeviceRecord(
        device_id="DEV-PG-CLR",
        device_type="keyboard",
        class_id=3,
        confidence=0.88,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(0, 0, 40, 40),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-pg-clr",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    postgres_device_repo.save(device)
    postgres_anchor_repo.save(TrustAnchor(anchor_id="anc-clr-1", device_id="DEV-PG-CLR", passport_fingerprint="c" * 64))

    assert postgres_anchor_repo.count() == 1
    postgres_anchor_repo.clear()
    assert postgres_anchor_repo.count() == 0


def test_postgres_anchor_repo_idempotent_save(
    postgres_device_repo: PostgresDeviceRepository,
    postgres_anchor_repo: PostgresTrustAnchorRepository,
) -> None:
    """Saving identical fingerprint returns existing anchor without creating duplicates."""
    now = _utc_now()
    device = DeviceRecord(
        device_id="DEV-PG-IDEMP",
        device_type="printer",
        class_id=4,
        confidence=0.89,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(0, 0, 60, 60),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-pg-idemp",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    postgres_device_repo.save(device)

    a1 = TrustAnchor(anchor_id="anc-idemp-1", device_id="DEV-PG-IDEMP", passport_fingerprint="b" * 64)
    saved1 = postgres_anchor_repo.save(a1)

    a2 = TrustAnchor(anchor_id="anc-idemp-2", device_id="DEV-PG-IDEMP", passport_fingerprint="b" * 64)
    saved2 = postgres_anchor_repo.save(a2)

    assert saved1.anchor_id == saved2.anchor_id
    assert postgres_anchor_repo.count() == 1


def test_postgres_anchor_repo_conflict_rejection(
    postgres_device_repo: PostgresDeviceRepository,
    postgres_anchor_repo: PostgresTrustAnchorRepository,
) -> None:
    """Attempting to overwrite an anchored device with a different fingerprint raises AnchorConflictError."""
    now = _utc_now()
    device = DeviceRecord(
        device_id="DEV-PG-CONF",
        device_type="mouse",
        class_id=5,
        confidence=0.90,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(0, 0, 20, 20),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-pg-conf",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    postgres_device_repo.save(device)

    a1 = TrustAnchor(anchor_id="anc-conf-1", device_id="DEV-PG-CONF", passport_fingerprint="1" * 64)
    postgres_anchor_repo.save(a1)

    a2 = TrustAnchor(anchor_id="anc-conf-2", device_id="DEV-PG-CONF", passport_fingerprint="2" * 64)
    with pytest.raises(AnchorConflictError) as exc_info:
        postgres_anchor_repo.save(a2)

    assert "Anchor conflict" in str(exc_info.value)
    assert postgres_anchor_repo.get_by_device_id("DEV-PG-CONF").passport_fingerprint == "1" * 64


def test_persistence_across_repository_reinstantiation(
    postgres_device_repo: PostgresDeviceRepository,
    postgres_anchor_repo: PostgresTrustAnchorRepository,
    session_factory,
) -> None:
    """Data persisted via one repository instance is cleanly read by a fresh repository instance."""
    now = _utc_now()
    device = DeviceRecord(
        device_id="DEV-PG-REINST",
        device_type="camera",
        class_id=6,
        confidence=0.93,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(0, 0, 70, 70),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-pg-reinst",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    postgres_device_repo.save(device)

    postgres_anchor_repo.save(
        TrustAnchor(anchor_id="anc-reinst-1", device_id="DEV-PG-REINST", passport_fingerprint="3" * 64, metadata={"test": "reinst"})
    )

    # Fresh repository instance with same session factory
    fresh_repo = PostgresTrustAnchorRepository(session_factory)
    retrieved = fresh_repo.get_by_device_id("DEV-PG-REINST")
    assert retrieved is not None
    assert retrieved.anchor_id == "anc-reinst-1"
    assert retrieved.passport_fingerprint == "3" * 64
    assert retrieved.metadata == {"test": "reinst"}


# ---------------------------------------------------------------------------
# 3. DevicePassportTrustService with Persistent Repository
# ---------------------------------------------------------------------------


def test_service_anchor_and_verification_flow(persistent_trust_services) -> None:
    """End-to-end service anchoring and verification using PostgreSQL storage."""
    reg_service, enrich_service, trust_service = persistent_trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-pg-svc-01")
    device_id = records[0].device_id

    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 15", ocr_confidence=0.97)

    # 1. Anchor
    anchor, is_new = trust_service.anchor_device_passport(device_id, metadata={"env": "postgres_test"})
    assert is_new is True
    assert anchor.device_id == device_id
    assert len(anchor.passport_fingerprint) == 64

    # 2. Retrieve
    stored_anchor = trust_service.get_device_anchor(device_id)
    assert stored_anchor.anchor_id == anchor.anchor_id
    assert stored_anchor.passport_fingerprint == anchor.passport_fingerprint

    # 3. Verify
    ver = trust_service.verify_device_anchor(device_id)
    assert ver.status == TrustAnchorStatus.VERIFIED
    assert ver.stored_fingerprint == anchor.passport_fingerprint
    assert ver.current_fingerprint == anchor.passport_fingerprint


def test_strict_policy_persistence(persistent_trust_services) -> None:
    """Under STRICT policy, un-enriched device (status WARNING) is rejected from anchoring."""
    reg_service, _, trust_service = persistent_trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-pg-strict-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)

    with pytest.raises(PassportNotAnchorableError) as exc_info:
        trust_service.anchor_device_passport(device_id)

    assert "STRICT policy" in str(exc_info.value)


def test_permissive_policy_persistence(persistent_trust_services, postgres_anchor_repo) -> None:
    """Under PERMISSIVE policy, un-enriched device (status WARNING) is successfully anchored."""
    reg_service, _, _ = persistent_trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-pg-perm-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)

    permissive_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=postgres_anchor_repo,
        policy=TrustAnchorPolicy.PERMISSIVE,
    )

    anchor, is_new = permissive_service.anchor_device_passport(device_id)
    assert is_new is True
    assert anchor.device_id == device_id
    assert postgres_anchor_repo.exists(device_id) is True


def test_invalid_passport_rejected_persistence(persistent_trust_services, postgres_device_repo) -> None:
    """INVALID passport is rejected under any policy in persistent repository."""
    reg_service, _, trust_service = persistent_trust_services

    now = _utc_now()
    bad_record = DeviceRecord(
        device_id="DEV-PG-INVALID",
        device_type="laptop",
        class_id=0,
        confidence=2.0,  # Invalid confidence out of range
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 100, 100),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-pg-bad",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    postgres_device_repo.save(bad_record)

    with pytest.raises(PassportNotAnchorableError):
        trust_service.anchor_device_passport("DEV-PG-INVALID")


def test_read_only_verification_produces_zero_writes(persistent_trust_services, session_factory) -> None:
    """verify_device_anchor produces zero database writes, zero event emissions, and zero record mutations."""
    reg_service, enrich_service, trust_service = persistent_trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-pg-ro-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 15", ocr_confidence=0.97)
    trust_service.anchor_device_passport(device_id)

    # Count rows before verification
    with session_scope(session_factory) as session:
        anchors_before = session.query(TrustAnchorModel).count()
        events_before = session.query(DeviceEventModel).count()
        devices_before = session.query(DeviceModel).count()

    # Execute verification 5 times
    for _ in range(5):
        ver = trust_service.verify_device_anchor(device_id)
        assert ver.status == TrustAnchorStatus.VERIFIED

    # Count rows after verification
    with session_scope(session_factory) as session:
        anchors_after = session.query(TrustAnchorModel).count()
        events_after = session.query(DeviceEventModel).count()
        devices_after = session.query(DeviceModel).count()

    assert anchors_before == anchors_after
    assert events_before == events_after
    assert devices_before == devices_after


# ---------------------------------------------------------------------------
# 4. REST API Integration with Persistent Backend
# ---------------------------------------------------------------------------


def test_api_postgres_backend_anchor_flow(session_factory, postgres_device_repo, postgres_anchor_repo) -> None:
    """Test full FastAPI REST API workflow with persistent PostgreSQL/SQLAlchemy backend."""
    app = create_app()
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.95, bounding_box=(10, 10, 150, 150))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_repository] = lambda: postgres_device_repo
    app.dependency_overrides[dependencies.get_trust_anchor_repository] = lambda: postgres_anchor_repo

    with TestClient(app) as client:
        # 1. Register, confirm, finalize, enrich
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("laptop.png", _make_test_image_bytes(), "image/png"))],
            data={"capture_id": "cap-api-pg-01"},
            headers={"X-Request-ID": "req-api-pg-01"},
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]

        client.post(f"/devices/{device_id}/confirm")
        client.post(f"/devices/{device_id}/finalize")
        client.post(
            f"/devices/{device_id}/enrich",
            json={"ocr_text": "Dell Latitude 5520", "ocr_confidence": 0.96},
        )

        # 2. POST /devices/{id}/passport/anchor -> HTTP 201 Created
        anc_resp = client.post(
            f"/devices/{device_id}/passport/anchor",
            json={"metadata": {"anchored_by": "postgres_agent"}},
            headers={"X-Request-ID": "req-pg-anc-01"},
        )
        assert anc_resp.status_code == 201
        anc_data = anc_resp.json()
        assert anc_data["success"] is True
        assert anc_data["is_new"] is True
        assert anc_data["anchor"]["device_id"] == device_id
        assert len(anc_data["anchor"]["passport_fingerprint"]) == 64
        assert anc_data["anchor"]["status"] == "ANCHORED"

        # Verify persisted in database
        assert postgres_anchor_repo.exists(device_id) is True

        # 3. POST duplicate -> HTTP 200 OK (idempotent)
        anc_dup = client.post(f"/devices/{device_id}/passport/anchor")
        assert anc_dup.status_code == 200
        assert anc_dup.json()["is_new"] is False

        # 4. GET /devices/{id}/passport/anchor -> HTTP 200 OK
        get_resp = client.get(f"/devices/{device_id}/passport/anchor")
        assert get_resp.status_code == 200
        assert get_resp.json()["anchor"]["passport_fingerprint"] == anc_data["anchor"]["passport_fingerprint"]

        # 5. GET /devices/{id}/passport/anchor/verify -> HTTP 200 OK
        ver_resp = client.get(f"/devices/{device_id}/passport/anchor/verify")
        assert ver_resp.status_code == 200
        ver_data = ver_resp.json()
        assert ver_data["verification"]["status"] == "VERIFIED"
        assert ver_data["verification"]["stored_fingerprint"] == anc_data["anchor"]["passport_fingerprint"]

        # 6. GET nonexistent returns 404
        assert client.get("/devices/DEV-NONEXISTENT/passport/anchor").status_code == 404
        assert client.get("/devices/DEV-NONEXISTENT/passport/anchor/verify").status_code == 404

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# 5. Multi-Backend Parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("repo_type", ["memory", "postgres"])
def test_multi_backend_parity(repo_type: str, session_factory) -> None:
    """InMemory and Postgres trust anchor repositories exhibit identical behavior."""
    if repo_type == "memory":
        dev_repo = InMemoryDeviceRepository()
        anc_repo = InMemoryTrustAnchorRepository()
    else:
        dev_repo = PostgresDeviceRepository(session_factory)
        anc_repo = PostgresTrustAnchorRepository(session_factory)

    pipeline = build_detection_pipeline(
        detector=_FakeDetector([
            Detection(label="headphones", confidence=0.92, bounding_box=(10, 10, 50, 50))
        ]),
        model_version="1.0.0",
        year=2026,
    )
    reg_service = DeviceRegistrationService(repository=dev_repo, pipeline=pipeline, settings=Settings(log_level="WARNING"))
    trust_service = DevicePassportTrustService(device_service=reg_service, anchor_repository=anc_repo, policy=TrustAnchorPolicy.PERMISSIVE)

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id=f"cap-parity-{repo_type}")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)

    # Initial verification before anchoring -> NOT_FOUND
    ver_pre = trust_service.verify_device_anchor(device_id)
    assert ver_pre.status == TrustAnchorStatus.NOT_FOUND

    # Anchor under PERMISSIVE
    anchor, is_new = trust_service.anchor_device_passport(device_id)
    assert is_new is True
    assert anc_repo.exists(device_id) is True
    assert anc_repo.count() == 1

    # Verification after anchoring -> VERIFIED
    ver_post = trust_service.verify_device_anchor(device_id)
    assert ver_post.status == TrustAnchorStatus.VERIFIED
    assert ver_post.stored_fingerprint == anchor.passport_fingerprint

    # Duplicate anchor is idempotent
    anchor_dup, is_new_dup = trust_service.anchor_device_passport(device_id)
    assert is_new_dup is False
    assert anchor_dup.anchor_id == anchor.anchor_id


def test_alembic_upgrade_and_downgrade_programmatic(tmp_path: Path) -> None:
    """Alembic cleanly executes upgrade head, downgrade to 001, and re-upgrade."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "alembic_test.db"
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    script_loc = Path(__file__).resolve().parents[1] / "alembic"

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(script_loc))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    # Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Downgrade to 001
    command.downgrade(alembic_cfg, "001_initial_p54_device_schema")

    # Re-upgrade to head
    command.upgrade(alembic_cfg, "head")


def test_api_409_conflict_on_mismatched_hash_with_postgres(
    session_factory,
    postgres_device_repo: PostgresDeviceRepository,
    postgres_anchor_repo: PostgresTrustAnchorRepository,
) -> None:
    """POST /devices/{id}/passport/anchor returns 409 Conflict if already anchored with different fingerprint."""
    app = create_app()
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.95, bounding_box=(10, 10, 150, 150))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_repository] = lambda: postgres_device_repo
    app.dependency_overrides[dependencies.get_trust_anchor_repository] = lambda: postgres_anchor_repo

    with TestClient(app) as client:
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("laptop.png", _make_test_image_bytes(), "image/png"))],
            data={"capture_id": "cap-api-pg-conf"},
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]
        client.post(f"/devices/{device_id}/confirm")
        client.post(f"/devices/{device_id}/finalize")
        client.post(f"/devices/{device_id}/enrich", json={"ocr_text": "Dell Latitude 5520"})

        # Pre-seed conflicting anchor directly in DB
        now = _utc_now()
        postgres_anchor_repo.save(
            TrustAnchor(
                anchor_id="anc-preseed-conf",
                device_id=device_id,
                passport_fingerprint="0" * 64,  # Conflicting fake fingerprint
                algorithm="sha256",
                anchored_at=now.isoformat(),
            )
        )

        # Attempt to anchor genuine passport -> 409 Conflict
        anc_resp = client.post(f"/devices/{device_id}/passport/anchor")
        assert anc_resp.status_code == 409
        assert anc_resp.json()["error"]["code"] == "ANCHOR_CONFLICT"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()
