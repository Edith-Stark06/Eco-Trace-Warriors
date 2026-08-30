"""Comprehensive test suite for Device Passport Trust Anchor Abstraction (P5.8).

Tests:
1. Domain model creation and serialization.
2. Deterministic trust payload creation and canonicalization.
3. InMemoryTrustAnchorRepository storage, retrieval, and count.
4. Idempotent duplicate anchoring.
5. Conflicting fingerprint rejection (AnchorConflictError).
6. Anchoring a VERIFIED passport succeeds.
7. Anchoring an INVALID passport raises PassportNotAnchorableError.
8. Anchoring a WARNING passport is rejected under STRICT policy.
9. Anchoring a WARNING passport succeeds under PERMISSIVE policy.
10. Trust anchor verification succeeds with VERIFIED status.
11. Trust anchor verification detects MISMATCH on altered data.
12. Trust anchor verification returns NOT_FOUND when unanchored.
13. Operations on non-existent device raise DeviceNotFoundError.
14. Trust anchor retrieval for unanchored device raises AnchorNotFoundError.
15. Anchor verification is strictly read-only (zero record mutations).
16. Zero audit events are emitted during anchor verification.
17. REST API: POST /devices/{id}/passport/anchor creates new anchor (HTTP 201).
18. REST API: POST /devices/{id}/passport/anchor is idempotent on duplicate (HTTP 200).
19. REST API: GET /devices/{id}/passport/anchor retrieves existing anchor (HTTP 200) and 404 when missing.
20. REST API: GET /devices/{id}/passport/anchor/verify verifies fingerprint match (HTTP 200).
"""

from __future__ import annotations

from datetime import UTC, datetime
import io
from typing import Any
import pytest
from PIL import Image
from starlette.testclient import TestClient

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings
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
from device_ai.devices.repository import (
    DeviceRepository,
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from device_ai.devices.postgres_repository import PostgresDeviceRepository
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


def _make_test_image_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (160, 160), color=(60, 90, 120))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_loaded_image(name: str = "test.png") -> LoadedImage:
    raw = _make_test_image_bytes()
    pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    return LoadedImage(filename=name, content_type="image/png", raw=raw, image=pil_img)


class _FakeDetector(Detector):
    version = "1.0.0"

    def __init__(self, detections: list[Detection] | None = None) -> None:
        self._detections = detections or [
            Detection(label="laptop", confidence=0.95, bounding_box=(10, 10, 100, 100))
        ]

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        top = self._detections[0] if self._detections else None
        return DetectionResult(
            device_type=top.label.title() if top else "Unknown",
            brand="Unknown",
            confidence=top.confidence if top else 0.0,
            detections=self._detections,
        )


@pytest.fixture
def in_memory_repo() -> InMemoryDeviceRepository:
    return InMemoryDeviceRepository()


@pytest.fixture
def anchor_repo() -> InMemoryTrustAnchorRepository:
    return InMemoryTrustAnchorRepository()


@pytest.fixture
def trust_services(in_memory_repo: InMemoryDeviceRepository, anchor_repo: InMemoryTrustAnchorRepository):
    pipeline = build_detection_pipeline(
        detector=_FakeDetector([
            Detection(label="laptop", confidence=0.96, bounding_box=(10, 10, 120, 120))
        ]),
        model_version="1.0.0",
        year=2026,
    )
    reg_service = DeviceRegistrationService(
        repository=in_memory_repo,
        pipeline=pipeline,
        settings=Settings(log_level="WARNING"),
    )
    enrich_service = DeviceIntelligenceService(
        repository=in_memory_repo,
        brand_intelligence=RuleBasedBrandIntelligence(),
        condition_intelligence=BaselineConditionIntelligence(),
        material_intelligence=ProfileBasedMaterialIntelligence(),
        carbon_intelligence=EstimatedBurdenCarbonIntelligence(),
        settings=Settings(log_level="WARNING"),
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=anchor_repo,
        policy=TrustAnchorPolicy.STRICT,
        settings=Settings(log_level="WARNING"),
    )
    return reg_service, enrich_service, trust_service


# ---------------------------------------------------------------------------
# 1. Domain Models & Canonical Serialization
# ---------------------------------------------------------------------------


