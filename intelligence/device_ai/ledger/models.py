"""Blockchain ledger domain models (milestone M3.1).

The Blockchain Ledger Core is an **immutable record assembler**, not a
distributed consensus system. It consumes the three upstream artefacts the
passport pipeline already produced — the immutable
:class:`~device_ai.passport.models.DevicePassport` (M2.3), its
:class:`~device_ai.integrity.models.PassportIntegrityReport` (M2.4), and its
:class:`~device_ai.trust.models.PassportTrustReport` (M2.5) — and emits a
deterministic, tamper-evident :class:`Blockchain` that chains those records
together via cryptographic hashes.

The value objects here are the vocabulary of that ledger:

* :class:`LedgerRecord` — one immutable record capturing the passport id, the
  integrity hash, the trust score/level, and provenance (timestamp and engine
  version). It is the **payload** a block carries.
* :class:`BlockHeader` — the deterministic metadata of one block: its index,
  timestamp, the SHA-256 hash of the previous block's header (the chain link),
  and the SHA-256 hash of this block's record payload (the integrity anchor).
* :class:`Block` — one immutable block: its header and its single ledger record.
  A block is the atomic unit the chain is built from.
* :class:`Blockchain` — the immutable, ordered chain: its blocks, the chain
  version, and verification metadata (whether the chain is structurally valid,
  the number of blocks, and an optional timestamp). It is the final artefact
  the ledger service produces.

Every object is a frozen, slotted dataclass with deterministic ``to_dict`` and
``to_json`` serialization, so the same inputs always yield byte-identical
output (modulo optional timestamps). There is no proof-of-work, no consensus,
no networking, no persistence, no smart contracts, and no digital signatures —
those are out of scope for M3.1. The ledger is a **local, deterministic
data structure** that provides tamper-evident history via hash-chaining.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "Block",
    "BlockHeader",
    "Blockchain",
    "LedgerRecord",
]


@dataclass(frozen=True, slots=True)
class LedgerRecord:
    """One immutable ledger record capturing passport provenance and verdicts.

    The payload a :class:`Block` carries. It is a **snapshot** of the three
    upstream reports' key outcomes: the passport id (the device identity
    anchor), the integrity hash (the passport's canonical anchor), the trust
    score and level (the trustworthiness verdict), and provenance (when the
    record was created and which engines produced the upstream reports).

    Attributes:
        passport_id: The id of the device passport this record anchors.
        integrity_hash: The canonical SHA-256 hex digest from the integrity
            report (the passport's tamper-evident anchor).
        trust_score: The normalized ``[0, 1]`` trust score from the trust
            report.
        trust_level: The trust level wire value (``high`` / ``medium`` /
            ``low`` / ``untrusted``).
        passport_version: The passport's structural version, echoed for the
            consumer.
        integrity_engine_version: Version of the integrity engine that
            validated the passport.
        trust_engine_version: Version of the trust engine that assessed it.
        created_at: UTC timestamp the record was created (``None`` when the
            service was constructed without a clock).
    """

    passport_id: str
    integrity_hash: str
    trust_score: float
    trust_level: str
    passport_version: str
    integrity_engine_version: str
    trust_engine_version: str
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the ledger record.

        The keys are emitted in a fixed, logical order, so the mapping is a
        deterministic function of the inputs (the only source of variation is
        the optional ``created_at`` timestamp).

        Returns:
            A plain ``dict`` with the passport id, integrity hash, trust
            score/level, provenance versions and an ISO-8601 ``created_at``
            (or ``None``).
        """
        return {
            "passport_id": self.passport_id,
            "integrity_hash": self.integrity_hash,
            "trust_score": self.trust_score,
            "trust_level": self.trust_level,
            "passport_version": self.passport_version,
            "integrity_engine_version": self.integrity_engine_version,
            "trust_engine_version": self.trust_engine_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the ledger record.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same record always serializes to the exact
        same bytes. Because :meth:`to_dict` is a pure function of the inputs,
        the only source of variation is the optional ``created_at`` timestamp.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )


@dataclass(frozen=True, slots=True)
class BlockHeader:
    """The deterministic metadata of one block in the chain.

    The header is what links blocks together: each header carries the SHA-256
    hash of the previous block's header, forming the tamper-evident chain. The
    header also carries the hash of this block's record payload, so tampering
    with either the chain or the payload is detectable.

    Attributes:
        index: The zero-based position of this block in the chain (the genesis
            block is index ``0``).
        timestamp: UTC timestamp the block was created (``None`` when the
            builder was constructed without a clock).
        previous_hash: SHA-256 hex digest of the previous block's header
            (deterministically serialized), or the genesis sentinel
            (``"0" * 64``) when this is the genesis block.
        record_hash: SHA-256 hex digest of this block's ledger record
            (deterministically serialized).
    """

    index: int
    timestamp: datetime | None
    previous_hash: str
    record_hash: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the block header.

        The keys are emitted in a fixed, logical order, so the mapping is a
        deterministic function of the inputs.

        Returns:
            A plain ``dict`` with the index, an ISO-8601 timestamp (or
            ``None``), the previous hash and the record hash.
        """
        return {
            "index": self.index,
            "timestamp": (
                self.timestamp.isoformat() if self.timestamp is not None else None
            ),
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the block header.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same header always serializes to the exact
        same bytes (suitable for hashing). Because :meth:`to_dict` is itself a
        pure function of the inputs, the only source of variation is the
        optional ``timestamp``.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )


@dataclass(frozen=True, slots=True)
class Block:
    """One immutable block: a header and its single ledger record.

    The atomic unit the blockchain is built from. Each block carries one ledger
    record (the payload) and one header (the chain link and integrity anchor).
    Blocks are chained together via the ``previous_hash`` in the header.

    Attributes:
        header: The block's :class:`BlockHeader` (the chain link).
        record: The block's :class:`LedgerRecord` (the payload).
    """

    header: BlockHeader
    record: LedgerRecord

    @property
    def index(self) -> int:
        """Return the block's index in the chain."""
        return self.header.index

    @property
    def previous_hash(self) -> str:
        """Return the SHA-256 hash of the previous block's header."""
        return self.header.previous_hash

    @property
    def record_hash(self) -> str:
        """Return the SHA-256 hash of this block's record."""
        return self.header.record_hash

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the block.

        The keys are emitted in a fixed, logical order, so the mapping is a
        deterministic function of the inputs.

        Returns:
            A plain ``dict`` with the header and record as nested mappings.
        """
        return {
            "header": self.header.to_dict(),
            "record": self.record.to_dict(),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the block.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same block always serializes to the exact
        same bytes.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )


@dataclass(frozen=True, slots=True)
class Blockchain:
    """The immutable, ordered blockchain: blocks chained by cryptographic hashes.

    The final artefact the ledger service produces. It is a **deterministic
    data structure** — given the same passport/integrity/trust inputs in the
    same order, the builder always produces the same chain. The chain is
    tamper-evident: any modification to a block or its order invalidates the
    subsequent hashes, which is detectable via :meth:`is_valid`.

    Attributes:
        blocks: The ordered blocks, from genesis (index ``0``) to the most
            recent.
        version: Semantic version of the blockchain structure.
        is_valid: Whether the chain passes structural validation (every block's
            ``previous_hash`` matches the prior block's header hash, every
            block's ``record_hash`` matches its record's canonical hash, and
            block indices are sequential starting from ``0``).
        block_count: Number of blocks in the chain.
        created_at: UTC timestamp the chain was assembled (``None`` when the
            service was constructed without a clock).
    """

    blocks: tuple[Block, ...]
    version: str
    is_valid: bool
    block_count: int
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the blockchain.

        The keys are emitted in a fixed, logical order, so the mapping is a
        deterministic function of the inputs.

        Returns:
            A plain ``dict`` with the ordered blocks, version, validation
            status, block count and an ISO-8601 ``created_at`` (or ``None``).
        """
        return {
            "blocks": [block.to_dict() for block in self.blocks],
            "version": self.version,
            "is_valid": self.is_valid,
            "block_count": self.block_count,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the blockchain.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same chain always serializes to the exact
        same bytes.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )
