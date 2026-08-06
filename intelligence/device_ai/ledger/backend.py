"""Ledger backend abstraction layer (milestone M3.2).

The ledger service depends only on the :class:`LedgerBackend` *protocol*, never
on a concrete store — so the ledger *technology* (in-memory, a mock
Fabric/Ethereum simulation, or a future real Hyperledger Fabric / Ethereum
anchor) can change without touching the domain or service layers (``CLAUDE.md``
→ "persistence abstraction; do not tightly couple to storage").

The service owns chain identity: it computes a stable ``chain_id`` from a chain's
genesis record and passes both to :meth:`LedgerBackend.write`, so each backend is
a pure, technology-flavored key-value store rather than duplicating identity
logic. Every backend returns a :class:`LedgerReceipt` on write, carrying the
``chain_id`` and backend-specific metadata (a Fabric transaction id and channel,
an Ethereum transaction hash and gas, etc.), so callers can correlate a chain
with the backend's write.

Three implementations ship with M3.2 — all **deterministic**, **in-memory** and
free of any real SDK, RPC, networking or persistence:

* :class:`MemoryLedgerBackend` — process-local dict; the default and the one
  used throughout the test suite.
* :class:`MockFabricLedgerBackend` — a stand-in for a Hyperledger Fabric channel
  that emits Fabric-shaped metadata (transaction id, channel, block number).
* :class:`MockEthereumLedgerBackend` — a stand-in for an Ethereum smart contract
  that emits Ethereum-shaped metadata (content-addressed transaction hash, gas
  used, nonce, contract address).

The two mocks exist to prove the abstraction: the service drives all three
identically, differing only in the metadata each records. They deliberately
implement **no** Fabric SDK, chaincode, smart contracts, wallets, certificates,
consensus, Ethereum RPC, networking or persistence — those are out of scope for
M3.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..utils.hashing import hash_bytes

if TYPE_CHECKING:
    from .models import Blockchain

#: Default Fabric channel name recorded in mock-Fabric receipts.
DEFAULT_FABRIC_CHANNEL = "ecotrace-ledger"

#: Default Ethereum contract address recorded in mock-Ethereum receipts.
DEFAULT_ETHEREUM_CONTRACT = "0xEcoTraceLedger"

#: Default simulated gas cost per mock-Ethereum write.
DEFAULT_ETHEREUM_GAS_PER_WRITE = 21000


@dataclass(frozen=True, slots=True)
class LedgerReceipt:
    """Immutable receipt a backend returns after writing a chain.

    Attributes:
        chain_id: The service-assigned identifier of the stored chain.
        backend: The backend identifier that produced this receipt
            (``memory`` / ``mock_fabric`` / ``mock_ethereum``).
        metadata: Backend-specific write details (e.g. a transaction id, block
            number, gas used); an empty mapping when the backend records none.
    """

    chain_id: str
    backend: str
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the receipt.

        Returns:
            A plain ``dict`` with the chain id, backend name and metadata.
        """
        return {
            "chain_id": self.chain_id,
            "backend": self.backend,
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class LedgerBackend(Protocol):
    """Technology-agnostic persistence contract for blockchains.

    The service assigns each chain a stable ``chain_id`` (derived from its
    genesis record) and passes it to :meth:`write`, so implementations never
    re-derive identity. Implementations must be safe to call with unknown ids:
    :meth:`read` returns ``None`` rather than raising when a chain is absent.
    """

    def write(self, chain_id: str, chain: Blockchain) -> LedgerReceipt:
        """Persist ``chain`` under ``chain_id`` (replacing any existing chain).

        Args:
            chain_id: The service-assigned identifier for the chain.
            chain: The :class:`~device_ai.ledger.models.Blockchain` to store.

        Returns:
            A :class:`LedgerReceipt` carrying ``chain_id`` and backend metadata.
        """
        ...

    def read(self, chain_id: str) -> Blockchain | None:
        """Return the blockchain for ``chain_id``, or ``None`` if absent."""
        ...

    def exists(self, chain_id: str) -> bool:
        """Return whether a blockchain is stored for ``chain_id``."""
        ...

    def list_ids(self) -> list[str]:
        """Return all stored chain ids (order is not guaranteed)."""
        ...


class MemoryLedgerBackend:
    """Non-durable, process-local ledger store backed by a dict.

    The default backend, and the one used throughout the test suite. Chains are
    lost when the process exits. It records only the block count as metadata —
    it emulates no particular ledger technology.
    """

    #: The backend identifier recorded on every receipt.
    name = "memory"

    def __init__(self) -> None:
        self._store: dict[str, Blockchain] = {}

    def write(self, chain_id: str, chain: Blockchain) -> LedgerReceipt:
        """Store ``chain`` under ``chain_id`` (last write wins)."""
        self._store[chain_id] = chain
        return LedgerReceipt(
            chain_id=chain_id,
            backend=self.name,
            metadata={"block_count": chain.block_count},
        )

    def read(self, chain_id: str) -> Blockchain | None:
        """Return the blockchain for ``chain_id``, or ``None`` if absent."""
        return self._store.get(chain_id)

    def exists(self, chain_id: str) -> bool:
        """Return whether a blockchain is stored for ``chain_id``."""
        return chain_id in self._store

    def list_ids(self) -> list[str]:
        """Return all stored chain ids."""
        return list(self._store)


class MockFabricLedgerBackend:
    """Deterministic stand-in for a Hyperledger Fabric channel.

    Emits Fabric-shaped receipt metadata (a monotonic transaction id, the
    channel name and a block number) so the abstraction can be exercised against
    a Fabric-like backend **without** any Fabric SDK, chaincode, certificates,
    consensus, networking or persistence. Chains are held in-memory for the
    lifetime of the instance.

    Args:
        channel: The Fabric channel name recorded on every receipt.
    """

    #: The backend identifier recorded on every receipt.
    name = "mock_fabric"

    def __init__(self, *, channel: str = DEFAULT_FABRIC_CHANNEL) -> None:
        self._store: dict[str, Blockchain] = {}
        self._channel = channel
        self._tx_counter = 0

    @property
    def channel(self) -> str:
        """Return the Fabric channel name this backend records."""
        return self._channel

    def write(self, chain_id: str, chain: Blockchain) -> LedgerReceipt:
        """Store ``chain`` and return a Fabric-shaped receipt.

        The transaction id and block number advance with each write, mirroring
        an append-only channel; both are deterministic given the write order.
        """
        self._store[chain_id] = chain
        self._tx_counter += 1
        return LedgerReceipt(
            chain_id=chain_id,
            backend=self.name,
            metadata={
                "tx_id": f"fabric-tx-{self._tx_counter:08d}",
                "channel": self._channel,
                "block_number": self._tx_counter,
                "block_count": chain.block_count,
            },
        )

    def read(self, chain_id: str) -> Blockchain | None:
        """Return the blockchain for ``chain_id``, or ``None`` if absent."""
        return self._store.get(chain_id)

    def exists(self, chain_id: str) -> bool:
        """Return whether a blockchain is stored for ``chain_id``."""
        return chain_id in self._store

    def list_ids(self) -> list[str]:
        """Return all stored chain ids."""
        return list(self._store)


class MockEthereumLedgerBackend:
    """Deterministic stand-in for an Ethereum smart contract.

    Emits Ethereum-shaped receipt metadata (a content-addressed transaction
    hash, a monotonic nonce/block number, gas used and the contract address) so
    the abstraction can be exercised against an Ethereum-like backend **without**
    any Ethereum RPC, smart contract, wallet, digital signature, networking or
    persistence. The transaction hash is the SHA-256 of the chain's canonical
    serialization (hex, ``0x``-prefixed), so it is deterministic and unique per
    chain state. Chains are held in-memory for the lifetime of the instance.

    Args:
        contract: The contract address recorded on every receipt.
        gas_per_write: The simulated gas cost recorded on every write.
    """

    #: The backend identifier recorded on every receipt.
    name = "mock_ethereum"

    def __init__(
        self,
        *,
        contract: str = DEFAULT_ETHEREUM_CONTRACT,
        gas_per_write: int = DEFAULT_ETHEREUM_GAS_PER_WRITE,
    ) -> None:
        self._store: dict[str, Blockchain] = {}
        self._contract = contract
        self._gas_per_write = gas_per_write
        self._nonce = 0

    @property
    def contract(self) -> str:
        """Return the contract address this backend records."""
        return self._contract

    def write(self, chain_id: str, chain: Blockchain) -> LedgerReceipt:
        """Store ``chain`` and return an Ethereum-shaped receipt.

        The transaction hash is the SHA-256 of the chain's canonical JSON
        (deterministic and unique per chain state); the nonce/block number
        advance with each write.
        """
        self._store[chain_id] = chain
        self._nonce += 1
        tx_hash = "0x" + hash_bytes(chain.to_json().encode("utf-8"))
        return LedgerReceipt(
            chain_id=chain_id,
            backend=self.name,
            metadata={
                "tx_hash": tx_hash,
                "block_number": self._nonce,
                "nonce": self._nonce,
                "gas_used": self._gas_per_write,
                "contract": self._contract,
                "block_count": chain.block_count,
            },
        )

    def read(self, chain_id: str) -> Blockchain | None:
        """Return the blockchain for ``chain_id``, or ``None`` if absent."""
        return self._store.get(chain_id)

    def exists(self, chain_id: str) -> bool:
        """Return whether a blockchain is stored for ``chain_id``."""
        return chain_id in self._store

    def list_ids(self) -> list[str]:
        """Return all stored chain ids."""
        return list(self._store)
