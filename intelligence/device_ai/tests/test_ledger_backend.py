"""Shared test contract for the ledger backend implementations (M3.2).

Exercises the :class:`~device_ai.ledger.backend.LedgerBackend` protocol across
all three shipped implementations — :class:`MemoryLedgerBackend`,
:class:`MockFabricLedgerBackend`, :class:`MockEthereumLedgerBackend` — asserting
that each satisfies the protocol, persists chains under the service-assigned id,
returns a :class:`~device_ai.ledger.backend.LedgerReceipt` with backend-specific
metadata, and supports read/exists/list_ids round-trips. Mirrors the
``test_repository.py`` shared-contract pattern for the fingerprint backends.
"""

from __future__ import annotations

import pytest

from device_ai.ledger import (
    LedgerBackend,
    LedgerService,
    MemoryLedgerBackend,
    MockEthereumLedgerBackend,
    MockFabricLedgerBackend,
)


@pytest.fixture(params=["memory", "mock_fabric", "mock_ethereum"])
def backend(request: pytest.FixtureRequest) -> LedgerBackend:
    """Yield each backend implementation so tests run against all three."""
    if request.param == "memory":
        return MemoryLedgerBackend()
    if request.param == "mock_fabric":
        return MockFabricLedgerBackend()
    return MockEthereumLedgerBackend()


def test_all_implementations_satisfy_the_protocol(backend):
    """Each concrete backend is a structural :class:`LedgerBackend`."""
    assert isinstance(backend, LedgerBackend)


def test_write_then_read_round_trips(backend):
    """A written chain is returned unchanged by ``read``."""
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    receipt = backend.write(chain_id, chain)
    restored = backend.read(chain_id)
    assert restored == chain
    assert receipt.chain_id == chain_id


def test_read_missing_returns_none(backend):
    """Fetching an unknown chain id returns ``None`` rather than raising."""
    assert backend.read("ET-PP-DEADBEEF") is None


def test_exists_reflects_presence(backend):
    """``exists`` is False before writing and True afterwards."""
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    assert backend.exists(chain_id) is False
    backend.write(chain_id, chain)
    assert backend.exists(chain_id) is True


def test_list_ids_returns_written_ids(backend):
    """``list_ids`` reports every stored chain id."""
    assert backend.list_ids() == []
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    backend.write(chain_id, chain)
    assert backend.list_ids() == [chain_id]


def test_write_overwrites_existing_chain(backend):
    """Writing twice with the same id keeps a single (latest) chain."""
    service = LedgerService(backend=backend, clock=None)
    chain1 = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain1)
    backend.write(chain_id, chain1)
    # Append a block to produce a longer chain.
    chain2 = service.append(chain1, *_sample_artifacts(passport_id="ET-PP-0002"))
    backend.write(chain_id, chain2)
    assert backend.list_ids() == [chain_id]
    assert backend.read(chain_id).block_count == 2


def test_receipt_carries_chain_id_and_backend_name(backend):
    """Every backend returns a receipt with the chain id and its own name."""
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    receipt = backend.write(chain_id, chain)
    assert receipt.chain_id == chain_id
    assert receipt.backend in {"memory", "mock_fabric", "mock_ethereum"}


def test_memory_backend_receipt_metadata():
    """The memory backend records block_count as metadata."""
    backend = MemoryLedgerBackend()
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    receipt = backend.write(chain_id, chain)
    assert receipt.backend == "memory"
    assert receipt.metadata["block_count"] == 1


def test_mock_fabric_backend_receipt_metadata():
    """The mock-Fabric backend records tx_id, channel, block_number."""
    backend = MockFabricLedgerBackend()
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    receipt = backend.write(chain_id, chain)
    assert receipt.backend == "mock_fabric"
    assert "tx_id" in receipt.metadata
    assert receipt.metadata["channel"] == "ecotrace-ledger"
    assert receipt.metadata["block_number"] == 1


