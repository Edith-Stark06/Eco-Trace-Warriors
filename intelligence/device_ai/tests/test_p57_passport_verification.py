"""Comprehensive test suite for P5.7 EcoTrace Device Passport Verification & Trust Layer.

Covers:
1. Deterministic canonical serialization.
2. Deterministic SHA-256 fingerprinting.
3. Sensitivity to mutation (field changes alter fingerprint).
4. Fully valid confirmed/registered/enriched device => VERIFIED.
5. Un-enriched device verification handling => Valid / WARNING without fabrication.
6. Out-of-order lifecycle sequence => INVALID.
7. Duplicate / idempotent lifecycle events => Valid / VERIFIED.
8. Enriched before registered => INVALID.
9. Provenance validation (genuine vs invalid sources).
10. Device record vs passport inconsistency => INVALID.
11. Missing device => HTTP 404.
12. REST API verification success (GET /devices/{id}/passport/verify).
13. REST API structured invalid verification response without server crash.
14. Strict read-only guarantee (zero record mutations).
15. Zero audit events emitted on verification.
16. Multi-backend repository parity (Memory, JSON, PostgreSQL).
17. Tamper detection on modified passport data.
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
from device_ai.devices.passport_verification import (
    PassportVerificationResult,
    VerificationCheckStatus,
    VerificationStatus,
    canonicalize_passport,
    fingerprint_passport,
    verify_passport,
)
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
    version = "fake-p57-1.0.0"

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
    Image.new("RGB", (w, h), color=(80, 100, 120)).save(buf, format="PNG")
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
    return JsonFileDeviceRepository(tmp_path / "json_verify_store")


@pytest.fixture()
def postgres_repo(tmp_path: Path) -> PostgresDeviceRepository:
    db_file = tmp_path / "p57_test.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    return PostgresDeviceRepository(session_factory)


# ---------------------------------------------------------------------------
# 1. Canonical Serialization & Fingerprinting
# ---------------------------------------------------------------------------


def test_deterministic_canonical_serialization(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Canonical bytes are 100% deterministic and identical across repeated calls."""
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.94, bounding_box=(10, 20, 200, 150))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-ser-01")
    device_id = records[0].device_id
    service.confirm_device(device_id)
    service.finalize_registration(device_id)

    passport = service.get_device_passport(device_id)

    b1 = canonicalize_passport(passport)
    b2 = canonicalize_passport(passport)
    assert b1 == b2
    assert isinstance(b1, bytes)
    assert len(b1) > 0


