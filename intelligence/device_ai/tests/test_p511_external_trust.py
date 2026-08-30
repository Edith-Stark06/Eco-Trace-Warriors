"""Test suite for Phase P5.11: External / Blockchain Trust Integration.

Covers:
1. Local verified passport can be externally anchored.
2. Unverified/invalid passport cannot be anchored externally.
3. Missing local anchor is rejected before external anchoring.
4. Identical external anchor is idempotent.
5. Conflicting external anchor is rejected with conflict error.
6. External anchor retrieval works.
7. External fingerprint verification works (VERIFIED).
8. External fingerprint mismatch is detected (MISMATCH).
9. Full trust comparison matrix (local vs external).
10. External provider unavailable handled safely (Fabric offline).
11. GET verification is strictly read-only (zero writes).
12. GET verification emits zero lifecycle events.
13. Device ID and algorithm mismatch detection.
14. Transaction ID and metadata preservation.
15. InMemory provider deterministic behavior.
16. Multi-backend parity (InMemory vs PostgreSQL).
17. Alembic migration upgrade/downgrade for external_trust_anchors.
18. REST API endpoints (POST /external-anchor, GET /external-anchor, GET /verify, GET /trust/full).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
import uuid

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings
from device_ai.database.models import (
    Base,
    DeviceEventModel,
    DeviceModel,
    ExternalTrustAnchorModel,
    TrustAnchorModel,
)
from device_ai.database.session import session_scope
from device_ai.devices.brand import RuleBasedBrandIntelligence
from device_ai.devices.carbon import EstimatedBurdenCarbonIntelligence
from device_ai.devices.condition import BaselineConditionIntelligence
from device_ai.devices.enrichment_service import DeviceIntelligenceService
from device_ai.devices.external_trust import (
    ExternalTrustAnchor,
    ExternalTrustLedger,
    ExternalTrustStatus,
    ExternalTrustVerificationResult,
    FabricExternalTrustLedger,
    FullTrustComparisonResult,
    InMemoryExternalTrustLedger,
    compute_overall_trust_status,
)
from device_ai.devices.material import ProfileBasedMaterialIntelligence
from device_ai.devices.models import DeviceEventType
from device_ai.devices.passport_verification import (
    PassportVerificationResult,
    VerificationStatus,
    fingerprint_passport,
)
from device_ai.devices.postgres_external_trust_repository import (
    PostgresExternalTrustAnchorRepository,
)
from device_ai.devices.postgres_repository import PostgresDeviceRepository
from device_ai.devices.postgres_trust_anchor_repository import (
    PostgresTrustAnchorRepository,
)
from device_ai.devices.repository import InMemoryDeviceRepository
from device_ai.devices.service import DeviceRegistrationService
from device_ai.devices.trust_anchor import (
    DevicePassportTrustService,
    InMemoryTrustAnchorRepository,
    TrustAnchor,
    TrustAnchorPolicy,
    TrustAnchorStatus,
    TrustStatus,
)
from device_ai.exceptions import (
    ExternalAnchorConflictError,
    ExternalAnchorNotFoundError,
    ExternalLedgerUnavailableError,
    PassportNotAnchorableError,
)
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.predictor import Detection, Detector
from device_ai.preprocessing.image_loader import LoadedImage
import io
from PIL import Image


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


from device_ai.inference.predictor import Detection, DetectionResult, Detector


class _FakeDetector(Detector):
    version = "p511-fake-1.0.0"

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


from device_ai.database.session import get_session_factory
from pathlib import Path


@pytest.fixture
def sqlite_engine(tmp_path: Path):
    db_file = tmp_path / "test_p511_suite.db"
    engine = create_engine(f"sqlite:///{db_file}", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine):
    return get_session_factory(sqlite_engine)


@pytest.fixture
def full_trust_environment(session_factory):
    dev_repo = PostgresDeviceRepository(session_factory)
    local_anc_repo = PostgresTrustAnchorRepository(session_factory)
    ext_anc_repo = PostgresExternalTrustAnchorRepository(session_factory)
    ext_ledger = InMemoryExternalTrustLedger(network="ecotrace-channel", provider="memory")

    pipeline = build_detection_pipeline(
        detector=_FakeDetector([
            Detection(label="laptop", confidence=0.95, bounding_box=(20, 20, 200, 200))
        ]),
        model_version="1.0.0",
        year=2026,
    )
    settings = Settings(
        trust_anchor_backend="postgres",
        external_trust_backend="memory",
        external_trust_network="ecotrace-channel",
        trust_anchor_max_age_days=90,
        log_level="WARNING",
    )
    reg_service = DeviceRegistrationService(repository=dev_repo, pipeline=pipeline, settings=settings)
    enrich_service = DeviceIntelligenceService(
        repository=dev_repo,
        brand_intelligence=RuleBasedBrandIntelligence(),
        condition_intelligence=BaselineConditionIntelligence(),
        material_intelligence=ProfileBasedMaterialIntelligence(),
        carbon_intelligence=EstimatedBurdenCarbonIntelligence(),
        settings=settings,
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=local_anc_repo,
        policy=TrustAnchorPolicy.STRICT,
        settings=settings,
        external_ledger=ext_ledger,
        external_repository=ext_anc_repo,
    )

    return reg_service, enrich_service, trust_service, local_anc_repo, ext_ledger, ext_anc_repo


# ---------------------------------------------------------------------------
# 1. External Anchoring Workflow & Invariants
# ---------------------------------------------------------------------------


def test_external_anchor_success(full_trust_environment) -> None:
    """A locally verified device passport can be externally anchored."""
    reg_service, enrich_service, trust_service, _, ext_ledger, ext_repo = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ext-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 13")

    # Local anchor
    trust_service.anchor_device_passport(device_id)

    # External anchor
    ext_anchor, is_new = trust_service.anchor_device_passport_externally(
        device_id=device_id,
        metadata={"facility_id": "FAC-BLR-01"},
    )

    assert is_new is True
    assert ext_anchor.device_id == device_id
    assert ext_anchor.passport_fingerprint is not None
    assert ext_anchor.transaction_id.startswith("tx-")
    assert ext_anchor.network == "ecotrace-channel"

    # Verified on ledger
    on_ledger = ext_ledger.get_anchor(device_id)
    assert on_ledger is not None
    assert on_ledger.passport_fingerprint == ext_anchor.passport_fingerprint

    # Mirrored in PostgreSQL repository
    in_db = ext_repo.get_by_device_id(device_id)
    assert in_db is not None
    assert in_db.passport_fingerprint == ext_anchor.passport_fingerprint


def test_external_anchor_fails_without_local_anchor(full_trust_environment) -> None:
    """Device without a local operational trust anchor cannot be anchored externally."""
    reg_service, enrich_service, trust_service, _, _, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ext-unanc")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Lenovo ThinkPad")

    with pytest.raises(PassportNotAnchorableError) as exc_info:
        trust_service.anchor_device_passport_externally(device_id)
    assert "no local trust anchor" in str(exc_info.value)


def test_external_anchor_fails_on_mismatch_state(full_trust_environment) -> None:
    """Device whose passport diverged from local anchor (MISMATCH) cannot be anchored externally."""
    reg_service, enrich_service, trust_service, _, _, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ext-mismatch")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    trust_service.anchor_device_passport(device_id)

    # Mutate enrichment to create local MISMATCH
    enrich_service.enrich_device(device_id, ocr_text="HP EliteBook")

    with pytest.raises(PassportNotAnchorableError) as exc_info:
        trust_service.anchor_device_passport_externally(device_id)
    assert "MISMATCH" in str(exc_info.value)


def test_external_anchor_idempotency(full_trust_environment) -> None:
    """Re-submitting identical passport to external anchor returns is_new=False without error."""
    reg_service, enrich_service, trust_service, _, _, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ext-idem")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    trust_service.anchor_device_passport(device_id)

    a1, is_new1 = trust_service.anchor_device_passport_externally(device_id)
    assert is_new1 is True

    a2, is_new2 = trust_service.anchor_device_passport_externally(device_id)
    assert is_new2 is False
    assert a1.passport_fingerprint == a2.passport_fingerprint


def test_external_anchor_conflict_detection(full_trust_environment) -> None:
    """Attempting to anchor a conflicting fingerprint directly raises ExternalAnchorConflictError."""
    _, _, _, _, ext_ledger, _ = full_trust_environment

    anchor1 = ExternalTrustAnchor(
        external_anchor_id="ext-1",
        device_id="DEV-CONFLICT-01",
        passport_fingerprint="abc123hash",
    )
    ext_ledger.anchor(anchor1)

    anchor2 = ExternalTrustAnchor(
        external_anchor_id="ext-2",
        device_id="DEV-CONFLICT-01",
        passport_fingerprint="def456hash",
    )

    with pytest.raises(ExternalAnchorConflictError):
        ext_ledger.anchor(anchor2, overwrite=False)

    # Overwrite=True succeeds
    saved = ext_ledger.anchor(anchor2, overwrite=True)
    assert saved.passport_fingerprint == "def456hash"


# ---------------------------------------------------------------------------
# 2. External Verification & Full Trust Synthesis
# ---------------------------------------------------------------------------


def test_verify_device_passport_external_success(full_trust_environment) -> None:
    """verify_device_passport_external correctly verifies matching on-chain record."""
    reg_service, enrich_service, trust_service, _, _, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ext-ver")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Precision")

    trust_service.anchor_device_passport(device_id)
    trust_service.anchor_device_passport_externally(device_id)

    res = trust_service.verify_device_passport_external(device_id)
    assert res.status == ExternalTrustStatus.VERIFIED
    assert res.stored_fingerprint == res.current_fingerprint
    assert res.provider == "memory"
    assert res.network == "ecotrace-channel"


def test_verify_device_passport_external_not_anchored(full_trust_environment) -> None:
    """verify_device_passport_external returns NOT_ANCHORED when external anchor is missing."""
    reg_service, enrich_service, trust_service, _, _, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ext-notanc")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    res = trust_service.verify_device_passport_external(device_id)
    assert res.status == ExternalTrustStatus.NOT_ANCHORED


def test_verify_device_passport_external_mismatch(full_trust_environment) -> None:
    """External mismatch is detected when ledger fingerprint differs from current passport."""
    reg_service, enrich_service, trust_service, _, ext_ledger, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ext-tamper")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")

    trust_service.anchor_device_passport(device_id)
    trust_service.anchor_device_passport_externally(device_id)

    # Manually tamper with external ledger
    ext_ledger.anchor(
        ExternalTrustAnchor(
            external_anchor_id="tampered-1",
            device_id=device_id,
            passport_fingerprint="0000000000000000000000000000000000000000000000000000000000000000",
        ),
        overwrite=True,
    )

    res = trust_service.verify_device_passport_external(device_id)
    assert res.status == ExternalTrustStatus.MISMATCH


def test_full_trust_comparison_synthesis(full_trust_environment) -> None:
    """get_full_device_trust_status returns synthesized comparison of local and external trust."""
    reg_service, enrich_service, trust_service, _, _, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-full-trust")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell XPS 15")

    # 1. Unanchored
    full_unanc = trust_service.get_full_device_trust_status(device_id)
    assert full_unanc.local_status == "UNANCHORED"
    assert full_unanc.external_status == "NOT_ANCHORED"
    assert full_unanc.overall_status == "UNANCHORED"

    # 2. Local only
    trust_service.anchor_device_passport(device_id)
    full_local = trust_service.get_full_device_trust_status(device_id)
    assert full_local.local_status == "VERIFIED"
    assert full_local.external_status == "NOT_ANCHORED"
    assert full_local.overall_status == "VERIFIED"

    # 3. Both local and external verified
    trust_service.anchor_device_passport_externally(device_id)
    full_both = trust_service.get_full_device_trust_status(device_id)
    assert full_both.local_status == "VERIFIED"
    assert full_both.external_status == "VERIFIED"
    assert full_both.overall_status == "VERIFIED"


# ---------------------------------------------------------------------------
# 3. Read-Only Invariants & Audit Events
# ---------------------------------------------------------------------------


def test_read_only_guarantees(full_trust_environment, session_factory) -> None:
    """GET operations perform zero database writes and emit zero audit events."""
    reg_service, enrich_service, trust_service, _, _, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-ro-test")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")
    trust_service.anchor_device_passport(device_id)
    trust_service.anchor_device_passport_externally(device_id)

    with session_scope(session_factory) as session:
        events_pre = session.query(DeviceEventModel).count()
        anchors_pre = session.query(ExternalTrustAnchorModel).count()

    # Call read-only methods multiple times
    for _ in range(5):
        trust_service.verify_device_passport_external(device_id)
        trust_service.get_full_device_trust_status(device_id)
        trust_service.get_device_external_anchor(device_id)

    with session_scope(session_factory) as session:
        events_post = session.query(DeviceEventModel).count()
        anchors_post = session.query(ExternalTrustAnchorModel).count()

    assert events_pre == events_post
    assert anchors_pre == anchors_post


def test_audit_event_emitted_on_external_anchor(full_trust_environment, session_factory) -> None:
    """External trust anchor is persisted in PostgreSQL relational store with full metadata."""
    reg_service, enrich_service, trust_service, _, _, _ = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-audit-ext")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")
    trust_service.anchor_device_passport(device_id)

    ext_anchor, _ = trust_service.anchor_device_passport_externally(
        device_id,
        metadata={"facility": "BLR-01", "auditor": "EcoTraceCert"},
    )

    with session_scope(session_factory) as session:
        stored = session.query(ExternalTrustAnchorModel).filter(
            ExternalTrustAnchorModel.device_id == device_id
        ).one()
        assert stored.external_anchor_id == ext_anchor.external_anchor_id
        assert stored.passport_fingerprint == ext_anchor.passport_fingerprint
        assert stored.metadata_["facility"] == "BLR-01"
        assert stored.metadata_["auditor"] == "EcoTraceCert"


# ---------------------------------------------------------------------------
# 4. Fabric Adapter Offline Safety
# ---------------------------------------------------------------------------


def test_fabric_adapter_offline_behavior() -> None:
    """FabricExternalTrustLedger cleanly returns UNAVAILABLE when gateway client is offline."""
    fabric_ledger = FabricExternalTrustLedger(
        channel="ecotrace-channel",
        chaincode="ecotrace-lifecycle",
        gateway_client=None,
    )
    assert fabric_ledger.is_available() is False

    # verify returns UNAVAILABLE
    res = fabric_ledger.verify_anchor("DEV-01", "some-hash")
    assert res.status == ExternalTrustStatus.UNAVAILABLE

    # anchor raises ExternalLedgerUnavailableError
    with pytest.raises(ExternalLedgerUnavailableError):
        fabric_ledger.anchor(
            ExternalTrustAnchor(external_anchor_id="e1", device_id="DEV-01", passport_fingerprint="abc")
        )


# ---------------------------------------------------------------------------
# 5. REST API Integration
# ---------------------------------------------------------------------------


def test_api_external_trust_flow(session_factory) -> None:
    """Full REST API flow: anchor external, query external, verify external, full trust."""
    dev_repo = PostgresDeviceRepository(session_factory)
    local_anc_repo = PostgresTrustAnchorRepository(session_factory)
    ext_anc_repo = PostgresExternalTrustAnchorRepository(session_factory)
    ext_ledger = InMemoryExternalTrustLedger(network="ecotrace-channel", provider="memory")

    pipeline = build_detection_pipeline(
        detector=_FakeDetector([
            Detection(label="monitor", confidence=0.96, bounding_box=(10, 10, 150, 150))
        ]),
        model_version="1.0.0",
        year=2026,
    )
    settings = Settings(
        device_backend="postgres",
        trust_anchor_backend="postgres",
        external_trust_backend="memory",
        log_level="WARNING",
    )
    reg_service = DeviceRegistrationService(repository=dev_repo, pipeline=pipeline, settings=settings)
    enrich_service = DeviceIntelligenceService(
        repository=dev_repo,
        brand_intelligence=RuleBasedBrandIntelligence(),
        condition_intelligence=BaselineConditionIntelligence(),
        material_intelligence=ProfileBasedMaterialIntelligence(),
        carbon_intelligence=EstimatedBurdenCarbonIntelligence(),
        settings=settings,
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=local_anc_repo,
        policy=TrustAnchorPolicy.STRICT,
        settings=settings,
        external_ledger=ext_ledger,
        external_repository=ext_anc_repo,
    )

    app = create_app()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_service] = lambda: reg_service
    app.dependency_overrides[dependencies.get_device_intelligence_service] = lambda: enrich_service
    app.dependency_overrides[dependencies.get_trust_service] = lambda: trust_service
    app.dependency_overrides[dependencies.get_settings] = lambda: settings

    with TestClient(app) as client:
        # Register and enrich device
        img_bytes = _make_test_image_bytes()
        reg_resp = client.post(
            "/devices/register",
            data={"capture_id": "cap-api-ext-01"},
            files=[("images", ("monitor.png", img_bytes, "image/png"))],
        )
        assert reg_resp.status_code == 200
        device_id = reg_resp.json()["devices"][0]["device_id"]
        client.post(f"/devices/{device_id}/confirm")
        client.post(f"/devices/{device_id}/finalize")
        client.post(f"/devices/{device_id}/enrich", json={"ocr_text": "Samsung Odyssey G9"})

        # 1. External verify before anchoring -> NOT_ANCHORED
        v_pre = client.get(f"/devices/{device_id}/passport/external-anchor/verify")
        assert v_pre.status_code == 200
        assert v_pre.json()["verification"]["status"] == "NOT_ANCHORED"

        # 2. Local anchor
        client.post(f"/devices/{device_id}/passport/anchor")

        # 3. External anchor -> HTTP 201
        ext_resp = client.post(
            f"/devices/{device_id}/passport/external-anchor",
            json={"metadata": {"auditor": "EcoTraceCert"}},
        )
        assert ext_resp.status_code == 201
        ext_data = ext_resp.json()
        assert ext_data["is_new"] is True
        assert ext_data["anchor"]["device_id"] == device_id

        # 4. GET external anchor -> HTTP 200
        get_ext = client.get(f"/devices/{device_id}/passport/external-anchor")
        assert get_ext.status_code == 200
        assert get_ext.json()["anchor"]["external_anchor_id"] == ext_data["anchor"]["external_anchor_id"]

        # 5. External verify -> VERIFIED
        v_post = client.get(f"/devices/{device_id}/passport/external-anchor/verify")
        assert v_post.status_code == 200
        assert v_post.json()["verification"]["status"] == "VERIFIED"

        # 6. Full trust comparison -> VERIFIED overall
        full_resp = client.get(f"/devices/{device_id}/trust/full")
        assert full_resp.status_code == 200
        full_data = full_resp.json()["trust"]
        assert full_data["local_status"] == "VERIFIED"
        assert full_data["external_status"] == "VERIFIED"
        assert full_data["overall_status"] == "VERIFIED"

        # 7. Non-existent device -> HTTP 404
        assert client.get("/devices/DEV-NONEXISTENT/passport/external-anchor").status_code == 404
        assert client.get("/devices/DEV-NONEXISTENT/trust/full").status_code == 404

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# 6. Alembic Migration Upgrade & Downgrade
# ---------------------------------------------------------------------------


def test_alembic_migration_003_upgrade_downgrade(tmp_path) -> None:
    """Alembic cleanly executes upgrade head, downgrade to 002, and re-upgrade."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "alembic_test_p511.db"
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    script_loc = Path(__file__).resolve().parents[1] / "alembic"

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(script_loc))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    # Upgrade to head (includes 003)
    command.upgrade(alembic_cfg, "head")

    # Downgrade to 002
    command.downgrade(alembic_cfg, "002_add_p59_trust_anchors")

    # Re-upgrade to head
    command.upgrade(alembic_cfg, "head")


