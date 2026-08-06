"""Blockchain Ledger Core (milestones M3.1, M3.2).

An internal-only, deterministic **immutable-ledger builder** that consumes the
three upstream artefacts the passport pipeline already produced — the immutable
:class:`~device_ai.passport.models.DevicePassport` (M2.3), its
:class:`~device_ai.integrity.models.PassportIntegrityReport` (M2.4) and its
:class:`~device_ai.trust.models.PassportTrustReport` (M2.5) — and emits a
tamper-evident :class:`Blockchain`: an ordered chain of :class:`Block` objects,
each carrying one :class:`LedgerRecord` payload and one :class:`BlockHeader`
that links it to the previous block via a deterministic SHA-256 hash.

Unlike the M2.3 core (which *assembles* the passport), the M2.4 engine (which
*checks* it) and the M2.5 engine (which *scores* it), the ledger core carries
**no inference and no evidence collection of its own**: it snapshots the three
reports' key outcomes into a record, hashes it, and chains it. Its operational
knobs (hash algorithm, versions, genesis sentinel) live in an external, versioned
YAML/JSON file (loaded by a strict validating loader); its hashing and block
generation are deterministic and its serialization is canonical, so the same
inputs always yield byte-identical output (modulo optional timestamps).

Milestone M3.2 adds the **ledger backend abstraction layer**: a
technology-agnostic :class:`~device_ai.ledger.backend.LedgerBackend` protocol and
three deterministic, in-memory implementations
(:class:`~device_ai.ledger.backend.MemoryLedgerBackend`,
:class:`~device_ai.ledger.backend.MockFabricLedgerBackend`,
:class:`~device_ai.ledger.backend.MockEthereumLedgerBackend`). The
:class:`LedgerService` persists chains through an injected backend, depending
only on the protocol — so the ledger technology can change without touching the
service.

There is no HTTP surface — orchestrating code consumes the :class:`Blockchain`
directly. This core deliberately implements no Hyperledger Fabric, Ethereum,
consensus, proof-of-work, smart-contract, chaincode, wallet, certificate,
digital-signature, networking or persistence concern; those are out of scope for
M3.1/M3.2. It is a local, deterministic, in-memory data structure that provides
tamper-evident, independently verifiable history via hash-chaining, behind a
pluggable backend abstraction.
"""

from __future__ import annotations

from .backend import (
    DEFAULT_ETHEREUM_CONTRACT,
    DEFAULT_ETHEREUM_GAS_PER_WRITE,
    DEFAULT_FABRIC_CHANNEL,
    LedgerBackend,
    LedgerReceipt,
    MemoryLedgerBackend,
    MockEthereumLedgerBackend,
    MockFabricLedgerBackend,
)
from .builder import LedgerBuilder
from .config import (
    DEFAULT_BLOCKCHAIN_VERSION,
    DEFAULT_CONFIG_PATH,
    DEFAULT_HASH_ALGORITHM,
    GENESIS_PREVIOUS_HASH,
    LedgerConfig,
    load_config,
)
from .models import (
    Block,
    Blockchain,
    BlockHeader,
    LedgerRecord,
)
from .service import LedgerService

__all__ = [
    "DEFAULT_BLOCKCHAIN_VERSION",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_ETHEREUM_CONTRACT",
    "DEFAULT_ETHEREUM_GAS_PER_WRITE",
    "DEFAULT_FABRIC_CHANNEL",
    "DEFAULT_HASH_ALGORITHM",
    "GENESIS_PREVIOUS_HASH",
    "Block",
    "BlockHeader",
    "Blockchain",
    "LedgerBackend",
    "LedgerBuilder",
    "LedgerConfig",
    "LedgerReceipt",
    "LedgerRecord",
    "LedgerService",
    "MemoryLedgerBackend",
    "MockEthereumLedgerBackend",
    "MockFabricLedgerBackend",
    "load_config",
]