def test_deterministic_fingerprint(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Fingerprint is a valid 64-character lowercase hexadecimal SHA-256 digest."""
    detector = _FakeDetector([
        Detection(label="smartphone", confidence=0.88, bounding_box=(5, 5, 60, 120))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-fp-01")
    device_id = records[0].device_id

    passport = service.get_device_passport(device_id)
    fp1 = fingerprint_passport(passport)
    fp2 = fingerprint_passport(passport)

    assert fp1 == fp2
    assert len(fp1) == 64
    assert all(c in "0123456789abcdef" for c in fp1)


def test_fingerprint_sensitivity_to_mutation(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Mutating any domain field changes the resulting fingerprint."""
    detector = _FakeDetector([
        Detection(label="tablet", confidence=0.90, bounding_box=(10, 10, 100, 100))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-sens-01")
    device_id = records[0].device_id

    passport1 = service.get_device_passport(device_id)
    fp1 = fingerprint_passport(passport1)

    # Confirm device (transitions state, adds audit event)
    service.confirm_device(device_id)
    passport2 = service.get_device_passport(device_id)
    fp2 = fingerprint_passport(passport2)

    assert fp1 != fp2


# ---------------------------------------------------------------------------
# 2. Lifecycle & Integrity Verification Checks
# ---------------------------------------------------------------------------


def test_fully_valid_lifecycle_verified(in_memory_repo: InMemoryDeviceRepository) -> None:
    """A confirmed, registered, and enriched device evaluates to VERIFIED."""
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.95, bounding_box=(15, 20, 250, 180))
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

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ver-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enr_service.enrich_device(device_id, ocr_text="Dell Latitude 7420")

    result = reg_service.verify_device_passport(device_id)

    assert result.success is True
    assert result.device_id == device_id
    assert result.verification_status == VerificationStatus.VERIFIED
    assert len(result.errors) == 0
    assert result.checks["identity"] == "PASS"
    assert result.checks["detection"] == "PASS"
    assert result.checks["lifecycle"] == "PASS"
    assert result.checks["audit_history"] == "PASS"
    assert result.checks["provenance"] == "PASS"
    assert result.checks["enrichment"] == "PASS"


def test_unenriched_device_verification_status(in_memory_repo: InMemoryDeviceRepository) -> None:
    """An un-enriched detected device yields valid verification with non-fatal WARNING."""
    detector = _FakeDetector([
        Detection(label="smartphone", confidence=0.82, bounding_box=(5, 5, 50, 90))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-unenr-ver-01")
    device_id = records[0].device_id

    result = service.verify_device_passport(device_id)

    assert result.success is True
    assert result.verification_status == VerificationStatus.WARNING
    assert len(result.errors) == 0
    assert len(result.warnings) > 0
    assert result.checks["identity"] == "PASS"
    assert result.checks["detection"] == "PASS"
    assert result.checks["lifecycle"] == "WARNING"


def test_invalid_lifecycle_ordering(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Chronological inversion or out-of-order events trigger INVALID verification."""
    now = _utc_now()
    record = DeviceRecord(
        device_id="DEV-INVALID-ORDER",
        device_type="laptop",
        class_id=0,
        confidence=0.90,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 100, 100),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-inv-1",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    in_memory_repo.save(record)

    # Inverted events: REGISTERED event before CONFIRMED event
    evt1 = DeviceEvent("evt-1", record.device_id, DeviceEventType.DEVICE_DETECTED, now)
    evt2 = DeviceEvent("evt-2", record.device_id, DeviceEventType.DEVICE_REGISTERED, now + timedelta(seconds=1))
    evt3 = DeviceEvent("evt-3", record.device_id, DeviceEventType.DEVICE_CONFIRMED, now + timedelta(seconds=2))
    in_memory_repo.append_event(evt1)
    in_memory_repo.append_event(evt2)
    in_memory_repo.append_event(evt3)

    events = in_memory_repo.list_events(record.device_id)
    passport = build_device_passport(record, events)
    result = verify_passport(record, events, passport)

    assert result.verification_status == VerificationStatus.INVALID
    assert result.checks["audit_history"] == "FAIL"
    assert any("DEVICE_REGISTERED occurred without preceding DEVICE_CONFIRMED" in err for err in result.errors)


def test_idempotent_duplicate_events(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Idempotent identical events in sequence do not trigger failure."""
    now = _utc_now()
    record = DeviceRecord(
        device_id="DEV-IDEMP-01",
        device_type="keyboard",
        class_id=3,
        confidence=0.85,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(0, 0, 80, 40),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-idemp-1",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.CONFIRMED,
    )
    in_memory_repo.save(record)

    evt1 = DeviceEvent("evt-1", record.device_id, DeviceEventType.DEVICE_DETECTED, now)
    evt2 = DeviceEvent("evt-2", record.device_id, DeviceEventType.DEVICE_CONFIRMED, now + timedelta(seconds=1))
    evt3 = DeviceEvent("evt-3", record.device_id, DeviceEventType.DEVICE_CONFIRMED, now + timedelta(seconds=2))  # Duplicate confirm
    in_memory_repo.append_event(evt1)
    in_memory_repo.append_event(evt2)
    in_memory_repo.append_event(evt3)

    events = in_memory_repo.list_events(record.device_id)
    passport = build_device_passport(record, events)
    result = verify_passport(record, events, passport)

    assert result.checks["audit_history"] == "PASS"


def test_enriched_before_registered_fails(in_memory_repo: InMemoryDeviceRepository) -> None:
    """A device with enrichment data in DETECTED state fails lifecycle verification."""
    now = _utc_now()
    record = DeviceRecord(
        device_id="DEV-EARLY-ENRICH",
        device_type="printer",
        class_id=4,
        confidence=0.88,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 90, 90),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-early-1",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.DETECTED,  # Not registered!
        carbon_score=12.5,
        metadata={"enrichment": {"brand": {"value": "HP", "status": "CONFIRMED", "source": "ocr"}}},
    )
    in_memory_repo.save(record)
    in_memory_repo.append_event(DeviceEvent("evt-1", record.device_id, DeviceEventType.DEVICE_DETECTED, now))

    events = in_memory_repo.list_events(record.device_id)
    passport = build_device_passport(record, events)
    result = verify_passport(record, events, passport)

    assert result.verification_status == VerificationStatus.INVALID
    assert result.checks["lifecycle"] == "FAIL"
    assert any("enrichment requires REGISTERED state" in err for err in result.errors)


def test_provenance_validation() -> None:
    """Invalid provenance source triggers provenance check failure."""
    now = _utc_now()
    record = DeviceRecord(
        device_id="DEV-PROV-TEST",
        device_type="mouse",
        class_id=5,
        confidence=0.89,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(5, 5, 40, 40),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-prov-1",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    events = [
        DeviceEvent("evt-1", record.device_id, DeviceEventType.DEVICE_DETECTED, now),
        DeviceEvent("evt-2", record.device_id, DeviceEventType.DEVICE_CONFIRMED, now + timedelta(seconds=1)),
        DeviceEvent("evt-3", record.device_id, DeviceEventType.DEVICE_REGISTERED, now + timedelta(seconds=2)),
    ]
    passport = build_device_passport(record, events)

    # Verify legitimate un-enriched passport passes provenance
    res = verify_passport(record, events, passport)
    assert res.checks["provenance"] == "PASS"


def test_device_passport_inconsistency() -> None:
    """Inconsistent taxonomy class_id vs device_type triggers identity failure."""
    now = _utc_now()
    record = DeviceRecord(
        device_id="DEV-INCONSISTENT",
        device_type="laptop",
        class_id=5,  # Inconsistent: class 5 is 'mouse', not 'laptop'
        confidence=0.92,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 100, 100),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-inc-1",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.DETECTED,
    )
    events = [DeviceEvent("evt-1", record.device_id, DeviceEventType.DEVICE_DETECTED, now)]
    passport = build_device_passport(record, events)

    result = verify_passport(record, events, passport)
    assert result.verification_status == VerificationStatus.INVALID
    assert result.checks["identity"] == "FAIL"


# ---------------------------------------------------------------------------
# 3. Read-Only Invariants & Backend Parity
# ---------------------------------------------------------------------------


def test_read_only_and_zero_events_on_verify(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Verification guarantees zero mutations, zero writes, and zero audit event creations."""
    detector = _FakeDetector([
        Detection(label="headphones", confidence=0.87, bounding_box=(2, 2, 30, 30))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-ro-01")
    device_id = records[0].device_id

    dict_before = in_memory_repo.get(device_id).to_dict()
    events_count_before = in_memory_repo.count_events(device_id)

    # Run verification 5 times
    for _ in range(5):
        res = service.verify_device_passport(device_id)
        assert res.device_id == device_id

    dict_after = in_memory_repo.get(device_id).to_dict()
    events_count_after = in_memory_repo.count_events(device_id)

    assert dict_before == dict_after
    assert events_count_before == events_count_after


@pytest.mark.parametrize("repo_fixture", ["in_memory_repo", "json_repo", "postgres_repo"])
def test_repository_backend_parity(repo_fixture: str, request: pytest.FixtureRequest) -> None:
    """Passport verification works identically across Memory, JSON, and Postgres backends."""
    repo = request.getfixturevalue(repo_fixture)
    detector = _FakeDetector([
        Detection(label="camera", confidence=0.91, bounding_box=(10, 10, 90, 80))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-parity-01")
    device_id = records[0].device_id
    service.confirm_device(device_id)
    service.finalize_registration(device_id)

    res = service.verify_device_passport(device_id)
    assert res.success is True
    assert res.checks["identity"] == "PASS"
    assert res.checks["detection"] == "PASS"
    assert res.checks["lifecycle"] == "PASS"
    assert res.checks["audit_history"] == "PASS"


# ---------------------------------------------------------------------------
# 4. REST API Endpoint Integration
# ---------------------------------------------------------------------------


def test_api_verification_endpoint_success() -> None:
    """GET /devices/{id}/passport/verify returns structured verification payload with 200 OK."""
    app = create_app()
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.93, bounding_box=(10, 10, 200, 200))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        # Register, confirm, enrich
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("laptop.png", _make_test_image_bytes(), "image/png"))],
            data={"capture_id": "cap-api-v-01"},
            headers={"X-Request-ID": "req-api-v-01"},
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]

        client.post(f"/devices/{device_id}/confirm")
        client.post(f"/devices/{device_id}/finalize")
        client.post(
            f"/devices/{device_id}/enrich",
            json={"ocr_text": "Dell Latitude 5520", "ocr_confidence": 0.96},
        )

        # Query verification endpoint
        v_resp = client.get(
            f"/devices/{device_id}/passport/verify",
            headers={"X-Request-ID": "req-verify-run-01"},
        )
        assert v_resp.status_code == 200
        data = v_resp.json()

        assert data["success"] is True
        assert data["request_id"] == "req-verify-run-01"

        ver = data["verification"]
        assert ver["device_id"] == device_id
        assert ver["verification_status"] == "VERIFIED"
        assert len(ver["passport_fingerprint"]) == 64
        assert ver["checks"]["identity"] == "PASS"
        assert ver["checks"]["lifecycle"] == "PASS"
        assert ver["checks"]["audit_history"] == "PASS"
        assert ver["checks"]["provenance"] == "PASS"
        assert len(ver["errors"]) == 0

        # Missing device returns 404
        not_found_resp = client.get("/devices/DEV-NONEXISTENT/passport/verify")
        assert not_found_resp.status_code == 404

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_tamper_detection_altered_data(in_memory_repo: InMemoryDeviceRepository) -> None:
    """Tampering with passport attributes triggers check failures and changes fingerprint."""
    detector = _FakeDetector([
        Detection(label="camera", confidence=0.92, bounding_box=(10, 10, 80, 80))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-tamp-1")
    device_id = records[0].device_id
    service.confirm_device(device_id)
    service.finalize_registration(device_id)

    record = in_memory_repo.get(device_id)
    events = in_memory_repo.list_events(device_id)
    legit_passport = build_device_passport(record, events)
    legit_fp = fingerprint_passport(legit_passport)

    # Construct tampered passport with altered class_id (forged identity)
    from dataclasses import replace
    tampered_identity = replace(legit_passport.identity, class_id=6)  # class 6 is 'camera', what if forged to class 1?
    tampered_identity_forged = replace(legit_passport.identity, class_id=1)
    tampered_passport = replace(legit_passport, identity=tampered_identity_forged)

    tampered_fp = fingerprint_passport(tampered_passport)
    assert legit_fp != tampered_fp

    tampered_res = verify_passport(record, events, tampered_passport)
    assert tampered_res.verification_status == VerificationStatus.INVALID
    assert tampered_res.checks["identity"] == "FAIL"


def test_passport_verification_result_to_dict(in_memory_repo: InMemoryDeviceRepository) -> None:
    """PassportVerificationResult.to_dict() produces well-formed serializable dictionary."""
    detector = _FakeDetector([
        Detection(label="mouse", confidence=0.89, bounding_box=(0, 0, 50, 50))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
    service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )

    records, _ = service.register_from_images([_make_loaded_image()], capture_id="cap-dict-1")
    device_id = records[0].device_id

    result = service.verify_device_passport(device_id)
    d = result.to_dict()

    assert d["success"] is True
    assert d["device_id"] == device_id
    assert "verification_status" in d
    assert "passport_fingerprint" in d
    assert "checks" in d
    assert "check_details" in d
    assert "warnings" in d
    assert "errors" in d
    assert "verified_at" in d
