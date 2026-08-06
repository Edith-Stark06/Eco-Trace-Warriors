"""Unit tests for the blockchain ledger builder (milestone M3.1).

Exercises :class:`LedgerBuilder`: deterministic record/block/chain construction,
previous-hash linking, record-hash matching, genesis-sentinel handling, and
chain verification (detecting tampering with block contents or order). Mirrors
the M2.5 trust-engine and M2.4 integrity-validator test structure.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from device_ai.exceptions import LedgerError
from device_ai.ledger.builder import LedgerBuilder
from device_ai.ledger.config import GENESIS_PREVIOUS_HASH, LedgerConfig
from device_ai.ledger.models import Block, LedgerRecord

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _builder(*, hash_algorithm="sha256"):
    return LedgerBuilder(
        LedgerConfig(hash_algorithm=hash_algorithm, blockchain_version="1.0.0")
    )


def _record(*, passport_id="ET-PP-0000000001", trust_score=0.9, trust_level="high"):
    return LedgerRecord(
        passport_id=passport_id,
        integrity_hash="a" * 64,
        trust_score=trust_score,
        trust_level=trust_level,
        passport_version="1.0.0",
        integrity_engine_version="1.0.0",
        trust_engine_version="1.0.0",
        created_at=None,
    )


# --- Record and block creation ---------------------------------------------


def test_create_record_snapshots_three_reports():
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
        passport_id="ET-PP-ABC",
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
        passport_id="ET-PP-ABC",
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
        passport_id="ET-PP-ABC",
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
    builder = _builder()
    record = builder.create_record(passport, integrity, trust, created_at=_CLOCK)
    assert record.passport_id == "ET-PP-ABC"
    assert record.integrity_hash == "b" * 64
    assert record.trust_score == 0.85
    assert record.trust_level == "high"
    assert record.created_at == _CLOCK


def test_create_block_genesis_uses_sentinel():
    builder = _builder()
    block = builder.create_block(_record(), None, timestamp=_CLOCK)
    assert block.index == 0
    assert block.previous_hash == GENESIS_PREVIOUS_HASH
    assert len(block.record_hash) == 64


def test_create_block_chains_to_previous():
    builder = _builder()
    b0 = builder.create_block(_record(passport_id="ET-PP-0001"), None)
    b1 = builder.create_block(_record(passport_id="ET-PP-0002"), b0)
    assert b1.index == 1
    assert b1.previous_hash != GENESIS_PREVIOUS_HASH
    # The previous_hash should be the hash of b0's header.
    expected = builder._hash(b0.header.to_json())
    assert b1.previous_hash == expected


def test_record_hash_is_deterministic():
    builder = _builder()
    record = _record()
    hash1 = builder._hash_record(record)
    hash2 = builder._hash_record(record)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_different_records_have_different_hashes():
    builder = _builder()
    r1 = _record(passport_id="ET-PP-0001")
    r2 = _record(passport_id="ET-PP-0002")
    assert builder._hash_record(r1) != builder._hash_record(r2)


# --- Chain creation and verification ---------------------------------------


def test_create_chain_empty_is_valid():
    chain = _builder().create_chain([], created_at=None)
    assert chain.block_count == 0
    assert chain.is_valid
    assert chain.blocks == ()


def test_create_chain_single_block_is_valid():
    builder = _builder()
    block = builder.create_block(_record(), None)
    chain = builder.create_chain([block])
    assert chain.block_count == 1
    assert chain.is_valid


def test_create_chain_three_blocks_validates():
    builder = _builder()
    r1, r2, r3 = (
        _record(passport_id="P1"),
        _record(passport_id="P2"),
        _record(passport_id="P3"),
    )
    b0 = builder.create_block(r1, None)
    b1 = builder.create_block(r2, b0)
    b2 = builder.create_block(r3, b1)
    chain = builder.create_chain([b0, b1, b2])
    assert chain.is_valid
    assert chain.block_count == 3


def test_verify_chain_detects_wrong_index():
    from dataclasses import replace

    builder = _builder()
    b0 = builder.create_block(_record(), None)
    b1_bad = replace(b0, header=replace(b0.header, index=99))
    assert not builder.verify_chain([b0, b1_bad])


def test_verify_chain_detects_tampered_record():
    from dataclasses import replace

    builder = _builder()
    r1 = _record(passport_id="P1", trust_score=0.9)
    r2 = _record(passport_id="P2", trust_score=0.6)
    b0 = builder.create_block(r1, None)
    b1 = builder.create_block(r2, b0)
    # Tamper with the record in b1 after hashing.
    r2_tampered = replace(r2, trust_score=1.0)
    b1_tampered = replace(b1, record=r2_tampered)
    assert not builder.verify_chain([b0, b1_tampered])


def test_verify_chain_detects_broken_previous_link():
    from dataclasses import replace

    builder = _builder()
    b0 = builder.create_block(_record(passport_id="P1"), None)
    b1 = builder.create_block(_record(passport_id="P2"), b0)
    # Break the previous-hash link.
    b1_bad = replace(b1, header=replace(b1.header, previous_hash="x" * 64))
    assert not builder.verify_chain([b0, b1_bad])


def test_append_block_returns_new_chain_with_one_more_block():
    builder = _builder()
    chain0 = builder.create_chain(
        [builder.create_block(_record(passport_id="P1"), None)]
    )
    chain1 = builder.append_block(chain0, _record(passport_id="P2"))
    assert chain1.block_count == 2
    assert chain1.is_valid
    assert chain1.blocks[1].index == 1


# --- Hash algorithm configuration ------------------------------------------


def test_unsupported_hash_algorithm_raises():
    builder = _builder(hash_algorithm="not_real")
    with pytest.raises(LedgerError):
        builder.create_block(_record(), None)


def test_sha3_256_works():
    builder = _builder(hash_algorithm="sha3_256")
    block = builder.create_block(_record(), None)
    assert len(block.record_hash) == 64


# --- Determinism -----------------------------------------------------------


def test_same_records_build_identical_chains():
    builder = _builder()
    records = [_record(passport_id=f"P{i}") for i in range(3)]

    def _build() -> Block:
        blocks: list[Block] = []
        prev: Block | None = None
        for record in records:
            block = builder.create_block(record, prev)
            blocks.append(block)
            prev = block
        return builder.create_chain(blocks)

    # Without timestamps the two independently-built chains are byte-identical.
    assert _build().to_json() == _build().to_json()


def test_chain_json_deterministic():
    builder = _builder()
    block = builder.create_block(_record(), None)
    chain = builder.create_chain([block])
    json1 = chain.to_json()
    json2 = chain.to_json()
    assert json1 == json2
    parsed = json.loads(json1)
    assert list(parsed) == sorted(parsed)