def test_mock_ethereum_backend_receipt_metadata():
    """The mock-Ethereum backend records tx_hash, gas_used, nonce, contract."""
    backend = MockEthereumLedgerBackend()
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    receipt = backend.write(chain_id, chain)
    assert receipt.backend == "mock_ethereum"
    assert "tx_hash" in receipt.metadata
    assert receipt.metadata["tx_hash"].startswith("0x")
    assert receipt.metadata["gas_used"] == 21000
    assert receipt.metadata["nonce"] == 1
    assert receipt.metadata["contract"] == "0xEcoTraceLedger"


def test_mock_fabric_transaction_counter_increments():
    """The mock-Fabric backend's tx_id and block_number advance with writes."""
    backend = MockFabricLedgerBackend()
    service = LedgerService(backend=backend, clock=None)
    chain1 = service.genesis(*_sample_artifacts(passport_id="ET-PP-0001"))
    chain2 = service.genesis(*_sample_artifacts(passport_id="ET-PP-0002"))
    receipt1 = backend.write(service.chain_id(chain1), chain1)
    receipt2 = backend.write(service.chain_id(chain2), chain2)
    assert receipt1.metadata["tx_id"] == "fabric-tx-00000001"
    assert receipt2.metadata["tx_id"] == "fabric-tx-00000002"
    assert receipt1.metadata["block_number"] == 1
    assert receipt2.metadata["block_number"] == 2


def test_mock_ethereum_nonce_increments():
    """The mock-Ethereum backend's nonce and block_number advance with writes."""
    backend = MockEthereumLedgerBackend()
    service = LedgerService(backend=backend, clock=None)
    chain1 = service.genesis(*_sample_artifacts(passport_id="ET-PP-0001"))
    chain2 = service.genesis(*_sample_artifacts(passport_id="ET-PP-0002"))
    receipt1 = backend.write(service.chain_id(chain1), chain1)
    receipt2 = backend.write(service.chain_id(chain2), chain2)
    assert receipt1.metadata["nonce"] == 1
    assert receipt2.metadata["nonce"] == 2
    assert receipt1.metadata["block_number"] == 1
    assert receipt2.metadata["block_number"] == 2


def test_mock_ethereum_tx_hash_is_deterministic():
    """The mock-Ethereum backend's tx_hash is the SHA-256 of the chain JSON."""
    backend = MockEthereumLedgerBackend()
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    receipt1 = backend.write(chain_id, chain)
    # Write the same chain again (overwrites, same content).
    receipt2 = backend.write(chain_id, chain)
    # The tx_hash is the same because the chain's canonical JSON is identical.
    assert receipt1.metadata["tx_hash"] == receipt2.metadata["tx_hash"]
    assert receipt1.metadata["tx_hash"].startswith("0x")


def test_service_save_and_load_via_injected_backend():
    """The service's save/load delegate to the injected backend."""
    backend = MemoryLedgerBackend()
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    receipt = service.save(chain)
    assert receipt.chain_id == service.chain_id(chain)
    loaded = service.load(receipt.chain_id)
    assert loaded == chain


def test_service_exists_and_list_ids_via_injected_backend():
    """The service's exists/list_ids delegate to the injected backend."""
    backend = MemoryLedgerBackend()
    service = LedgerService(backend=backend, clock=None)
    chain = service.genesis(*_sample_artifacts())
    chain_id = service.chain_id(chain)
    assert service.exists(chain_id) is False
    service.save(chain)
    assert service.exists(chain_id) is True
    assert service.list_ids() == [chain_id]


# -- Helpers -----------------------------------------------------------------


def _sample_artifacts(*, passport_id="ET-PP-0000000001"):
    """Build a minimal (passport, integrity, trust) tuple for testing.

    Uses hand-built reports so the test suite stays offline (no upstream
    engines, no fusion, no images). The passport id is what the builder hashes
    to derive the chain_id.
    """
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
        passport_id=passport_id,
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
        passport_id=passport_id,
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
        passport_id=passport_id,
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
    return passport, integrity, trust