def test_trust_anchor_model_to_dict() -> None:
    """TrustAnchor model serializes cleanly to JSON dictionary."""
    anchor = TrustAnchor(
        anchor_id="anc-001",
        device_id="DEV-2026-001",
        passport_fingerprint="a" * 64,
        algorithm="sha256",
        anchored_at="2026-08-30T10:00:00+00:00",
        status=TrustAnchorStatus.ANCHORED,
        metadata={"network": "in_memory"},
    )
    d = anchor.to_dict()
    assert d["anchor_id"] == "anc-001"
    assert d["device_id"] == "DEV-2026-001"
    assert d["passport_fingerprint"] == "a" * 64
    assert d["algorithm"] == "sha256"
    assert d["status"] == "ANCHORED"
    assert d["metadata"] == {"network": "in_memory"}


def test_trust_anchor_verification_to_dict() -> None:
    """TrustAnchorVerification model produces serializable dictionary."""
    ver = TrustAnchorVerification(
        device_id="DEV-2026-002",
        status=TrustAnchorStatus.VERIFIED,
        stored_fingerprint="b" * 64,
        current_fingerprint="b" * 64,
        algorithm="sha256",
        verified_at="2026-08-30T10:05:00+00:00",
        message="Match verified",
        details={"checks": 6},
    )
    d = ver.to_dict()
    assert d["status"] == "VERIFIED"
    assert d["stored_fingerprint"] == "b" * 64
    assert d["current_fingerprint"] == "b" * 64
    assert d["details"] == {"checks": 6}


def test_deterministic_trust_payload_and_canonicalization() -> None:
    """Trust anchor payload serialization is deterministic across invocations."""
    p1 = build_trust_payload("DEV-001", "ABCDEF123456", "SHA256")
    p2 = build_trust_payload("DEV-001", "abcdef123456", "sha256")
    assert p1 == p2
    assert p1["algorithm"] == "sha256"

    c1 = canonicalize_trust_payload("DEV-001", "abcdef123456")
    c2 = canonicalize_trust_payload("DEV-001", "abcdef123456")
    assert c1 == c2
    assert isinstance(c1, bytes)
    assert b'"algorithm":"sha256"' in c1
    assert b'"device_id":"DEV-001"' in c1


# ---------------------------------------------------------------------------
# 2. InMemoryTrustAnchorRepository Operations
# ---------------------------------------------------------------------------


def test_in_memory_repository_save_and_retrieve(anchor_repo: InMemoryTrustAnchorRepository) -> None:
    """Repository saves and retrieves anchors properly."""
    assert anchor_repo.count() == 0
    assert not anchor_repo.exists("DEV-100")

    anchor = TrustAnchor(
        anchor_id="anc-100",
        device_id="DEV-100",
        passport_fingerprint="1" * 64,
    )
    saved = anchor_repo.save(anchor)
    assert saved.anchor_id == "anc-100"
    assert anchor_repo.count() == 1
    assert anchor_repo.exists("DEV-100")

    retrieved = anchor_repo.get_by_device_id("DEV-100")
    assert retrieved is not None
    assert retrieved.passport_fingerprint == "1" * 64


def test_in_memory_repository_idempotent_save(anchor_repo: InMemoryTrustAnchorRepository) -> None:
    """Saving an identical fingerprint for the same device returns the existing anchor."""
    anchor1 = TrustAnchor(
        anchor_id="anc-idemp-1",
        device_id="DEV-IDEMP",
        passport_fingerprint="2" * 64,
    )
    saved1 = anchor_repo.save(anchor1)

    anchor2 = TrustAnchor(
        anchor_id="anc-idemp-2",
        device_id="DEV-IDEMP",
        passport_fingerprint="2" * 64,
    )
    saved2 = anchor_repo.save(anchor2)

    assert saved1.anchor_id == saved2.anchor_id
    assert anchor_repo.count() == 1


