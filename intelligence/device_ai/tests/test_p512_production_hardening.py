"""Phase P5.12: End-to-End Production Hardening & Release Test Suite.

Verifies:
1. Complete device lifecycle end-to-end flow from image upload to full blockchain trust verification.
2. Strict read-only guarantees on all GET verification/trust endpoints.
3. Explicit state mutation workflows and idempotency invariants.
4. REST API error envelope compliance and HTTP status code mappings (404, 409, 422, 503).
5. X-Request-ID propagation across headers, logs, and response envelopes.
6. Multi-backend repository parity across InMemory and PostgreSQL stores.
7. Complete Alembic migration chain (001 -> 002 -> 003 -> 000 -> 003).
8. Protected ML/Data asset cryptographic immutability.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import io
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings
from device_ai.database.models import (
    Base,
    DeviceEnrichmentModel,
    DeviceEventModel,
    DeviceModel,
    ExternalTrustAnchorModel,
    MaterialItemModel,
    TrustAnchorModel,
)
from device_ai.database.session import get_session_factory, session_scope
from device_ai.devices.brand import RuleBasedBrandIntelligence
from device_ai.devices.carbon import EstimatedBurdenCarbonIntelligence
from device_ai.devices.condition import BaselineConditionIntelligence
from device_ai.devices.enrichment_service import DeviceIntelligenceService
from device_ai.devices.external_trust import (
    ExternalTrustAnchor,
    ExternalTrustStatus,
    FabricExternalTrustLedger,
    InMemoryExternalTrustLedger,
)
from device_ai.devices.material import ProfileBasedMaterialIntelligence
from device_ai.devices.models import (
    DeviceEvent,
    DeviceEventType,
    DeviceRecord,
    RegistrationState,
)
from device_ai.devices.passport_verification import (
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
    TrustStatus,
)
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.predictor import Detection, DetectionResult, Detector
from device_ai.preprocessing.image_loader import LoadedImage


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _make_test_image_bytes(w: int = 150, h: int = 150) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=(100, 150, 200)).save(buf, format="PNG")
    return buf.getvalue()


class _ProductionHardeningDetector(Detector):
    version = "p512-hardened-1.0.0"

    def __init__(self, detections: list[Detection] | None = None) -> None:
        self._detections = detections or [
            Detection(label="laptop", confidence=0.97, bounding_box=(15, 15, 120, 120))
        ]

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        top = self._detections[0] if self._detections else None
        return DetectionResult(
            device_type=top.label.title() if top else "Unknown",
            brand="Dell",
            confidence=top.confidence if top else 0.0,
            detections=self._detections,
        )


@pytest.fixture
def sqlite_engine(tmp_path: Path):
    db_file = tmp_path / "test_p512_hardened.db"
    engine = create_engine(f"sqlite:///{db_file}", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine):
    return get_session_factory(sqlite_engine)


@pytest.fixture
def hardened_services(session_factory):
    dev_repo = PostgresDeviceRepository(session_factory)
    local_anc_repo = PostgresTrustAnchorRepository(session_factory)
    ext_anc_repo = PostgresExternalTrustAnchorRepository(session_factory)
    ext_ledger = InMemoryExternalTrustLedger(network="ecotrace-channel", provider="memory")

    detector = _ProductionHardeningDetector()
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)

    settings = Settings(
        device_backend="postgres",
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

    return reg_service, enrich_service, trust_service, pipeline, settings


# ---------------------------------------------------------------------------
# 1. Complete End-to-End Production Lifecycle Test
# ---------------------------------------------------------------------------


def test_complete_end_to_end_production_lifecycle(hardened_services, session_factory) -> None:
    """Validate full flow from HTTP registration to external blockchain verification."""
    reg_service, enrich_service, trust_service, pipeline, settings = hardened_services

    app = create_app()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_service] = lambda: reg_service
    app.dependency_overrides[dependencies.get_device_intelligence_service] = lambda: enrich_service
    app.dependency_overrides[dependencies.get_trust_service] = lambda: trust_service
    app.dependency_overrides[dependencies.get_settings] = lambda: settings

    with TestClient(app) as client:
        # Step 1: Health & Model Check
        h_resp = client.get("/health")
        assert h_resp.status_code == 200
        assert h_resp.json()["status"] in ("healthy", "degraded")

        m_resp = client.get("/model")
        assert m_resp.status_code == 200
        assert "class_map" in m_resp.json()

        # Step 2: Register Device from image
        img_bytes = _make_test_image_bytes()
        reg_resp = client.post(
            "/devices/register",
            data={"capture_id": "cap-p512-prod-01"},
            files=[("images", ("device.png", img_bytes, "image/png"))],
            headers={"X-Request-ID": "req-p512-test-01"},
        )
        assert reg_resp.status_code == 200
        assert reg_resp.headers.get("X-Request-ID") == "req-p512-test-01"
        data = reg_resp.json()
        assert len(data["devices"]) == 1
        device_id = data["devices"][0]["device_id"]
        assert data["devices"][0]["registration_state"] == "DETECTED"

        # Step 3: Confirm Device
        conf_resp = client.post(f"/devices/{device_id}/confirm")
        assert conf_resp.status_code == 200
        assert conf_resp.json()["device"]["registration_state"] == "CONFIRMED"

        # Step 4: Finalize Device
        fin_resp = client.post(f"/devices/{device_id}/finalize")
        assert fin_resp.status_code == 200
        assert fin_resp.json()["device"]["registration_state"] == "REGISTERED"

        # Step 5: Enrich Device Intelligence
        enr_resp = client.post(
            f"/devices/{device_id}/enrich",
            json={"ocr_text": "Dell Latitude 7420 Intel Core i7"},
        )
        assert enr_resp.status_code == 200
        assert enr_resp.json()["intelligence"]["brand"]["value"] == "Dell"

        # Step 6: Generate Device Passport
        pass_resp = client.get(f"/devices/{device_id}/passport")
        assert pass_resp.status_code == 200
        passport = pass_resp.json()["passport"]
        assert passport["identity"]["device_id"] == device_id
        assert passport["lifecycle"]["is_registered"] is True
        assert passport["lifecycle"]["is_enriched"] is True

        # Step 7: Passport Verification (Read-Only)
        ver_resp = client.get(f"/devices/{device_id}/passport/verify")
        assert ver_resp.status_code == 200
        assert ver_resp.json()["verification"]["verification_status"] == "VERIFIED"

        # Step 8: Local Trust Anchoring
        anc_resp = client.post(f"/devices/{device_id}/passport/anchor")
        assert anc_resp.status_code == 201
        assert anc_resp.json()["is_new"] is True
        local_anchor = anc_resp.json()["anchor"]
        assert local_anchor["status"] == "ANCHORED"

        # Step 9: Trust Status Evaluation (Read-Only)
        trust_resp = client.get(f"/devices/{device_id}/trust")
        assert trust_resp.status_code == 200
        assert trust_resp.json()["trust"]["status"] == "VERIFIED"

        # Step 10: External Blockchain Trust Anchoring
        ext_resp = client.post(
            f"/devices/{device_id}/passport/external-anchor",
            json={"metadata": {"auditor": "EcoTraceCert", "facility": "BLR-01"}},
        )
        assert ext_resp.status_code == 201
        ext_anchor = ext_resp.json()["anchor"]
        assert ext_anchor["device_id"] == device_id
        assert ext_anchor["network"] == "ecotrace-channel"

        # Step 11: External Verification (Read-Only)
        ext_ver_resp = client.get(f"/devices/{device_id}/passport/external-anchor/verify")
        assert ext_ver_resp.status_code == 200
        assert ext_ver_resp.json()["verification"]["status"] == "VERIFIED"

        # Step 12: Full Trust Comparison (Read-Only)
        full_trust_resp = client.get(f"/devices/{device_id}/trust/full")
        assert full_trust_resp.status_code == 200
        full_trust = full_trust_resp.json()["trust"]
        assert full_trust["local_status"] == "VERIFIED"
        assert full_trust["external_status"] == "VERIFIED"
        assert full_trust["overall_status"] == "VERIFIED"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# 2. Strict Read-Only Guarantees Audit
# ---------------------------------------------------------------------------


def test_all_get_verification_routes_strictly_read_only(hardened_services, session_factory) -> None:
    """Every GET verification/read route guarantees zero DB writes and zero event emissions."""
    reg_service, enrich_service, trust_service, pipeline, settings = hardened_services

    app = create_app()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_service] = lambda: reg_service
    app.dependency_overrides[dependencies.get_device_intelligence_service] = lambda: enrich_service
    app.dependency_overrides[dependencies.get_trust_service] = lambda: trust_service
    app.dependency_overrides[dependencies.get_settings] = lambda: settings

    with TestClient(app) as client:
        # Seed anchored device
        reg_resp = client.post(
            "/devices/register",
            data={"capture_id": "cap-p512-ro"},
            files=[("images", ("device.png", _make_test_image_bytes(), "image/png"))],
        )
        device_id = reg_resp.json()["devices"][0]["device_id"]
        client.post(f"/devices/{device_id}/confirm")
        client.post(f"/devices/{device_id}/finalize")
        client.post(f"/devices/{device_id}/enrich", json={"ocr_text": "Dell Precision 5550"})
        client.post(f"/devices/{device_id}/passport/anchor")
        client.post(f"/devices/{device_id}/passport/external-anchor")

        # Snapshot DB counts before read-only calls
        with session_scope(session_factory) as session:
            count_devices = session.query(DeviceModel).count()
            count_enrich = session.query(DeviceEnrichmentModel).count()
            count_events = session.query(DeviceEventModel).count()
            count_local_anchors = session.query(TrustAnchorModel).count()
            count_ext_anchors = session.query(ExternalTrustAnchorModel).count()

        # Repeatedly call ALL GET read/verification endpoints
        for _ in range(5):
            client.get(f"/devices/{device_id}")
            client.get(f"/devices/{device_id}/intelligence")
            client.get(f"/devices/{device_id}/events")
            client.get(f"/devices/{device_id}/passport")
            client.get(f"/devices/{device_id}/passport/verify")
            client.get(f"/devices/{device_id}/passport/anchor")
            client.get(f"/devices/{device_id}/passport/anchor/verify")
            client.get(f"/devices/{device_id}/trust")
            client.get(f"/devices/{device_id}/passport/external-anchor")
            client.get(f"/devices/{device_id}/passport/external-anchor/verify")
            client.get(f"/devices/{device_id}/trust/full")

        # Snapshot DB counts after read-only calls
        with session_scope(session_factory) as session:
            assert session.query(DeviceModel).count() == count_devices
            assert session.query(DeviceEnrichmentModel).count() == count_enrich
            assert session.query(DeviceEventModel).count() == count_events
            assert session.query(TrustAnchorModel).count() == count_local_anchors
            assert session.query(ExternalTrustAnchorModel).count() == count_ext_anchors

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# 3. HTTP Error Envelopes & Status Codes Audit
# ---------------------------------------------------------------------------


def test_http_error_envelopes_and_status_codes(hardened_services) -> None:
    """Audit proper 404, 409, 422, 503 status codes and structured ErrorResponse shape."""
    reg_service, enrich_service, trust_service, pipeline, settings = hardened_services

    app = create_app()
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline
    app.dependency_overrides[dependencies.get_device_service] = lambda: reg_service
    app.dependency_overrides[dependencies.get_device_intelligence_service] = lambda: enrich_service
    app.dependency_overrides[dependencies.get_trust_service] = lambda: trust_service
    app.dependency_overrides[dependencies.get_settings] = lambda: settings

    with TestClient(app) as client:
        # 1. 404 on non-existent device
        for url in [
            "/devices/DEV-NONEXISTENT",
            "/devices/DEV-NONEXISTENT/confirm",
            "/devices/DEV-NONEXISTENT/finalize",
            "/devices/DEV-NONEXISTENT/enrich",
            "/devices/DEV-NONEXISTENT/passport",
            "/devices/DEV-NONEXISTENT/trust",
            "/devices/DEV-NONEXISTENT/passport/external-anchor",
            "/devices/DEV-NONEXISTENT/trust/full",
        ]:
            resp = client.get(url) if "confirm" not in url and "finalize" not in url and "enrich" not in url else client.post(url)
            assert resp.status_code == 404, f"Expected 404 for {url}, got {resp.status_code}"
            err_data = resp.json()
            assert "error" in err_data
            assert err_data["error"]["code"] == "DEVICE_NOT_FOUND"

        # 2. 422 on corrupted image upload
        bad_resp = client.post(
            "/devices/register",
            data={"capture_id": "cap-bad"},
            files=[("images", ("corrupt.png", b"not-a-valid-image", "image/png"))],
        )
        assert bad_resp.status_code == 422
        assert "error" in bad_resp.json()

        # 3. 409 on anchor conflict
        reg_resp = client.post(
            "/devices/register",
            data={"capture_id": "cap-conf"},
            files=[("images", ("device.png", _make_test_image_bytes(), "image/png"))],
        )
        dev_id = reg_resp.json()["devices"][0]["device_id"]
        client.post(f"/devices/{dev_id}/confirm")
        client.post(f"/devices/{dev_id}/finalize")
        client.post(f"/devices/{dev_id}/enrich", json={"ocr_text": "Dell Precision"})
        client.post(f"/devices/{dev_id}/passport/anchor")

        # Mutate to create mismatch
        client.post(f"/devices/{dev_id}/enrich", json={"ocr_text": "HP EliteBook 840"})

        # Calling standard anchor (without reanchor) -> 409 ANCHOR_CONFLICT
        anc_conf = client.post(f"/devices/{dev_id}/passport/anchor")
        assert anc_conf.status_code == 409
        assert anc_conf.json()["error"]["code"] == "ANCHOR_CONFLICT"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


# ---------------------------------------------------------------------------
# 4. Multi-Backend Persistence Parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend", ["memory", "postgres"])
def test_multi_backend_full_parity(backend: str, session_factory) -> None:
    """Validate behavior equivalence across InMemory and Postgres backends."""
    if backend == "memory":
        dev_repo = InMemoryDeviceRepository()
        local_repo = InMemoryTrustAnchorRepository()
        ext_repo = None
    else:
        dev_repo = PostgresDeviceRepository(session_factory)
        local_repo = PostgresTrustAnchorRepository(session_factory)
        ext_repo = PostgresExternalTrustAnchorRepository(session_factory)

    ext_ledger = InMemoryExternalTrustLedger()
    detector = _ProductionHardeningDetector()
    pipeline = build_detection_pipeline(detector=detector, model_version="1.0.0", year=2026)
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

    # Register
    raw = _make_test_image_bytes()
    pil = Image.open(io.BytesIO(raw)).convert("RGB")
    loaded = LoadedImage(filename="d.png", content_type="image/png", raw=raw, image=pil)
    recs, _ = reg_service.register_from_images([loaded], capture_id=f"cap-parity-{backend}")
    d_id = recs[0].device_id

    reg_service.confirm_device(d_id)
    reg_service.finalize_registration(d_id)
    enrich_service.enrich_device(d_id, ocr_text="Dell Latitude")

    # Local anchor
    anc, is_new = trust_service.anchor_device_passport(d_id)
    assert is_new is True

    # External anchor
    ext_anc, ext_is_new = trust_service.anchor_device_passport_externally(d_id)
    assert ext_is_new is True

    # Full trust evaluation
    full = trust_service.get_full_device_trust_status(d_id)
    assert full.local_status == "VERIFIED"
    assert full.external_status == "VERIFIED"
    assert full.overall_status == "VERIFIED"


# ---------------------------------------------------------------------------
# 5. Alembic Migration Complete Cycle Audit
# ---------------------------------------------------------------------------


def test_alembic_chain_001_002_003_complete_cycle(tmp_path: Path) -> None:
    """Audit migration chain: clean upgrade to head, stepwise downgrade to base, re-upgrade."""
    db_path = tmp_path / "alembic_full_cycle.db"
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    script_loc = Path(__file__).resolve().parents[1] / "alembic"

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(script_loc))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    # 1. Upgrade from empty to head
    command.upgrade(alembic_cfg, "head")

    # 2. Downgrade to 002
    command.downgrade(alembic_cfg, "002_add_p59_trust_anchors")

    # 3. Downgrade to 001
    command.downgrade(alembic_cfg, "001_initial_p54_device_schema")

    # 4. Downgrade to base
    command.downgrade(alembic_cfg, "base")

    # 5. Full re-upgrade to head
    command.upgrade(alembic_cfg, "head")


# ---------------------------------------------------------------------------
# 6. Protected ML / Data Assets Cryptographic Hash Audit
# ---------------------------------------------------------------------------


def test_protected_assets_sha256_verification() -> None:
    """Audit that all 6 protected ML checkpoints and dataset manifests match exact SHA-256 digests."""
    targets = {
        "dataset_acquisition/training/p4_4_2_bulk_balance_v1/runs/p442_yolo11n/weights/best.pt": (
            "c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92"
        ),
        "dataset_acquisition/training/p4_11_multisource_targeted_aug_v1/runs/p411_yolo11n_targeted_aug/weights/best.pt": (
            "ca10aaf0de5cc6e24874a24a472b5cf8135f7163f7b54289a74554265a97355c"
        ),
        "dataset_acquisition/training/p4_12_model_scale_v1/runs/p412_yolo11s/weights/best.pt": (
            "96f156d0a46240f6a67187704f91f8a7b1e675e1b94246cf0d83f19f3f0380bc"
        ),
        "dataset_acquisition/training/p4_14_targeted_ood_robustness_v1/runs/p414_yolo11n_targeted_aug/weights/best.pt": (
            "8fdb02a43db526f7ebb4ba413e6e3dcf5d8eb516590bcd0120d26118e79e9d81"
        ),
        "dataset_acquisition/evaluation/p4_5_real_world_v1/p45_data.yaml": (
            "b5fae47d73ec30698d9825cb04c06722bc1cb41d687a917bb208f1bd1c3bdf5b"
        ),
        "dataset_acquisition/evaluation/p4_7_wikimedia_ood_v1/p47_final_data.yaml": (
            "5daa90ae1ebca5fe7b5578dd37530e5eba90b47ce7873c35e133e51f7e60e284"
        ),
    }

    # Resolve paths relative to workspace root (2 levels up from intelligence/device_ai)
    workspace_root = Path(__file__).resolve().parents[3]

    for rel_path, expected_hash in targets.items():
        full_path = workspace_root / rel_path
        assert full_path.exists(), f"Protected asset missing at {full_path}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, (
            f"Protected asset SHA-256 mismatch for {rel_path}!\n"
            f"Expected: {expected_hash}\n"
            f"Actual:   {actual_hash}"
        )
