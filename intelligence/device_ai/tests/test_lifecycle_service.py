"""Unit tests for the device lifecycle service and config (milestone M3.3).

Exercises the injectable :class:`LifecycleService` façade: event/record
construction against the shipped rules, incremental append, provenance stamping,
clockless determinism, config resolution, and integration with the ledger
**through the backend abstraction** (M3.2). Offline — the ledger uses in-memory
and mock backends; no networking, no images.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from device_ai.ledger import LedgerService, MockEthereumLedgerBackend
from device_ai.lifecycle import (
    DEFAULT_RULES_PATH,
    LifecycleConfig,
    LifecycleEventType,
    LifecycleService,
)

E = LifecycleEventType


def _fixed_clock():
    return lambda: datetime(2026, 8, 5, 9, 30, 0, tzinfo=UTC)


# -- Config ------------------------------------------------------------------


def test_config_default_rules_path():
    config = LifecycleConfig()
    assert config.rules_path == DEFAULT_RULES_PATH
    assert DEFAULT_RULES_PATH == "lifecycle/data/transitions.yaml"


def test_config_resolves_relative_to_package_root():
    config = LifecycleConfig()
    root = Path("/tmp/pkg")
    assert config.resolved_rules_path(package_root=root) == root / DEFAULT_RULES_PATH


def test_config_absolute_path_is_preserved(tmp_path):
    absolute = tmp_path / "custom.yaml"
    config = LifecycleConfig(rules_path=str(absolute))
    # An absolute configured path is used as-is regardless of package root.
    assert config.resolved_rules_path(package_root=Path("/other")) == absolute


# -- Service: construction ---------------------------------------------------


def test_service_loads_shipped_rules_by_default():
    svc = LifecycleService(clock=None)
    assert svc.rules.version == "1.0.0"
    assert svc.rules.is_initial(E.REGISTERED)


def test_service_default_ledger_is_injected():
    svc = LifecycleService(clock=None)
    assert isinstance(svc.ledger, LedgerService)


# -- Service: event & record building ----------------------------------------


def test_event_factory_stamps_clock():
    svc = LifecycleService(clock=_fixed_clock())
    event = svc.event(E.REGISTERED, actor="mint", note="genesis")
    assert event.event_type is E.REGISTERED
    assert event.actor == "mint"
    assert event.occurred_at == datetime(2026, 8, 5, 9, 30, 0, tzinfo=UTC)


def test_event_factory_clockless_omits_timestamp():
    svc = LifecycleService(clock=None)
    assert svc.event(E.REGISTERED).occurred_at is None


def test_build_valid_history():
    svc = LifecycleService(clock=None)
    events = [
        svc.event(E.REGISTERED),
        svc.event(E.IN_USE),
        svc.event(E.COLLECTED),
        svc.event(E.ASSESSED),
        svc.event(E.RECYCLED),
        svc.event(E.DISPOSED),
    ]
    record = svc.build("ET-PP-0001", events)
    assert record.is_valid is True
    assert record.event_count == 6
    assert record.current_state == "disposed"
    assert record.engine_version == "1.0.0"
    assert record.rules_version == "1.0.0"


def test_build_invalid_history_is_data_not_exception():
    svc = LifecycleService(clock=None)
    record = svc.build("ET-PP-0001", [svc.event(E.IN_USE)])
    assert record.is_valid is False


def test_build_is_deterministic_when_clockless():
    """Clockless records serialize byte-identically across builds."""
    svc = LifecycleService(clock=None)
    events = [svc.event(E.REGISTERED), svc.event(E.IN_USE)]
    a = svc.build("dev", events)
    b = svc.build("dev", events)
    assert a.to_json() == b.to_json()


# -- Service: append & can_append --------------------------------------------


def test_append_extends_and_revalidates():
    svc = LifecycleService(clock=None)
    record = svc.build("dev", [svc.event(E.REGISTERED)])
    extended = svc.append(record, svc.event(E.IN_USE))
    assert extended.event_count == 2
    assert extended.is_valid is True
    assert extended.current_state == "in_use"


def test_append_illegal_transition_marks_invalid():
    svc = LifecycleService(clock=None)
    record = svc.build("dev", [svc.event(E.REGISTERED)])
    bad = svc.append(record, svc.event(E.ASSESSED))
    assert bad.is_valid is False


def test_can_append_predicate():
    svc = LifecycleService(clock=None)
    record = svc.build("dev", [svc.event(E.REGISTERED)])
    assert svc.can_append(record, svc.event(E.IN_USE)) is True
    assert svc.can_append(record, svc.event(E.DISPOSED)) is False


def test_append_does_not_mutate_original():
    svc = LifecycleService(clock=None)
    record = svc.build("dev", [svc.event(E.REGISTERED)])
    svc.append(record, svc.event(E.IN_USE))
    assert record.event_count == 1


# -- Service: ledger integration through the backend abstraction (M3.2) ------


def test_ledger_integration_reports_absence():
    svc = LifecycleService(clock=None)
    assert svc.anchored_ids() == []
    assert svc.is_anchored("ET-PP-NONE") is False
    assert svc.anchored_chain("ET-PP-NONE") is None


def test_ledger_integration_sees_anchored_chain():
    """A chain anchored via the ledger is visible through the lifecycle façade."""
    ledger = LedgerService(backend=MockEthereumLedgerBackend(), clock=None)
    svc = LifecycleService(ledger=ledger, clock=None)
    chain = _anchor_a_chain(ledger)
    chain_id = ledger.chain_id(chain)
    assert svc.is_anchored(chain_id) is True
    assert svc.anchored_ids() == [chain_id]
    assert svc.anchored_chain(chain_id) == chain


# -- Helpers -----------------------------------------------------------------


def _anchor_a_chain(ledger: LedgerService):
    """Build and persist a minimal ledger chain (offline hand-built artefacts)."""
    from device_ai.integrity.models import (
        PassportIntegrityReport,
        ValidationStatus,
    )
    from device_ai.passport.models import (
        Classification,
        ConfidenceSummary,
        DecisionSummary,
        DeviceIdentity,
        DevicePassport,
        EnvironmentalSummary,
        FingerprintSummary,
        MaterialSummary,
        PassportMetadata,
    )
    from device_ai.trust.models import PassportTrustReport, TrustLevel

    passport = DevicePassport(
        passport_id="ET-PP-0000000001",
        passport_version="1.0.0",
        eco_id="ET-2026-XYZ",
        device_identity=DeviceIdentity("Dell", "XPS", "SN1", "", ""),
        classification=Classification("laptop", 0.9, False),
        decision_summary=DecisionSummary("recycle", "high", 0.8, "R1", 1),
        material_summary=MaterialSummary(5, 100.0, 80.0, 5.0, 0.7),
        environmental_summary=EnvironmentalSummary(
            2.0, 50.0, 10.0, 0.08, 0.01, 0.6, 0.5, 0.7
        ),
        fingerprint_summary=FingerprintSummary("f" * 64, 512, "clip", "1.0", "cosine"),
        confidence_summary=ConfidenceSummary(0.9, 0.8, 0.7, 0.75, 0.8),
        metadata=PassportMetadata(
            "1.0", "1.0", "1.0", "1.0", "1.0", "1.0", "1.0", "1.0", "1.0", 1
        ),
        reasoning=(),
        warnings=(),
    )
    integrity = PassportIntegrityReport(
        passport_id="ET-PP-0000000001",
        status=ValidationStatus.VALID,
        canonical_hash="b" * 64,
        hash_algorithm="sha256",
        schema_version="1.0.0",
        passport_version="1.0.0",
        checked_sections=(),
        warnings=(),
        errors=(),
        rules_version="1.0.0",
        engine_version="1.0.0",
    )
    trust = PassportTrustReport(
        passport_id="ET-PP-0000000001",
        trust_score=0.85,
        trust_level=TrustLevel.HIGH,
        identity_confidence=0.9,
        evidence_consistency=0.8,
        decision_confidence=0.75,
        integrity_confidence=1.0,
        axes=(),
        reasoning=(),
        warnings=(),
        engine_version="1.0.0",
        rules_version="1.0.0",
    )
    chain = ledger.genesis(passport, integrity, trust)
    ledger.save(chain)
    return chain