# ---------------------------------------------------------------------------
# 7. Granular Algorithm, Metadata, and Multi-Backend Parity
# ---------------------------------------------------------------------------


def test_algorithm_mismatch_detected(full_trust_environment) -> None:
    """Algorithm mismatch on external ledger evaluates to MISMATCH."""
    _, _, trust_service, _, ext_ledger, _ = full_trust_environment

    anchor = ExternalTrustAnchor(
        external_anchor_id="ext-algo-01",
        device_id="DEV-ALGO-01",
        passport_fingerprint="abc123hash",
        algorithm="sha512",  # Different algorithm
    )
    ext_ledger.anchor(anchor)

    res = ext_ledger.verify_anchor("DEV-ALGO-01", "abc123hash", algorithm="sha256")
    assert res.status == ExternalTrustStatus.MISMATCH


def test_transaction_metadata_preserved(full_trust_environment) -> None:
    """Transaction IDs and metadata dictionaries are strictly preserved across storage and retrieval."""
    reg_service, enrich_service, trust_service, _, ext_ledger, ext_repo = full_trust_environment

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id="cap-meta-01")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell Latitude")
    trust_service.anchor_device_passport(device_id)

    ext_anchor, _ = trust_service.anchor_device_passport_externally(
        device_id,
        metadata={"facility_code": "BLR_DC_4", "auditor_signature": "SIG_ED25519_ABC"},
    )

    retrieved = trust_service.get_device_external_anchor(device_id)
    assert retrieved.transaction_id == ext_anchor.transaction_id
    assert retrieved.metadata["facility_code"] == "BLR_DC_4"
    assert retrieved.metadata["auditor_signature"] == "SIG_ED25519_ABC"