def test_in_memory_repository_conflict_rejection(anchor_repo: InMemoryTrustAnchorRepository) -> None:
    """Attempting to overwrite an anchored device with a different fingerprint raises AnchorConflictError."""
    anchor1 = TrustAnchor(
        anchor_id="anc-conf-1",
        device_id="DEV-CONFLICT",
        passport_fingerprint="3" * 64,
    )
    anchor_repo.save(anchor1)

    anchor2 = TrustAnchor(
        anchor_id="anc-conf-2",
        device_id="DEV-CONFLICT",
        passport_fingerprint="4" * 64,
    )
    with pytest.raises(AnchorConflictError) as exc_info:
        anchor_repo.save(anchor2)

    assert "Anchor conflict" in str(exc_info.value)
    assert anchor_repo.get_by_device_id("DEV-CONFLICT").passport_fingerprint == "3" * 64


# ---------------------------------------------------------------------------
# 3. DevicePassportTrustService Orchestration & Policies
# ---------------------------------------------------------------------------


def test_anchor_verified_passport_success(trust_services) -> None:
    """A fully verified and enriched device passport can be anchored successfully."""
    reg_service, enrich_service, trust_service = trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-anchor-01")
    device_id = records[0].device_id

    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude 7420", ocr_confidence=0.95)

    anchor, is_new = trust_service.anchor_device_passport(device_id, metadata={"env": "test"})
    assert is_new is True
    assert anchor.device_id == device_id
    assert len(anchor.passport_fingerprint) == 64
    assert anchor.status == TrustAnchorStatus.ANCHORED
    assert anchor.metadata == {"env": "test"}

    # Second call is idempotent
    anchor_dup, is_new_dup = trust_service.anchor_device_passport(device_id)
    assert is_new_dup is False
    assert anchor_dup.anchor_id == anchor.anchor_id


def test_anchor_invalid_passport_rejected(trust_services, in_memory_repo: InMemoryDeviceRepository) -> None:
    """A device with an invalid state/record is rejected with PassportNotAnchorableError."""
    reg_service, _, trust_service = trust_services

    # Construct an invalid record with confidence out of bounds (1.5)
    now = _utc_now()
    bad_record = DeviceRecord(
        device_id="DEV-BAD-RECORD",
        device_type="laptop",
        class_id=0,
        confidence=1.5,  # Out of bounds!
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 100, 100),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-bad",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    in_memory_repo.save(bad_record)
    in_memory_repo.append_event(DeviceEvent("evt-1", bad_record.device_id, DeviceEventType.DEVICE_DETECTED, now))

    with pytest.raises(PassportNotAnchorableError) as exc_info:
        trust_service.anchor_device_passport("DEV-BAD-RECORD")

    assert "status INVALID" in str(exc_info.value)


def test_warning_passport_policy_enforcement(trust_services) -> None:
    """A passport with status WARNING is rejected under STRICT policy and allowed under PERMISSIVE."""
    reg_service, _, _ = trust_services
    anchor_repo = InMemoryTrustAnchorRepository()

    # Create device in REGISTERED state but un-enriched (results in WARNING status)
    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-warn-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)

    # STRICT policy trust service
    strict_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=anchor_repo,
        policy=TrustAnchorPolicy.STRICT,
    )

    with pytest.raises(PassportNotAnchorableError) as exc_info:
        strict_service.anchor_device_passport(device_id)
    assert "STRICT policy" in str(exc_info.value)

    # PERMISSIVE policy trust service
    permissive_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=anchor_repo,
        policy=TrustAnchorPolicy.PERMISSIVE,
    )

    anchor, is_new = permissive_service.anchor_device_passport(device_id)
    assert is_new is True
    assert anchor.device_id == device_id


# ---------------------------------------------------------------------------
# 4. Trust Anchor Verification Logic
# ---------------------------------------------------------------------------


def test_verify_device_anchor_success(trust_services) -> None:
    """Verification returns VERIFIED when current passport matches stored anchor."""
    reg_service, enrich_service, trust_service = trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ver-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 13", ocr_confidence=0.98)

    trust_service.anchor_device_passport(device_id)

    ver = trust_service.verify_device_anchor(device_id)
    assert ver.status == TrustAnchorStatus.VERIFIED
    assert ver.stored_fingerprint == ver.current_fingerprint
    assert "matches anchored trust record" in ver.message


