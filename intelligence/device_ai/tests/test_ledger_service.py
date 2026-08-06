"""End-to-end tests for the blockchain ledger service (milestone M3.1).

Exercises :class:`LedgerService` by actually running the upstream engines
(recoverability, component, material, environmental, decision-knowledge,
circular), composing a real :class:`DevicePassport` via the passport service,
validating it via the integrity service, scoring it via the trust service, then
chaining the resulting records into a verifiable blockchain. Only the external
catalogues/schema/rule-sets/config are read from disk; there is no fusion run
and no models.

Asserts the service loads the shipped config once, chains records
deterministically, links blocks by previous-hash, verifies integrity, detects
tampering, honours the injected clock, and exposes no networking/consensus/
monetary surface — mirroring the M2.5 trust service test structure.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from device_ai.circular import CircularService
from device_ai.components import ComponentService
from device_ai.decision import DecisionService
from device_ai.environmental import EnvironmentalService
from device_ai.fingerprint.models import DeviceFingerprint
from device_ai.fusion.models import (
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.integrity import IntegrityService
from device_ai.ledger import Blockchain, LedgerRecord, LedgerService
from device_ai.materials import MaterialService
from device_ai.passport import PassportService
from device_ai.recoverability import RecoverabilityService
from device_ai.trust import TrustService

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _service(*, with_clock=False, config=None):
    return LedgerService(
        config=config,
        clock=(lambda: _CLOCK) if with_clock else None,
    )


def _resolved(attribute, value, confidence=0.9):
    return ResolvedAttribute(
        attribute=attribute,
        value=value,
        confidence=confidence,
        sources=(EvidenceKind.DETECTION,),
    )


def _context(*, model="XPS-13", serial="SN123"):
    return DeviceContext(
        eco_id="ET-2026-0000ABCD",
        fingerprint="f" * 64,
        attributes=(
            _resolved(FusionAttribute.DEVICE_TYPE, "laptop"),
            _resolved(FusionAttribute.MODEL, model),
            _resolved(FusionAttribute.SERIAL_NUMBER, serial),
        ),
        confidence=0.9,
        evidence=(),
        conflicts=(),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _fingerprint():
    return DeviceFingerprint(
        eco_id="ET-2026-0000ABCD",
        fingerprint="f" * 64,
        embedding=(0.1, 0.2, 0.3),
        dimension=3,
        encoder_name="CLIP",
        encoder_version="1.0",
        metric="cosine",
        created_at=_CLOCK,
    )


def _artifacts(*, model="XPS-13", serial="SN123"):
    """Run the real upstream engines and return (passport, integrity, trust)."""
    context = _context(model=model, serial=serial)
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    materials = MaterialService(clock=None).analyze(context, recoverability, components)
    environmental = EnvironmentalService(clock=None).analyze(
        context, recoverability, components, materials
    )
    knowledge = DecisionService(clock=None).analyze(
        context, recoverability, components, materials, environmental
    )
    decision = CircularService(clock=None).decide(
        context, knowledge, recoverability, environmental
    )
    passport = PassportService(clock=None).build(
        context, decision, materials, environmental, _fingerprint()
    )
    integrity = IntegrityService(clock=None).validate(passport)
    trust = TrustService(clock=None).assess(passport, integrity, knowledge, decision)
    return passport, integrity, trust


# --- Record creation -------------------------------------------------------


def test_create_record_from_real_artifacts():
    passport, integrity, trust = _artifacts()
    record = _service().create_record(passport, integrity, trust)
    assert isinstance(record, LedgerRecord)
    assert record.passport_id == passport.passport_id
    assert record.integrity_hash == integrity.canonical_hash
    assert record.trust_score == trust.trust_score
    assert record.trust_level == trust.trust_level.value


# --- Genesis and append ----------------------------------------------------


def test_genesis_builds_single_block_chain():
    passport, integrity, trust = _artifacts()
    chain = _service().genesis(passport, integrity, trust)
    assert isinstance(chain, Blockchain)
    assert chain.block_count == 1
    assert chain.is_valid
    assert chain.blocks[0].index == 0
    assert chain.blocks[0].previous_hash == "0" * 64


def test_append_links_and_verifies():
    service = _service()
    a1 = _artifacts(model="XPS-13", serial="SN001")
    a2 = _artifacts(model="XPS-15", serial="SN002")
    chain = service.genesis(*a1)
    chain = service.append(chain, *a2)
    assert chain.block_count == 2
    assert chain.is_valid
    # The second block links to the first.
    assert chain.blocks[1].previous_hash != "0" * 64
    assert chain.blocks[1].index == 1


def test_append_record_lower_level_api():
    service = _service()
    passport, integrity, trust = _artifacts()
    chain = service.genesis(passport, integrity, trust)
    record = service.create_record(*_artifacts(model="ThinkPad", serial="SN999"))
    chain = service.append_record(chain, record)
    assert chain.block_count == 2
    assert chain.is_valid


# --- build_chain -----------------------------------------------------------


def test_build_chain_from_multiple_records():
    service = _service()
    records = [
        service.create_record(*_artifacts(model=f"Model{i}", serial=f"SN{i}"))
        for i in range(3)
    ]
    chain = service.build_chain(records)
    assert chain.block_count == 3
    assert chain.is_valid
    assert [b.index for b in chain.blocks] == [0, 1, 2]


def test_build_chain_empty_is_valid():
    chain = _service().build_chain([])
    assert chain.block_count == 0
    assert chain.is_valid


# --- Verification and tamper detection -------------------------------------


def test_verify_intact_chain():
    service = _service()
    records = [
        service.create_record(*_artifacts(model=f"M{i}", serial=f"S{i}"))
        for i in range(2)
    ]
    chain = service.build_chain(records)
    assert service.verify(chain)


def test_verify_detects_tampered_record():
    service = _service()
    records = [
        service.create_record(*_artifacts(model=f"M{i}", serial=f"S{i}"))
        for i in range(2)
    ]
    chain = service.build_chain(records)
    # Tamper with the trust score of the genesis block's record.
    tampered_record = replace(chain.blocks[0].record, trust_score=0.0)
    tampered_block = replace(chain.blocks[0], record=tampered_record)
    tampered_chain = replace(chain, blocks=(tampered_block, *chain.blocks[1:]))
    assert not service.verify(tampered_chain)


# --- Determinism -----------------------------------------------------------


def test_build_chain_is_deterministic():
    service = _service()  # clock=None so no timestamp variation
    records = [
        LedgerRecord(
            passport_id=f"ET-PP-{i:012d}",
            integrity_hash=str(i) * 64,
            trust_score=0.5,
            trust_level="medium",
            passport_version="1.0.0",
            integrity_engine_version="1.0.0",
            trust_engine_version="1.0.0",
        )
        for i in range(3)
    ]
    first = service.build_chain(records)
    second = service.build_chain(records)
    assert first.to_json() == second.to_json()


def test_chain_stable_across_service_instances():
    records = [
        LedgerRecord(
            passport_id="ET-PP-000000000001",
            integrity_hash="a" * 64,
            trust_score=0.9,
            trust_level="high",
            passport_version="1.0.0",
            integrity_engine_version="1.0.0",
            trust_engine_version="1.0.0",
        )
    ]
    first = _service().build_chain(records)
    second = _service().build_chain(records)
    assert first.to_json() == second.to_json()


# --- Provenance & clock ----------------------------------------------------


def test_service_stamps_optional_clock():
    passport, integrity, trust = _artifacts()
    with_clock = _service(with_clock=True).genesis(passport, integrity, trust)
    assert with_clock.created_at == _CLOCK
    assert with_clock.blocks[0].header.timestamp == _CLOCK
    assert with_clock.blocks[0].record.created_at == _CLOCK
    without_clock = _service().genesis(passport, integrity, trust)
    assert without_clock.created_at is None
    assert without_clock.blocks[0].header.timestamp is None


def test_service_loads_shipped_config_by_default():
    service = _service()
    assert service.config.hash_algorithm == "sha256"
    assert service.config.blockchain_version


# --- No forbidden surface --------------------------------------------------


def test_chain_exposes_no_networking_or_consensus_field():
    passport, integrity, trust = _artifacts()
    payload = _service().genesis(passport, integrity, trust).to_dict()
    forbidden = {
        "nonce",
        "difficulty",
        "peers",
        "consensus",
        "signature",
        "gas",
        "miner",
        "proof_of_work",
    }
    assert forbidden.isdisjoint(payload)
    # And none appear on a block or record either.
    block_payload = payload["blocks"][0]
    assert forbidden.isdisjoint(block_payload)
    assert forbidden.isdisjoint(block_payload["record"])


def test_chain_is_immutable():
    passport, integrity, trust = _artifacts()
    chain = _service().genesis(passport, integrity, trust)
    with pytest.raises((AttributeError, TypeError)):
        chain.is_valid = False  # type: ignore[misc]
