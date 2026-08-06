"""Unit tests for the blockchain ledger domain models (milestone M3.1).

Exercises the four frozen, slotted value objects — :class:`LedgerRecord`,
:class:`BlockHeader`, :class:`Block` and :class:`Blockchain` — asserting their
immutability, their deterministic ``to_dict``/``to_json`` serialization, the
convenience properties on :class:`Block`, and that they expose no networking,
consensus or monetary surface. Mirrors the M2.5 trust and M2.4 integrity model
test structure.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from device_ai.ledger.models import Block, Blockchain, BlockHeader, LedgerRecord

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _record(*, created_at=None):
    return LedgerRecord(
        passport_id="ET-PP-0000000000AB",
        integrity_hash="a" * 64,
        trust_score=0.9,
        trust_level="high",
        passport_version="1.0.0",
        integrity_engine_version="1.0.0",
        trust_engine_version="1.0.0",
        created_at=created_at,
    )


def _header(*, index=0, timestamp=None, previous_hash="0" * 64, record_hash="b" * 64):
    return BlockHeader(
        index=index,
        timestamp=timestamp,
        previous_hash=previous_hash,
        record_hash=record_hash,
    )


def _block(*, index=0):
    return Block(header=_header(index=index), record=_record())


# --- LedgerRecord ----------------------------------------------------------


def test_record_to_dict_has_fixed_key_order_and_values():
    record = _record(created_at=_CLOCK)
    payload = record.to_dict()
    assert list(payload) == [
        "passport_id",
        "integrity_hash",
        "trust_score",
        "trust_level",
        "passport_version",
        "integrity_engine_version",
        "trust_engine_version",
        "created_at",
    ]
    assert payload["passport_id"] == "ET-PP-0000000000AB"
    assert payload["created_at"] == _CLOCK.isoformat()


def test_record_created_at_none_serializes_to_none():
    assert _record().to_dict()["created_at"] is None


def test_record_to_json_is_canonical_and_sorted():
    record = _record(created_at=_CLOCK)
    text = record.to_json()
    # Compact separators, sorted keys.
    assert ", " not in text
    parsed = json.loads(text)
    assert parsed["trust_level"] == "high"
    assert list(parsed) == sorted(parsed)


def test_record_is_immutable():
    record = _record()
    with pytest.raises((AttributeError, TypeError)):
        record.trust_score = 0.1  # type: ignore[misc]


def test_record_exposes_no_monetary_or_network_field():
    payload = _record(created_at=_CLOCK).to_dict()
    forbidden = {
        "price",
        "value_usd",
        "cost",
        "currency",
        "signature",
        "nonce",
        "peer",
        "host",
        "gas",
    }
    assert forbidden.isdisjoint(payload)


# --- BlockHeader -----------------------------------------------------------


def test_header_to_dict_has_fixed_key_order():
    header = _header(index=2, timestamp=_CLOCK)
    payload = header.to_dict()
    assert list(payload) == ["index", "timestamp", "previous_hash", "record_hash"]
    assert payload["index"] == 2
    assert payload["timestamp"] == _CLOCK.isoformat()


def test_header_timestamp_none_serializes_to_none():
    assert _header().to_dict()["timestamp"] is None


def test_header_to_json_deterministic():
    a = _header(index=1, timestamp=_CLOCK).to_json()
    b = _header(index=1, timestamp=_CLOCK).to_json()
    assert a == b


def test_header_is_immutable():
    header = _header()
    with pytest.raises((AttributeError, TypeError)):
        header.index = 9  # type: ignore[misc]


# --- Block -----------------------------------------------------------------


def test_block_convenience_properties_delegate_to_header():
    block = Block(
        header=_header(index=5, previous_hash="c" * 64, record_hash="d" * 64),
        record=_record(),
    )
    assert block.index == 5
    assert block.previous_hash == "c" * 64
    assert block.record_hash == "d" * 64


def test_block_to_dict_nests_header_and_record():
    block = _block()
    payload = block.to_dict()
    assert set(payload) == {"header", "record"}
    assert payload["header"]["index"] == 0
    assert payload["record"]["trust_level"] == "high"


def test_block_is_immutable():
    block = _block()
    with pytest.raises((AttributeError, TypeError)):
        block.record = _record()  # type: ignore[misc]


# --- Blockchain ------------------------------------------------------------


def test_chain_to_dict_has_fixed_key_order():
    chain = Blockchain(
        blocks=(_block(index=0),),
        version="1.0.0",
        is_valid=True,
        block_count=1,
        created_at=_CLOCK,
    )
    payload = chain.to_dict()
    assert list(payload) == [
        "blocks",
        "version",
        "is_valid",
        "block_count",
        "created_at",
    ]
    assert payload["block_count"] == 1
    assert len(payload["blocks"]) == 1


def test_chain_empty_serializes_cleanly():
    chain = Blockchain(
        blocks=(), version="1.0.0", is_valid=True, block_count=0, created_at=None
    )
    payload = json.loads(chain.to_json())
    assert payload["blocks"] == []
    assert payload["block_count"] == 0
    assert payload["created_at"] is None


def test_chain_is_immutable():
    chain = Blockchain(
        blocks=(), version="1.0.0", is_valid=True, block_count=0, created_at=None
    )
    with pytest.raises((AttributeError, TypeError)):
        chain.is_valid = False  # type: ignore[misc]


def test_chain_json_round_trips_keys():
    chain = Blockchain(
        blocks=(_block(index=0), _block(index=1)),
        version="1.0.0",
        is_valid=True,
        block_count=2,
        created_at=_CLOCK,
    )
    payload = json.loads(chain.to_json())
    assert payload["version"] == "1.0.0"
    assert payload["is_valid"] is True
    assert len(payload["blocks"]) == 2