def test_verify_device_anchor_detects_mismatch_on_tamper(trust_services, in_memory_repo: InMemoryDeviceRepository) -> None:
    """Tampering with underlying device data triggers MISMATCH verification status."""
    reg_service, enrich_service, trust_service = trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-tamp-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 13", ocr_confidence=0.98)

    # Anchor the legitimate passport
    trust_service.anchor_device_passport(device_id)

    # Directly tamper with record in storage (e.g. modify bounding box)
    record = in_memory_repo.get(device_id)
    tampered_record = DeviceRecord(
        device_id=record.device_id,
        device_type=record.device_type,
        class_id=record.class_id,
        confidence=record.confidence,
        confidence_state=record.confidence_state,
        bounding_box=(99, 99, 500, 500),  # TAMPERED
        inference_mode=record.inference_mode,
        model_version=record.model_version,
        capture_id=record.capture_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        registration_state=record.registration_state,
        carbon_score=record.carbon_score,
        condition=record.condition,
        metadata=record.metadata,
    )
    in_memory_repo.save(tampered_record)

    ver = trust_service.verify_device_anchor(device_id)
    assert ver.status == TrustAnchorStatus.MISMATCH
    assert ver.stored_fingerprint != ver.current_fingerprint
    assert "MISMATCH" in ver.message


def test_verify_unanchored_device_returns_not_found(trust_services) -> None:
    """Verifying an unanchored registered device returns NOT_FOUND status."""
    reg_service, _, trust_service = trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-unanch-01")
    device_id = records[0].device_id

    ver = trust_service.verify_device_anchor(device_id)
    assert ver.status == TrustAnchorStatus.NOT_FOUND
    assert ver.stored_fingerprint is None
    assert ver.current_fingerprint is not None


def test_operations_on_nonexistent_device_raise_error(trust_services) -> None:
    """Operations on non-existent devices raise DeviceNotFoundError."""
    _, _, trust_service = trust_services

    with pytest.raises(DeviceNotFoundError):
        trust_service.anchor_device_passport("DEV-NONEXISTENT")

    with pytest.raises(DeviceNotFoundError):
        trust_service.get_device_anchor("DEV-NONEXISTENT")

    with pytest.raises(DeviceNotFoundError):
        trust_service.verify_device_anchor("DEV-NONEXISTENT")


def test_get_unanchored_device_raises_anchor_not_found(trust_services) -> None:
    """Retrieving an anchor for an unanchored device raises AnchorNotFoundError."""
    reg_service, _, trust_service = trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-get-01")
    device_id = records[0].device_id

    with pytest.raises(AnchorNotFoundError):
        trust_service.get_device_anchor(device_id)


# ---------------------------------------------------------------------------
# 5. Read-Only Boundaries & Immutability Guarantees
# ---------------------------------------------------------------------------


def test_verify_device_anchor_is_strictly_read_only(trust_services, in_memory_repo: InMemoryDeviceRepository) -> None:
    """verify_device_anchor guarantees zero record mutations, zero anchor writes, and zero audit event creations."""
    reg_service, enrich_service, trust_service = trust_services

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ro-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 13", ocr_confidence=0.98)
    trust_service.anchor_device_passport(device_id)

    record_before = in_memory_repo.get(device_id).to_dict()
    events_count_before = in_memory_repo.count_events(device_id)
    anchor_before = trust_service.get_device_anchor(device_id).to_dict()

    # Execute verification 5 times
    for _ in range(5):
        res = trust_service.verify_device_anchor(device_id)
        assert res.status == TrustAnchorStatus.VERIFIED

    record_after = in_memory_repo.get(device_id).to_dict()
    events_count_after = in_memory_repo.count_events(device_id)
    anchor_after = trust_service.get_device_anchor(device_id).to_dict()

    assert record_before == record_after
    assert events_count_before == events_count_after
    assert anchor_before == anchor_after


# ---------------------------------------------------------------------------
# 6. REST API Endpoints Integration
# ---------------------------------------------------------------------------


