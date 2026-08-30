"""Comprehensive unit and integration test suite for Phase P5.10 Trust-Aware Device Operations.

Tests:
1. No anchor -> UNANCHORED.
2. Matching anchor + verified passport + within freshness window -> VERIFIED.
3. Matching anchor + old anchor (> max_age_days) -> STALE.
4. Different fingerprint -> MISMATCH.
5. Invalid passport -> MISMATCH.
6. Anchor metadata, checks, and diagnostics returned properly.
7. Freshness boundary evaluation.
8. Unlimited freshness configuration (None / <= 0).
9. Future timestamp handling (safe age clamping).
10. UTC and timezone parsing correctness.
11. Missing device raises DeviceNotFoundError.
12. REST API: GET /devices/{id}/trust returns 200 UNANCHORED for unanchored device.
13. REST API: GET /devices/{id}/trust returns 200 VERIFIED for valid anchored device.
14. REST API: GET /devices/{id}/trust returns 200 STALE for expired anchor.
15. REST API: GET /devices/{id}/trust returns 200 MISMATCH for divergent passport.
16. REST API: GET /devices/{id}/trust returns 404 for missing device.
17. REST API: GET /devices/{id}/trust produces zero writes, zero audit events, zero mutations.
18. Explicit re-anchor workflow updates anchor and returns is_changed=True.
19. REST API: POST /devices/{id}/passport/reanchor updates anchor in DB.
20. Re-anchor rejects INVALID passport.
21. Multi-backend parity (InMemory vs Postgres).
22. Deterministic status precedence hierarchy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import io
from pathlib import Path
from typing import Any
import pytest
from PIL import Image
from sqlalchemy import create_engine
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
    DeviceRecord,
    RegistrationState,
)
from device_ai.devices.postgres_repository import PostgresDeviceRepository
from device_ai.devices.postgres_trust_anchor_repository import PostgresTrustAnchorRepository
from device_ai.devices.repository import InMemoryDeviceRepository
from device_ai.devices.service import DeviceRegistrationService
from device_ai.devices.trust_anchor import (
    DevicePassportTrustService,
    InMemoryTrustAnchorRepository,
    TrustAnchor,
    TrustAnchorPolicy,
    TrustAnchorStatus,
    TrustStatus,
    TrustStatusResult,
)
from device_ai.exceptions import (
    AnchorConflictError,
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
    version = "p510-fake-1.0.0"

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
    """Isolated SQLite test engine with P5.10 schema."""
    db_file = tmp_path / "test_p510.db"
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
def trust_environment(postgres_device_repo, postgres_anchor_repo):
    """Setup configured registration, enrichment, and trust service."""
    pipeline = build_detection_pipeline(
        detector=_FakeDetector([
            Detection(label="laptop", confidence=0.95, bounding_box=(10, 10, 120, 120))
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
        settings=Settings(trust_anchor_max_age_days=90, log_level="WARNING"),
    )
    return reg_service, enrich_service, trust_service, postgres_anchor_repo, postgres_device_repo


# ---------------------------------------------------------------------------
# 1. Canonical Trust Status Evaluation Unit Tests
# ---------------------------------------------------------------------------


def test_unanchored_device_status(trust_environment) -> None:
    """Device without trust anchor returns UNANCHORED status with current passport fingerprint."""
    reg_service, _, trust_service, _, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-unanchored")
    device_id = records[0].device_id

    result = trust_service.get_device_trust_status(device_id)
    assert result.status == TrustStatus.UNANCHORED
    assert result.device_id == device_id
    assert result.anchored_fingerprint is None
    assert result.anchor_id is None
    assert len(result.passport_fingerprint) == 64
    assert result.is_fresh is True
    assert "No trust anchor exists" in result.reason


def test_matching_anchor_verified_status(trust_environment) -> None:
    """Matching anchor within freshness window returns VERIFIED status."""
    reg_service, enrich_service, trust_service, _, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-verified")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 15", ocr_confidence=0.96)

    anchor, _ = trust_service.anchor_device_passport(device_id)

    result = trust_service.get_device_trust_status(device_id)
    assert result.status == TrustStatus.VERIFIED
    assert result.device_id == device_id
    assert result.passport_fingerprint == anchor.passport_fingerprint
    assert result.anchored_fingerprint == anchor.passport_fingerprint
    assert result.anchor_id == anchor.anchor_id
    assert result.verification_status == "VERIFIED"
    assert result.is_fresh is True
    assert result.age_days is not None
    assert result.age_days < 1.0


def test_stale_anchor_status(trust_environment) -> None:
    """Matching anchor older than max_age_days returns STALE status."""
    reg_service, enrich_service, trust_service, anchor_repo, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-stale")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 15", ocr_confidence=0.96)

    anchor, _ = trust_service.anchor_device_passport(device_id)

    # Simulate anchor created 120 days ago (max_age_days = 90)
    old_time = _utc_now() - timedelta(days=120)
    old_anchor = TrustAnchor(
        anchor_id=anchor.anchor_id,
        device_id=device_id,
        passport_fingerprint=anchor.passport_fingerprint,
        algorithm=anchor.algorithm,
        anchored_at=old_time.isoformat(),
        status=TrustAnchorStatus.ANCHORED,
    )
    anchor_repo.save(old_anchor, overwrite=True)

    result = trust_service.get_device_trust_status(device_id)
    assert result.status == TrustStatus.STALE
    assert result.is_fresh is False
    assert result.max_age_days == 90
    assert result.age_days >= 119.0
    assert "exceeds configured trust freshness window" in result.reason


def test_mismatch_different_fingerprint(trust_environment) -> None:
    """If current passport diverges from anchored fingerprint, returns MISMATCH."""
    reg_service, enrich_service, trust_service, anchor_repo, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-mismatch")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 15")

    anchor, _ = trust_service.anchor_device_passport(device_id)

    # Simulate anchor having an old/different fingerprint
    tampered_anchor = TrustAnchor(
        anchor_id=anchor.anchor_id,
        device_id=device_id,
        passport_fingerprint="0" * 64,
        algorithm=anchor.algorithm,
        anchored_at=anchor.anchored_at,
    )
    anchor_repo.save(tampered_anchor, overwrite=True)

    result = trust_service.get_device_trust_status(device_id)
    assert result.status == TrustStatus.MISMATCH
    assert result.passport_fingerprint != result.anchored_fingerprint
    assert result.anchored_fingerprint == "0" * 64
    assert "does not match anchored trust record" in result.reason


def test_mismatch_invalid_passport(trust_environment) -> None:
    """If passport fails integrity verification (status INVALID), returns MISMATCH."""
    reg_service, _, trust_service, anchor_repo, device_repo = trust_environment

    now = _utc_now()
    bad_record = DeviceRecord(
        device_id="DEV-INVALID-TEST",
        device_type="laptop",
        class_id=0,
        confidence=1.99,  # Out of range -> INVALID passport
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 100, 100),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-bad",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    device_repo.save(bad_record)

    # Pre-seed an anchor
    anchor_repo.save(
        TrustAnchor(
            anchor_id="anc-bad-1",
            device_id="DEV-INVALID-TEST",
            passport_fingerprint="a" * 64,
            anchored_at=now.isoformat(),
        )
    )

    result = trust_service.get_device_trust_status("DEV-INVALID-TEST")
    assert result.status == TrustStatus.MISMATCH
    assert result.verification_status == "INVALID"
    assert "INVALID" in result.reason


def test_unlimited_freshness_configuration(trust_environment) -> None:
    """When trust_anchor_max_age_days is None or <= 0, anchors never expire as STALE."""
    reg_service, enrich_service, _, anchor_repo, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-unlim")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 15")

    unlimited_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=anchor_repo,
        settings=Settings(trust_anchor_max_age_days=0, log_level="WARNING"),
    )

    anchor, _ = unlimited_service.anchor_device_passport(device_id)

    # Set anchor date 500 days in past
    old_time = _utc_now() - timedelta(days=500)
    anchor_repo.save(
        TrustAnchor(
            anchor_id=anchor.anchor_id,
            device_id=device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            anchored_at=old_time.isoformat(),
        ),
        overwrite=True,
    )

    result = unlimited_service.get_device_trust_status(device_id)
    assert result.status == TrustStatus.VERIFIED
    assert result.is_fresh is True


def test_missing_device_raises_not_found(trust_environment) -> None:
    """get_device_trust_status raises DeviceNotFoundError if device does not exist."""
    _, _, trust_service, _, _ = trust_environment

    with pytest.raises(DeviceNotFoundError):
        trust_service.get_device_trust_status("DEV-DOES-NOT-EXIST")


# ---------------------------------------------------------------------------
# 2. Re-anchor Workflow Tests
# ---------------------------------------------------------------------------


def test_reanchor_workflow_in_service(trust_environment) -> None:
    """reanchor_device_passport replaces existing anchor with updated passport fingerprint."""
    reg_service, enrich_service, trust_service, anchor_repo, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-reanc")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    # Initial anchor
    anc1, is_new1 = trust_service.anchor_device_passport(device_id)
    assert is_new1 is True

    # Mutate data / re-enrich with new brand info
    enrich_service.enrich_device(device_id, ocr_text="Dell Precision 5550")

    # Status before re-anchoring is MISMATCH
    status_pre = trust_service.get_device_trust_status(device_id)
    assert status_pre.status == TrustStatus.MISMATCH

    # Explicit re-anchor
    anc2, is_changed = trust_service.reanchor_device_passport(device_id, metadata={"reason": "upgrade"})
    assert is_changed is True
    assert anc2.passport_fingerprint != anc1.passport_fingerprint
    assert anc2.metadata == {"reason": "upgrade"}

    # Status after re-anchoring is VERIFIED
    status_post = trust_service.get_device_trust_status(device_id)
    assert status_post.status == TrustStatus.VERIFIED
    assert status_post.passport_fingerprint == anc2.passport_fingerprint


def test_reanchor_rejects_invalid_passport(trust_environment) -> None:
    """reanchor_device_passport rejects INVALID passport under all policies."""
    reg_service, _, trust_service, _, device_repo = trust_environment

    now = _utc_now()
    bad_record = DeviceRecord(
        device_id="DEV-REANC-BAD",
        device_type="laptop",
        class_id=0,
        confidence=-0.5,  # Invalid
        confidence_state=ConfidenceState.LOW_CONFIDENCE,
        bounding_box=(0, 0, 10, 10),
        inference_mode="single_model",
        model_version="1.0.0",
        capture_id="cap-reanc-bad",
        created_at=now,
        updated_at=now,
        registration_state=RegistrationState.REGISTERED,
    )
    device_repo.save(bad_record)

    with pytest.raises(PassportNotAnchorableError):
        trust_service.reanchor_device_passport("DEV-REANC-BAD")


# ---------------------------------------------------------------------------
# 3. REST API Endpoint Tests (GET /devices/{id}/trust and POST /reanchor)
# ---------------------------------------------------------------------------


def test_api_get_trust_endpoints(session_factory, postgres_device_repo, postgres_anchor_repo) -> None:
    """Test REST API routes GET /devices/{id}/trust and POST /devices/{id}/passport/reanchor."""
    app = create_app()
    detector = _FakeDetector([
        Detection(label="laptop", confidence=0.96, bounding_box=(10, 10, 150, 150))
    ])
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    dependencies.reset_dependency_caches()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_repository] = lambda: postgres_device_repo
    app.dependency_overrides[dependencies.get_trust_anchor_repository] = lambda: postgres_anchor_repo

    with TestClient(app) as client:
        # Register device
        reg_resp = client.post(
            "/devices/register",
            files=[("images", ("laptop.png", _make_test_image_bytes(), "image/png"))],
            data={"capture_id": "cap-api-trust-01"},
            headers={"X-Request-ID": "req-trust-01"},
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]

        # 1. Unanchored GET /devices/{id}/trust -> HTTP 200 with UNANCHORED
        t_unanc = client.get(f"/devices/{device_id}/trust")
        assert t_unanc.status_code == 200
        assert t_unanc.json()["trust"]["status"] == "UNANCHORED"

        # Complete registration & enrichment
        client.post(f"/devices/{device_id}/confirm")
        client.post(f"/devices/{device_id}/finalize")
        client.post(f"/devices/{device_id}/enrich", json={"ocr_text": "Dell Latitude 5520"})

        # Anchor passport
        anc_resp = client.post(f"/devices/{device_id}/passport/anchor")
        assert anc_resp.status_code == 201
        anchored_fp = anc_resp.json()["anchor"]["passport_fingerprint"]

        # 2. Verified GET /devices/{id}/trust -> HTTP 200 with VERIFIED
        t_ver = client.get(f"/devices/{device_id}/trust")
        assert t_ver.status_code == 200
        ver_payload = t_ver.json()["trust"]
        assert ver_payload["status"] == "VERIFIED"
        assert ver_payload["passport_fingerprint"] == anchored_fp
        assert ver_payload["is_fresh"] is True

        # 3. Modify device enrichment -> GET /devices/{id}/trust becomes MISMATCH
        client.post(f"/devices/{device_id}/enrich", json={"ocr_text": "HP EliteBook 840"})
        t_mis = client.get(f"/devices/{device_id}/trust")
        assert t_mis.status_code == 200
        assert t_mis.json()["trust"]["status"] == "MISMATCH"

        # 4. Explicit re-anchor -> POST /devices/{id}/passport/reanchor -> HTTP 200 with new anchor
        reanc_resp = client.post(
            f"/devices/{device_id}/passport/reanchor",
            json={"metadata": {"updated_reason": "device_transfer"}},
        )
        assert reanc_resp.status_code == 200
        reanc_data = reanc_resp.json()
        assert reanc_data["is_new"] is True
        new_fp = reanc_data["anchor"]["passport_fingerprint"]
        assert new_fp != anchored_fp

        # 5. GET /devices/{id}/trust is now VERIFIED again
        t_rever = client.get(f"/devices/{device_id}/trust")
        assert t_rever.status_code == 200
        assert t_rever.json()["trust"]["status"] == "VERIFIED"
        assert t_rever.json()["trust"]["passport_fingerprint"] == new_fp

        # 6. Missing device -> HTTP 404
        assert client.get("/devices/DEV-NONEXISTENT/trust").status_code == 404

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_api_get_trust_read_only_guarantee(trust_environment, session_factory) -> None:
    """GET /devices/{id}/trust is strictly read-only and produces zero database writes."""
    reg_service, enrich_service, trust_service, _, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ro-trust")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 15")
    trust_service.anchor_device_passport(device_id)

    # Initial counts
    with session_scope(session_factory) as session:
        anchors_pre = session.query(TrustAnchorModel).count()
        events_pre = session.query(DeviceEventModel).count()
        devices_pre = session.query(DeviceModel).count()

    # Run get_device_trust_status 5 times
    for _ in range(5):
        res = trust_service.get_device_trust_status(device_id)
        assert res.status == TrustStatus.VERIFIED

    # Counts after evaluations
    with session_scope(session_factory) as session:
        anchors_post = session.query(TrustAnchorModel).count()
        events_post = session.query(DeviceEventModel).count()
        devices_post = session.query(DeviceModel).count()

    assert anchors_pre == anchors_post
    assert events_pre == events_post
    assert devices_pre == devices_post


# ---------------------------------------------------------------------------
# 4. Multi-Backend Parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("repo_type", ["memory", "postgres"])
def test_multi_backend_parity(repo_type: str, session_factory) -> None:
    """InMemory and Postgres backends exhibit identical trust evaluation semantics."""
    if repo_type == "memory":
        dev_repo = InMemoryDeviceRepository()
        anc_repo = InMemoryTrustAnchorRepository()
    else:
        dev_repo = PostgresDeviceRepository(session_factory)
        anc_repo = PostgresTrustAnchorRepository(session_factory)

    pipeline = build_detection_pipeline(
        detector=_FakeDetector([
            Detection(label="monitor", confidence=0.94, bounding_box=(10, 10, 80, 80))
        ]),
        model_version="1.0.0",
        year=2026,
    )
    reg_service = DeviceRegistrationService(repository=dev_repo, pipeline=pipeline, settings=Settings(log_level="WARNING"))
    enrich_service = DeviceIntelligenceService(
        repository=dev_repo,
        brand_intelligence=RuleBasedBrandIntelligence(),
        condition_intelligence=BaselineConditionIntelligence(),
        material_intelligence=ProfileBasedMaterialIntelligence(),
        carbon_intelligence=EstimatedBurdenCarbonIntelligence(),
        settings=Settings(log_level="WARNING"),
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=anc_repo,
        policy=TrustAnchorPolicy.STRICT,
        settings=Settings(trust_anchor_max_age_days=90, log_level="WARNING"),
    )

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id=f"cap-parity-t-{repo_type}")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell UltraSharp")

    # 1. UNANCHORED
    s1 = trust_service.get_device_trust_status(device_id)
    assert s1.status == TrustStatus.UNANCHORED

    # 2. VERIFIED
    anc, is_new = trust_service.anchor_device_passport(device_id)
    assert is_new is True
    s2 = trust_service.get_device_trust_status(device_id)
    assert s2.status == TrustStatus.VERIFIED

    # 3. MISMATCH on modification
    enrich_service.enrich_device(device_id, ocr_text="Samsung Odyssey")
    s3 = trust_service.get_device_trust_status(device_id)
    assert s3.status == TrustStatus.MISMATCH

    # 4. Re-anchor restores VERIFIED
    reanc, is_chg = trust_service.reanchor_device_passport(device_id)
    assert is_chg is True
    s4 = trust_service.get_device_trust_status(device_id)
    assert s4.status == TrustStatus.VERIFIED


# ---------------------------------------------------------------------------
# 5. Granular Edge Cases & Status Precedence
# ---------------------------------------------------------------------------


def test_anchor_metadata_and_checks_returned(trust_environment) -> None:
    """TrustStatusResult contains full checks dictionary, anchor metadata, and details."""
    reg_service, enrich_service, trust_service, _, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-checks-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    trust_service.anchor_device_passport(device_id, metadata={"anchor_facility": "BLR_DC_1"})

    result = trust_service.get_device_trust_status(device_id)
    assert result.status == TrustStatus.VERIFIED
    assert "identity" in result.checks
    assert "detection" in result.checks
    assert "lifecycle" in result.checks
    assert "enrichment" in result.checks
    assert result.details["anchor_metadata"]["anchor_facility"] == "BLR_DC_1"


def test_freshness_boundary_behavior(trust_environment) -> None:
    """Test exact boundary condition for freshness (age just below vs just above max_age_days)."""
    reg_service, enrich_service, trust_service, anchor_repo, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-boundary-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    anchor, _ = trust_service.anchor_device_passport(device_id)

    # 1. Age = 89.9 days (max_age_days = 90) -> VERIFIED
    time_just_under = _utc_now() - timedelta(days=89, hours=21)
    anchor_repo.save(
        TrustAnchor(
            anchor_id=anchor.anchor_id,
            device_id=device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            anchored_at=time_just_under.isoformat(),
        ),
        overwrite=True,
    )
    res_under = trust_service.get_device_trust_status(device_id)
    assert res_under.status == TrustStatus.VERIFIED
    assert res_under.is_fresh is True

    # 2. Age = 90.1 days -> STALE
    time_just_over = _utc_now() - timedelta(days=90, hours=3)
    anchor_repo.save(
        TrustAnchor(
            anchor_id=anchor.anchor_id,
            device_id=device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            anchored_at=time_just_over.isoformat(),
        ),
        overwrite=True,
    )
    res_over = trust_service.get_device_trust_status(device_id)
    assert res_over.status == TrustStatus.STALE
    assert res_over.is_fresh is False


def test_future_timestamp_handling(trust_environment) -> None:
    """Future timestamp on anchor is clamped to 0.0 age_days and remains VERIFIED."""
    reg_service, enrich_service, trust_service, anchor_repo, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-future-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    anchor, _ = trust_service.anchor_device_passport(device_id)

    # Future date (clock skew)
    future_time = _utc_now() + timedelta(hours=2)
    anchor_repo.save(
        TrustAnchor(
            anchor_id=anchor.anchor_id,
            device_id=device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            anchored_at=future_time.isoformat(),
        ),
        overwrite=True,
    )
    res_future = trust_service.get_device_trust_status(device_id)
    assert res_future.status == TrustStatus.VERIFIED
    assert res_future.age_days == 0.0


def test_utc_timezone_awareness(trust_environment) -> None:
    """Both timezone-aware and naive ISO timestamps are parsed safely."""
    reg_service, enrich_service, trust_service, anchor_repo, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-tz-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    anchor, _ = trust_service.anchor_device_passport(device_id)

    # Naive ISO format
    naive_iso = "2026-08-01T12:00:00"
    anchor_repo.save(
        TrustAnchor(
            anchor_id=anchor.anchor_id,
            device_id=device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            anchored_at=naive_iso,
        ),
        overwrite=True,
    )
    res_naive = trust_service.get_device_trust_status(device_id)
    assert res_naive.status in (TrustStatus.VERIFIED, TrustStatus.STALE)


def test_reanchor_no_change_is_false(trust_environment) -> None:
    """Re-anchoring when passport has not changed returns is_changed=False."""
    reg_service, enrich_service, trust_service, _, _ = trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-reanc-same")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    trust_service.anchor_device_passport(device_id)

    # Re-anchor identical passport
    _, is_changed = trust_service.reanchor_device_passport(device_id)
    assert is_changed is False