@pytest.mark.parametrize("backend_type", ["memory", "postgres"])
def test_multi_backend_parity(backend_type: str, session_factory) -> None:
    """InMemory and Postgres external trust repositories exhibit identical semantics."""
    if backend_type == "memory":
        dev_repo = InMemoryDeviceRepository()
        local_repo = InMemoryTrustAnchorRepository()
        ext_repo = None
        ext_ledger = InMemoryExternalTrustLedger()
    else:
        dev_repo = PostgresDeviceRepository(session_factory)
        local_repo = PostgresTrustAnchorRepository(session_factory)
        ext_repo = PostgresExternalTrustAnchorRepository(session_factory)
        ext_ledger = InMemoryExternalTrustLedger()

    pipeline = build_detection_pipeline(
        detector=_FakeDetector([
            Detection(label="monitor", confidence=0.94, bounding_box=(10, 10, 80, 80))
        ]),
        model_version="1.0.0",
        year=2026,
    )
    settings = Settings(log_level="WARNING")
    reg_service = DeviceRegistrationService(repository=dev_repo, pipeline=pipeline, settings=settings)
    enrich_service = DeviceIntelligenceService(
        repository=dev_repo,
        brand_intelligence=RuleBasedBrandIntelligence(),
        condition_intelligence=BaselineConditionIntelligence(),
        material_intelligence=ProfileBasedMaterialIntelligence(),
        carbon_intelligence=EstimatedBurdenCarbonIntelligence(),
        settings=settings,
    )
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=local_repo,
        policy=TrustAnchorPolicy.STRICT,
        settings=settings,
        external_ledger=ext_ledger,
        external_repository=ext_repo,
    )

    records, _ = reg_service.register_from_images([_make_loaded_image()], capture_id=f"cap-parity-ext-{backend_type}")
    device_id = records[0].device_id
    reg_service.confirm_device(device_id)
    reg_service.finalize_registration(device_id)
    enrich_service.enrich_device(device_id, ocr_text="Dell UltraSharp")
    trust_service.anchor_device_passport(device_id)

    # 1. External anchor
    anchor, is_new = trust_service.anchor_device_passport_externally(device_id)
    assert is_new is True

    # 2. External verify -> VERIFIED
    v_res = trust_service.verify_device_passport_external(device_id)
    assert v_res.status == ExternalTrustStatus.VERIFIED

    # 3. Full trust status -> VERIFIED
    full = trust_service.get_full_device_trust_status(device_id)
    assert full.overall_status == "VERIFIED"


def test_fabric_live_client_adapter_invocations() -> None:
    """FabricExternalTrustLedger correctly translates calls to an injected gateway client."""
    class _MockGatewayClient:
        def __init__(self) -> None:
            self.submitted = []
            self.evaluated = []

        def submitTransaction(self, fn: str, *args: str) -> str:
            self.submitted.append((fn, args))
            return "tx-fabric-live-999"

        def evaluateTransaction(self, fn: str, *args: str) -> str:
            self.evaluated.append((fn, args))
            return ""

    mock_client = _MockGatewayClient()
    fabric_ledger = FabricExternalTrustLedger(
        channel="ecotrace-channel",
        chaincode="ecotrace-lifecycle",
        gateway_client=mock_client,
    )
    assert fabric_ledger.is_available() is True

    anchor = ExternalTrustAnchor(
        external_anchor_id="ext-fab-01",
        device_id="DEV-FAB-01",
        passport_fingerprint="abc123hash",
    )
    res = fabric_ledger.anchor(anchor)
    assert res.transaction_id == "tx-fabric-live-999"
    assert len(mock_client.submitted) == 1
    assert mock_client.submitted[0][0] == "AnchorDevicePassport"
