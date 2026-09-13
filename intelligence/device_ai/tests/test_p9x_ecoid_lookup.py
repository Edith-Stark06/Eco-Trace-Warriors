"""Test suite for EcoID passport/trust lookup (E2E fix — Issue 1).

Covers:
1. device_id and EcoID resolve to the same DeviceRecord (InMemory, JsonFile, Postgres).
2. Passport lookup by EcoID matches passport lookup by device_id.
3. Intelligence enrichment lookup by EcoID returns the same enrichment (no
   accidental double-enrichment / mismatched device_id on the enrichment row).
4. Trust status resolved via EcoID correctly reports an existing local anchor
   as VERIFIED rather than UNANCHORED (regression test for the anchor lookup
   bug: the anchor repository is keyed by canonical device_id, so a naive
   fix that resolved get_device() but kept passing the raw EcoID into
   anchor_repository.get_by_device_id() would incorrectly report UNANCHORED).
5. An identifier matching neither a device_id nor an EcoID still 404s.
6. Alembic migration 004 (indexed eco_id column) upgrades/downgrades cleanly
   and backfills eco_id from pre-existing metadata JSON.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from device_ai.configs.settings import Settings
from device_ai.database.models import Base
from device_ai.database.session import get_session_factory
from device_ai.devices.enrichment_service import DeviceIntelligenceService
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
    resolve_device,
)
from device_ai.devices.service import DeviceRegistrationService
from device_ai.devices.trust_anchor import (
    DevicePassportTrustService,
    InMemoryTrustAnchorRepository,
    TrustAnchorPolicy,
    TrustStatus,
)
from device_ai.exceptions import DeviceNotFoundError


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _make_record(
    device_id: str = "DEV-2026-TESTECO1-01",
    eco_id: str = "ET-2026-TESTECO1",
) -> DeviceRecord:
    return DeviceRecord(
        device_id=device_id,
        capture_id="cap-testeco1",
        class_id=0,
        device_type="laptop",
        confidence=0.95,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 10, 100, 100),
        model_version="test-1.0.0",
        inference_mode="single_model",
        registration_state=RegistrationState.REGISTERED,
        metadata={"eco_id": eco_id, "image_count": 1},
    )


def _seed_registered_device(repo, record: DeviceRecord) -> None:
    """Persist ``record`` plus the DETECTED/CONFIRMED/REGISTERED audit trail
    that a real registration -> confirm -> finalize flow would have produced
    — required for passport verification to pass (see
    devices/passport_verification.py's audit_history check)."""
    repo.save(record)
    for event_type in (
        DeviceEventType.DEVICE_DETECTED,
        DeviceEventType.DEVICE_CONFIRMED,
        DeviceEventType.DEVICE_REGISTERED,
    ):
        repo.append_event(
            DeviceEvent(
                event_id=f"evt-{event_type.value.lower()}",
                device_id=record.device_id,
                event_type=event_type,
                capture_id=record.capture_id,
            )
        )


# ---------------------------------------------------------------------------
# 1. Repository-level get_by_eco_id / resolve_device across all backends
# ---------------------------------------------------------------------------


def test_in_memory_repository_resolves_by_eco_id() -> None:
    repo = InMemoryDeviceRepository()
    record = _make_record()
    repo.save(record)

    assert repo.get_by_eco_id("ET-2026-TESTECO1") is record
    assert repo.get_by_eco_id("NO-SUCH-ECOID") is None
    assert resolve_device(repo, record.device_id) is record
    assert resolve_device(repo, "ET-2026-TESTECO1") is record
    assert resolve_device(repo, "INVALID-DEVICE-12345") is None


def test_json_file_repository_resolves_by_eco_id(tmp_path: Path) -> None:
    repo = JsonFileDeviceRepository(tmp_path / "devices")
    record = _make_record()
    repo.save(record)

    found = repo.get_by_eco_id("ET-2026-TESTECO1")
    assert found is not None
    assert found.device_id == record.device_id
    assert repo.get_by_eco_id("NO-SUCH-ECOID") is None


@pytest.fixture
def sqlite_engine(tmp_path: Path):
    db_file = tmp_path / "test_ecoid_lookup.db"
    engine = create_engine(f"sqlite:///{db_file}", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine):
    return get_session_factory(sqlite_engine)


def test_postgres_repository_resolves_by_eco_id(session_factory) -> None:
    repo = PostgresDeviceRepository(session_factory)
    record = _make_record()
    repo.save(record)

    found = repo.get_by_eco_id("ET-2026-TESTECO1")
    assert found is not None
    assert found.device_id == record.device_id
    assert repo.get_by_eco_id("NO-SUCH-ECOID") is None
    assert resolve_device(repo, "ET-2026-TESTECO1").device_id == record.device_id


# ---------------------------------------------------------------------------
# 2-4. End-to-end: passport / intelligence / trust resolve identically via EcoID
# ---------------------------------------------------------------------------


@pytest.fixture
def ecoid_environment(session_factory):
    dev_repo = PostgresDeviceRepository(session_factory)
    anchor_repo = InMemoryTrustAnchorRepository()
    settings = Settings(
        trust_anchor_backend="memory",
        external_trust_backend="memory",
        log_level="WARNING",
    )

    # pipeline is unused by the get_device/passport/enrich/trust paths under test.
    reg_service = DeviceRegistrationService(
        repository=dev_repo,
        pipeline=None,
        settings=settings,
    )
    enrich_service = DeviceIntelligenceService(repository=dev_repo, settings=settings)
    trust_service = DevicePassportTrustService(
        device_service=reg_service,
        anchor_repository=anchor_repo,
        policy=TrustAnchorPolicy.STRICT,
        settings=settings,
    )
    return dev_repo, reg_service, enrich_service, trust_service


def test_passport_lookup_matches_by_device_id_and_eco_id(ecoid_environment) -> None:
    dev_repo, reg_service, _enrich_service, _trust_service = ecoid_environment
    record = _make_record()
    dev_repo.save(record)

    by_device_id = reg_service.get_device_passport(record.device_id)
    by_eco_id = reg_service.get_device_passport("ET-2026-TESTECO1")

    assert by_device_id.device_id == by_eco_id.device_id == record.device_id
    assert by_device_id.eco_id == by_eco_id.eco_id == "ET-2026-TESTECO1"


def test_invalid_identifier_still_404s(ecoid_environment) -> None:
    _dev_repo, reg_service, _enrich_service, _trust_service = ecoid_environment
    with pytest.raises(DeviceNotFoundError):
        reg_service.get_device("INVALID-DEVICE-12345")


def test_enrichment_lookup_by_eco_id_returns_same_enrichment(ecoid_environment) -> None:
    dev_repo, _reg_service, enrich_service, _trust_service = ecoid_environment
    record = _make_record()
    dev_repo.save(record)

    _record, enrichment_by_device_id = enrich_service.enrich_device(record.device_id)
    # get_device_intelligence should find the already-persisted enrichment via
    # EcoID rather than silently re-enriching under a mismatched device_id.
    _record2, enrichment_by_eco_id = enrich_service.get_device_intelligence(
        "ET-2026-TESTECO1"
    )

    assert enrichment_by_device_id.device_id == record.device_id
    assert enrichment_by_eco_id.device_id == record.device_id
    assert enrichment_by_eco_id.enriched_at == enrichment_by_device_id.enriched_at


def test_trust_status_via_eco_id_finds_existing_local_anchor(ecoid_environment) -> None:
    """Regression test: anchoring by device_id then querying trust by EcoID
    must report VERIFIED, not UNANCHORED — proving the anchor repository
    lookup uses the canonicalized device_id, not the raw EcoID string.
    """
    dev_repo, reg_service, enrich_service, trust_service = ecoid_environment
    record = _make_record()
    _seed_registered_device(dev_repo, record)
    enrich_service.enrich_device(record.device_id)

    anchor, is_new = trust_service.anchor_device_passport(record.device_id)
    assert is_new is True

    status_by_device_id = trust_service.get_device_trust_status(record.device_id)
    status_by_eco_id = trust_service.get_device_trust_status("ET-2026-TESTECO1")

    assert status_by_device_id.status == TrustStatus.VERIFIED
    assert status_by_eco_id.status == TrustStatus.VERIFIED
    assert status_by_device_id.anchor_id == anchor.anchor_id
    assert status_by_eco_id.anchor_id == anchor.anchor_id


def test_anchor_created_via_eco_id_is_retrievable_by_device_id(
    ecoid_environment,
) -> None:
    """Symmetric case: anchor using the EcoID as input, then confirm the
    anchor row itself is keyed by the canonical device_id (not the EcoID),
    so device_id-based lookups (e.g. from the collector app) still work.
    """
    dev_repo, reg_service, enrich_service, trust_service = ecoid_environment
    record = _make_record()
    _seed_registered_device(dev_repo, record)
    enrich_service.enrich_device(record.device_id)

    trust_service.anchor_device_passport("ET-2026-TESTECO1")

    anchor = trust_service.get_device_anchor(record.device_id)
    assert anchor.device_id == record.device_id


# ---------------------------------------------------------------------------
# 5. Alembic migration 004: schema + backfill
# ---------------------------------------------------------------------------


def test_alembic_migration_004_upgrade_downgrade(tmp_path: Path) -> None:
    """Alembic cleanly executes upgrade head, downgrade to 003, and re-upgrade."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "alembic_test_p9x.db"
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    script_loc = Path(__file__).resolve().parents[1] / "alembic"

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(script_loc))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "003_add_p511_external_trust_anchors")
    command.upgrade(alembic_cfg, "head")


def test_alembic_migration_004_backfills_eco_id_from_metadata(tmp_path: Path) -> None:
    """A device row persisted before this migration (eco_id only in the
    metadata JSON blob) is backfilled into the new indexed column."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "alembic_test_p9x_backfill.db"
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    script_loc = Path(__file__).resolve().parents[1] / "alembic"

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(script_loc))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    # Stop at 003 — before the eco_id column exists — and insert a "legacy" row.
    command.upgrade(alembic_cfg, "003_add_p511_external_trust_anchors")

    engine = create_engine(f"sqlite:///{db_path}")
    now = _utc_now().isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO devices "
                "(device_id, capture_id, class_id, device_type, confidence, "
                "confidence_state, bounding_box, model_version, inference_mode, "
                "registration_state, metadata, created_at, updated_at) "
                "VALUES "
                "(:device_id, 'cap-legacy', 0, 'laptop', 0.9, 'HIGH_CONFIDENCE', "
                "'[0,0,1,1]', '1.0.0', 'single_model', 'REGISTERED', "
                ":metadata, :now, :now)"
            ),
            {
                "device_id": "DEV-2026-LEGACY01-01",
                "metadata": '{"eco_id": "ET-2026-LEGACY01"}',
                "now": now,
            },
        )
    engine.dispose()

    # Upgrade to head: the eco_id column is added and backfilled.
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT eco_id FROM devices WHERE device_id = :device_id"),
            {"device_id": "DEV-2026-LEGACY01-01"},
        ).one()
    engine.dispose()

    assert row.eco_id == "ET-2026-LEGACY01"
