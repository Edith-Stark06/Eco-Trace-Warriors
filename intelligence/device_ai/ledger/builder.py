"""Blockchain ledger builder (milestone M3.1).

Deterministic block and chain construction over passport artefacts. The
`LedgerBuilder` consumes the three upstream reports — a
:class:`~device_ai.passport.models.DevicePassport` (M2.3), its
:class:`~device_ai.integrity.models.PassportIntegrityReport` (M2.4), and its
:class:`~device_ai.trust.models.PassportTrustReport` (M2.5) — and emits
deterministic, immutable :class:`~device_ai.ledger.models.Block` and
:class:`~device_ai.ledger.models.Blockchain` artefacts. There is no model, no
inference and no I/O here: given the same inputs the builder always produces
the same chain (modulo optional timestamps), which is what makes the ledger a
tamper-evident audit trail.

The construction has two clean stages:

1. **Append** a new block to an existing chain (or build the genesis block when
   the chain is empty). Each block carries one
   :class:`~device_ai.ledger.models.LedgerRecord` (the payload) and one
   :class:`~device_ai.ledger.models.BlockHeader` (the chain link). The header's
   ``previous_hash`` is the SHA-256 digest of the prior block's header
   (deterministically serialized), or a genesis sentinel when this is the first
   block. The header's ``record_hash`` is the SHA-256 digest of this block's
   record (deterministically serialized).
2. **Verify** the chain's structural integrity: every block's ``previous_hash``
   matches the prior block's header hash, every block's ``record_hash`` matches
   its record's canonical hash, and block indices are sequential starting from
   ``0``.

The builder emits **a tamper-evident chain** — a modification to any block or
its order invalidates subsequent hashes, which is detectable via the
verification stage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import LedgerError
from ..utils.hashing import hash_bytes
from .models import Block, Blockchain, BlockHeader, LedgerRecord

if TYPE_CHECKING:
    from datetime import datetime

    from ..integrity.models import PassportIntegrityReport
    from ..passport.models import DevicePassport
    from ..trust.models import PassportTrustReport
    from .config import LedgerConfig


class LedgerBuilder:
    """Build deterministic blocks and chains from passport artefacts."""

    def __init__(self, config: LedgerConfig) -> None:
        self._config = config

    @property
    def config(self) -> LedgerConfig:
        """Return the configuration this builder uses."""
        return self._config

    def create_record(
        self,
        passport: DevicePassport,
        integrity: PassportIntegrityReport,
        trust: PassportTrustReport,
        *,
        created_at: datetime | None = None,
    ) -> LedgerRecord:
        """Create an immutable ledger record from the upstream reports.

        Extracts the passport id, integrity hash, trust score/level and
        provenance versions from the three upstream reports and composes them
        into a single :class:`~device_ai.ledger.models.LedgerRecord` — the
        payload a block will carry.

        Args:
            passport: The :class:`~device_ai.passport.models.DevicePassport`.
            integrity: The passport's
                :class:`~device_ai.integrity.models.PassportIntegrityReport`.
            trust: The passport's
                :class:`~device_ai.trust.models.PassportTrustReport`.
            created_at: Record timestamp, or ``None``.

        Returns:
            The immutable :class:`~device_ai.ledger.models.LedgerRecord`.
        """
        return LedgerRecord(
            passport_id=passport.passport_id,
            integrity_hash=integrity.canonical_hash,
            trust_score=trust.trust_score,
            trust_level=trust.trust_level.value,
            passport_version=passport.passport_version,
            integrity_engine_version=integrity.engine_version,
            trust_engine_version=trust.engine_version,
            created_at=created_at,
        )

    def create_block(
        self,
        record: LedgerRecord,
        previous_block: Block | None = None,
        *,
        timestamp: datetime | None = None,
    ) -> Block:
        """Create an immutable block chaining to the previous block (or genesis).

        Builds a :class:`~device_ai.ledger.models.BlockHeader` with the
        deterministic SHA-256 hashes (the previous block's header hash and this
        block's record hash), then composes the header and record into a
        :class:`~device_ai.ledger.models.Block`.

        Args:
            record: The :class:`~device_ai.ledger.models.LedgerRecord` payload.
            previous_block: The prior block to chain to, or ``None`` when this
                is the genesis block (index ``0``).
            timestamp: Block timestamp, or ``None``.

        Returns:
            The immutable :class:`~device_ai.ledger.models.Block`.

        Raises:
            LedgerError: If the configured hash algorithm is not
                supported (an engine fault, never a data fault).
        """
        index = 0 if previous_block is None else previous_block.index + 1
        previous_hash = self._compute_previous_hash(previous_block)
        record_hash = self._hash_record(record)

        header = BlockHeader(
            index=index,
            timestamp=timestamp,
            previous_hash=previous_hash,
            record_hash=record_hash,
        )
        return Block(header=header, record=record)

    def create_chain(
        self,
        blocks: list[Block],
        *,
        created_at: datetime | None = None,
    ) -> Blockchain:
        """Create an immutable blockchain from the ordered blocks.

        Validates the chain's structural integrity (previous-hash linking,
        record-hash matching, sequential indices) and builds an immutable
        :class:`~device_ai.ledger.models.Blockchain`.

        Args:
            blocks: The ordered blocks, from genesis (index ``0``) to the most
                recent.
            created_at: Chain timestamp, or ``None``.

        Returns:
            The immutable :class:`~device_ai.ledger.models.Blockchain` with
            validation status.
        """
        is_valid = self.verify_chain(blocks)
        return Blockchain(
            blocks=tuple(blocks),
            version=self._config.blockchain_version,
            is_valid=is_valid,
            block_count=len(blocks),
            created_at=created_at,
        )

    def append_block(
        self,
        chain: Blockchain,
        record: LedgerRecord,
        *,
        timestamp: datetime | None = None,
        created_at: datetime | None = None,
    ) -> Blockchain:
        """Append a new block to an existing chain, returning a new chain.

        Builds a new block chaining to the last block of ``chain``, appends it
        to the block list, and returns a fresh
        :class:`~device_ai.ledger.models.Blockchain` with updated validation
        status and block count.

        Args:
            chain: The existing :class:`~device_ai.ledger.models.Blockchain`.
            record: The :class:`~device_ai.ledger.models.LedgerRecord` to
                append.
            timestamp: Block timestamp, or ``None``.
            created_at: Chain timestamp, or ``None``.

        Returns:
            A new :class:`~device_ai.ledger.models.Blockchain` with the
            appended block.

        Raises:
            LedgerError: If the configured hash algorithm is not
                supported.
        """
        previous_block = chain.blocks[-1] if chain.blocks else None
        new_block = self.create_block(record, previous_block, timestamp=timestamp)
        new_blocks = list(chain.blocks) + [new_block]
        return self.create_chain(new_blocks, created_at=created_at)

    # -- Internal hashing and verification -----------------------------------

    def _hash(self, canonical_json: str) -> str:
        """Compute the configured hash over a canonical JSON string.

        Isolated so both the header-linking hash and the record-payload hash go
        through one place — the single point that maps an unsupported algorithm
        onto a typed :class:`~device_ai.exceptions.LedgerError`.

        Args:
            canonical_json: The canonical JSON to hash (sorted keys, fixed
                separators, no pretty-printing).

        Returns:
            The hexadecimal digest string.

        Raises:
            LedgerError: If the configured hash algorithm is unsupported (an
                engine fault, never a data fault).
        """
        try:
            return hash_bytes(
                canonical_json.encode("utf-8"),
                algorithm=self._config.hash_algorithm,
            )
        except ValueError as exc:
            raise LedgerError(
                f"Unsupported ledger hash algorithm "
                f"'{self._config.hash_algorithm}'.",
                details={"algorithm": self._config.hash_algorithm},
            ) from exc

    def _compute_previous_hash(self, previous_block: Block | None) -> str:
        """Compute the previous-hash value for a new block.

        Returns the SHA-256 digest of the previous block's header (canonical
        JSON) when ``previous_block`` is given, or the genesis sentinel when
        this is the first block.

        Raises:
            LedgerError: If the hash algorithm is unsupported.
        """
        if previous_block is None:
            return self._config.genesis_previous_hash
        return self._hash(previous_block.header.to_json())

    def _hash_record(self, record: LedgerRecord) -> str:
        """Compute the canonical hash of a ledger record.

        Hashes the record's canonical JSON (sorted keys, fixed separators, no
        pretty-printing) so the digest is a pure function of the record's
        content.

        Raises:
            LedgerError: If the hash algorithm is unsupported.
        """
        return self._hash(record.to_json())

    def chain_id(self, chain: Blockchain) -> str:
        """Return the deterministic, content-addressed id of a chain.

        The id is the configured hash of the chain's **genesis block** (its
        canonical JSON) — a stable anchor that identifies the chain by its
        origin: it does not change as blocks are appended (the genesis block is
        immutable), and equal genesis blocks yield equal ids. It is what the
        :class:`~device_ai.ledger.service.LedgerService` hands to a
        :class:`~device_ai.ledger.backend.LedgerBackend` as the storage key.

        Args:
            chain: The :class:`~device_ai.ledger.models.Blockchain` to identify.

        Returns:
            The hexadecimal chain id.

        Raises:
            LedgerError: If the chain is empty (no genesis block to anchor on),
                or the configured hash algorithm is unsupported.
        """
        if not chain.blocks:
            raise LedgerError(
                "Cannot derive an id for an empty chain (no genesis block).",
                details={"block_count": 0},
            )
        return self._hash(chain.blocks[0].to_json())

    def verify_chain(self, blocks: list[Block]) -> bool:
        """Verify the chain's structural integrity.

        Recomputes every link and payload hash and checks the ordering, so any
        tampering with a block's contents or the chain's order is detectable.

        Args:
            blocks: The ordered blocks to verify (an empty list is trivially
                valid).

        Returns:
            Whether the chain passes every check: block indices are sequential
            starting from ``0``, every block's ``previous_hash`` matches the
            prior block's header hash, and every block's ``record_hash`` matches
            its record's canonical hash.

        Raises:
            LedgerError: If the configured hash algorithm is unsupported.
        """
        if not blocks:
            return True

        for i, block in enumerate(blocks):
            # Check sequential indices starting from 0.
            if block.index != i:
                return False

            # Check previous-hash linking.
            expected_previous = (
                self._config.genesis_previous_hash
                if i == 0
                else self._compute_previous_hash(blocks[i - 1])
            )
            if block.previous_hash != expected_previous:
                return False

            # Check record-hash matching.
            expected_record_hash = self._hash_record(block.record)
            if block.record_hash != expected_record_hash:
                return False

        return True