def test_api_anchor_flow_and_endpoints() -> None:
    """Test POST /anchor, GET /anchor, and GET /anchor/verify via FastAPI TestClient."""
    app = create_app()
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.94, bounding_box=(10, 10, 150, 150))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        # 1. Register, confirm, finalize, enrich
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("laptop.png", _make_test_image_bytes(), "image/png"))],
            data={"capture_id": "cap-api-anc-01"},
            headers={"X-Request-ID": "req-api-anc-01"},
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
            json={"metadata": {"anchored_by": "test_agent"}},
            headers={"X-Request-ID": "req-anchor-post-01"},
        )
        assert anc_resp.status_code == 201
        anc_data = anc_resp.json()
        assert anc_data["success"] is True
        assert anc_data["is_new"] is True
        assert anc_data["request_id"] == "req-anchor-post-01"
        assert anc_data["anchor"]["device_id"] == device_id
        assert len(anc_data["anchor"]["passport_fingerprint"]) == 64
        assert anc_data["anchor"]["status"] == "ANCHORED"
        assert anc_data["anchor"]["metadata"] == {"anchored_by": "test_agent"}

        # 3. POST duplicate -> HTTP 200 OK (idempotent)
        anc_dup = client.post(f"/devices/{device_id}/passport/anchor")
        assert anc_dup.status_code == 200
        assert anc_dup.json()["is_new"] is False

        # 4. GET /devices/{id}/passport/anchor -> HTTP 200 OK
        get_resp = client.get(
            f"/devices/{device_id}/passport/anchor",
            headers={"X-Request-ID": "req-anchor-get-01"},
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["anchor"]["device_id"] == device_id
        assert get_data["anchor"]["passport_fingerprint"] == anc_data["anchor"]["passport_fingerprint"]

        # 5. GET /devices/{id}/passport/anchor/verify -> HTTP 200 OK
        ver_resp = client.get(
            f"/devices/{device_id}/passport/anchor/verify",
            headers={"X-Request-ID": "req-anchor-ver-01"},
        )
        assert ver_resp.status_code == 200
        ver_data = ver_resp.json()
        assert ver_data["success"] is True
        assert ver_data["verification"]["status"] == "VERIFIED"
        assert ver_data["verification"]["stored_fingerprint"] == anc_data["anchor"]["passport_fingerprint"]
        assert ver_data["verification"]["current_fingerprint"] == anc_data["anchor"]["passport_fingerprint"]

        # 6. GET unanchored device returns 404
        unanch_resp = client.get("/devices/DEV-NONEXISTENT/passport/anchor")
        assert unanch_resp.status_code == 404

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_api_post_anchor_invalid_passport_returns_400() -> None:
    """POST /devices/{id}/passport/anchor on an unfinalized/invalid passport returns HTTP 400."""
    app = create_app()
    detector = _FakeDetector([
        Detection(label="camera", confidence=0.91, bounding_box=(10, 10, 80, 80))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        # Register device but leave in DETECTED state
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("camera.png", _make_test_image_bytes(), "image/png"))],
            data={"capture_id": "cap-api-anc-invalid"},
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]

        # Attempt to anchor DETECTED device (STRICT policy rejects WARNING/un-enriched)
        anc_resp = client.post(f"/devices/{device_id}/passport/anchor")
        assert anc_resp.status_code == 400
        assert anc_resp.json()["error"]["code"] == "PASSPORT_NOT_ANCHORABLE"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_api_get_anchor_nonexistent_device_returns_404() -> None:
    """GET /devices/{id}/passport/anchor for nonexistent device returns HTTP 404."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/devices/DEV-DOES-NOT-EXIST/passport/anchor")
        assert resp.status_code == 404


def test_api_verify_anchor_nonexistent_device_returns_404() -> None:
    """GET /devices/{id}/passport/anchor/verify for nonexistent device returns HTTP 404."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/devices/DEV-DOES-NOT-EXIST/passport/anchor/verify")
        assert resp.status_code == 404


def test_trust_anchor_repository_clear(anchor_repo: InMemoryTrustAnchorRepository) -> None:
    """anchor_repo.clear() removes all stored anchors."""
    anchor = TrustAnchor(
        anchor_id="anc-clr-1",
        device_id="DEV-CLR-1",
        passport_fingerprint="c" * 64,
    )
    anchor_repo.save(anchor)
    assert anchor_repo.count() == 1

    anchor_repo.clear()
    assert anchor_repo.count() == 0
    assert not anchor_repo.exists("DEV-CLR-1")
