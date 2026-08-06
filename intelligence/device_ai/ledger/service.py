"""Blockchain ledger service (milestones M3.1, M3.2).

The thin, injectable façade over the blockchain ledger core: it owns the loaded
ledger configuration, the deterministic builder and — since M3.2 — a pluggable
:class:`~device_ai.ledger.backend.LedgerBackend`. It drives the construction of
ledger records, blocks and chains from passport artefacts, and persists the
resulting chains through the injected backend. It stamps provenance (an optional
timestamp) onto every produced :class:`~device_ai.ledger.models.LedgerRecord`,
:class:`~device_ai.ledger.models.Block` and
:class:`~device_ai.ledger.models.Blockchain`.

Like the trust, integrity and passport services it mirrors, every collaborator
is constructor-injected with a sensible default, so production wires nothing
while tests can inject a hand-built config, a fixed clock, a custom builder or a
specific backend. The config is loaded exactly once, at construction, and held
immutably. For **storage and blockchain operations the service depends only on
the technology-agnostic** :class:`~device_ai.ledger.backend.LedgerBackend`
**protocol** (M3.2) — never a concrete store — so the ledger technology
(in-memory, a mock Fabric/Ethereum simulation, a future real anchor) can change
without touching the service. The service is **internal-only**: it exposes no
HTTP surface and does not touch the frozen ``/predict`` contract. It performs no
inference, no consensus, no networking and no persistence of its own — it
deterministically chains passport records into a tamper-evident, verifiable
ledger and hands it to the backend.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .backend import LedgerBackend, MemoryLedgerBackend
from .builder import LedgerBuilder
from .config import LedgerConfig, load_config

if TYPE_CHECKING:
    from ..integrity.models import PassportIntegrityReport
    from ..passport.models import DevicePassport
    from ..trust.models import PassportTrustReport
    from .backend import LedgerReceipt
    from .models import Block, Blockchain, LedgerRecord

#: The ``device_ai`` package root, used to resolve a relative config path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class LedgerService:
    """Chain passport artefacts into a deterministic, verifiable blockchain.

    Args:
        config: The ledger configuration (hash algorithm, versions, genesis
            sentinel). Defaults to loading the external config named by the
            reference :class:`LedgerConfig` from disk exactly once at
            construction.
        builder: The deterministic block/chain builder. Defaults to a
            :class:`LedgerBuilder` bound to ``config``.
        backend: The :class:`~device_ai.ledger.backend.LedgerBackend` chains are
            persisted through (M3.2). Defaults to a
            :class:`~device_ai.ledger.backend.MemoryLedgerBackend`. The service
            depends only on the protocol, so any conforming backend works.
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests. Pass ``None`` to omit timestamps entirely
            (keeping every artefact a pure function of its inputs).
    """

    def __init__(
        self,
        *,
        config: LedgerConfig | None = None,
        builder: LedgerBuilder | None = None,
        backend: LedgerBackend | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
    ) -> None:
        self._config = (
            config
            if config is not None
            else load_config(
                LedgerConfig().resolved_config_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._builder = builder if builder is not None else LedgerBuilder(self._config)
        self._backend = backend if backend is not None else MemoryLedgerBackend()
        self._clock = clock

    @property
    def config(self) -> LedgerConfig:
        """Return the configuration this service builds with."""
        return self._config

    @property
    def builder(self) -> LedgerBuilder:
        """Return the deterministic builder this service drives."""
        return self._builder

    @property
    def backend(self) -> LedgerBackend:
        """Return the backend this service persists chains through."""
        return self._backend

    def create_record(
        self,
        passport: DevicePassport,
        integrity: PassportIntegrityReport,
        trust: PassportTrustReport,
    ) -> LedgerRecord:
        """Create a ledger record from a passport and its two upstream reports.

        Composes the passport id, integrity hash, trust score/level and
        provenance versions into a single immutable
        :class:`~device_ai.ledger.models.LedgerRecord`, stamped with the current
        time (when a clock is configured).

        Args:
            passport: The :class:`~device_ai.passport.models.DevicePassport`.
            integrity: The passport's
                :class:`~device_ai.integrity.models.PassportIntegrityReport`.
            trust: The passport's
                :class:`~device_ai.trust.models.PassportTrustReport`.

        Returns:
            The immutable :class:`~device_ai.ledger.models.LedgerRecord`.
        """
        created_at = self._clock() if self._clock is not None else None
        return self._builder.create_record(
            passport, integrity, trust, created_at=created_at
        )

    def genesis(
        self,
        passport: DevicePassport,
        integrity: PassportIntegrityReport,
        trust: PassportTrustReport,
    ) -> Blockchain:
        """Build a fresh single-block chain from the first passport's artefacts.

        Creates the genesis record (index ``0``, previous-hash sentinel) and
        wraps it in a new :class:`~device_ai.ledger.models.Blockchain`.

        Args:
            passport: The :class:`~device_ai.passport.models.DevicePassport`.
            integrity: The passport's
                :class:`~device_ai.integrity.models.PassportIntegrityReport`.
            trust: The passport's
                :class:`~device_ai.trust.models.PassportTrustReport`.

        Returns:
            A new single-block :class:`~device_ai.ledger.models.Blockchain`.
        """
        record = self.create_record(passport, integrity, trust)
        timestamp = self._clock() if self._clock is not None else None
        block = self._builder.create_block(record, None, timestamp=timestamp)
        return self._builder.create_chain([block], created_at=timestamp)

    def append(
        self,
        chain: Blockchain,
        passport: DevicePassport,
        integrity: PassportIntegrityReport,
        trust: PassportTrustReport,
    ) -> Blockchain:
        """Append a new passport's record to an existing chain.

        Creates a ledger record from the passport and its two upstream reports,
        then appends a new block chaining to the last block of ``chain``,
        returning a fresh, re-verified :class:`~device_ai.ledger.models.Blockchain`.

        Args:
            chain: The existing :class:`~device_ai.ledger.models.Blockchain`.
            passport: The :class:`~device_ai.passport.models.DevicePassport`.
            integrity: The passport's
                :class:`~device_ai.integrity.models.PassportIntegrityReport`.
            trust: The passport's
                :class:`~device_ai.trust.models.PassportTrustReport`.

        Returns:
            A new :class:`~device_ai.ledger.models.Blockchain` with the appended
            block.
        """
        record = self.create_record(passport, integrity, trust)
        timestamp = self._clock() if self._clock is not None else None
        return self._builder.append_block(
            chain, record, timestamp=timestamp, created_at=timestamp
        )

    def append_record(
        self,
        chain: Blockchain,
        record: LedgerRecord,
    ) -> Blockchain:
        """Append an already-built ledger record to an existing chain.

        A lower-level companion to :meth:`append` for callers that have already
        composed the :class:`~device_ai.ledger.models.LedgerRecord` (e.g. to
        control its timestamp).

        Args:
            chain: The existing :class:`~device_ai.ledger.models.Blockchain`.
            record: The :class:`~device_ai.ledger.models.LedgerRecord` to append.

        Returns:
            A new :class:`~device_ai.ledger.models.Blockchain` with the appended
            block.
        """
        timestamp = self._clock() if self._clock is not None else None
        return self._builder.append_block(
            chain, record, timestamp=timestamp, created_at=timestamp
        )

    def build_chain(self, records: list[LedgerRecord]) -> Blockchain:
        """Build a complete chain from an ordered list of ledger records.

        Constructs each block in order (the first is genesis), chaining every
        block to its predecessor, and returns a fresh, verified
        :class:`~device_ai.ledger.models.Blockchain`.

        Args:
            records: The ordered ledger records to chain, from genesis onward.

        Returns:
            A new :class:`~device_ai.ledger.models.Blockchain` of ``len(records)``
            blocks (an empty, valid chain when ``records`` is empty).
        """
        blocks: list[Block] = []
        previous: Block | None = None
        for record in records:
            timestamp = self._clock() if self._clock is not None else None
            block = self._builder.create_block(record, previous, timestamp=timestamp)
            blocks.append(block)
            previous = block
        created_at = self._clock() if self._clock is not None else None
        return self._builder.create_chain(blocks, created_at=created_at)

    def verify(self, chain: Blockchain) -> bool:
        """Re-verify an existing chain's structural integrity.

        Recomputes every block's previous-hash link and record hash and checks
        the indices are sequential — detecting any tampering with a block's
        contents or the chain's order.

        Args:
            chain: The :class:`~device_ai.ledger.models.Blockchain` to verify.

        Returns:
            ``True`` when the chain is intact, ``False`` when any block or link
            fails verification.
        """
        return self._builder.verify_chain(list(chain.blocks))

    # -- Persistence via the injected backend (M3.2) -------------------------

    def chain_id(self, chain: Blockchain) -> str:
        """Return the deterministic storage id for a chain.

        Delegates to the builder's content-addressed
        :meth:`~device_ai.ledger.builder.LedgerBuilder.chain_id` (the hash of the
        chain's genesis block), which is the key the backend stores under.

        Args:
            chain: The :class:`~device_ai.ledger.models.Blockchain` to identify.

        Returns:
            The hexadecimal chain id.

        Raises:
            LedgerError: If the chain is empty or the hash algorithm is
                unsupported.
        """
        return self._builder.chain_id(chain)

    def save(self, chain: Blockchain) -> LedgerReceipt:
        """Persist a chain through the injected backend.

        Derives the chain's content-addressed id and hands both to the
        backend's :meth:`~device_ai.ledger.backend.LedgerBackend.write`,
        returning the backend's :class:`~device_ai.ledger.backend.LedgerReceipt`.
        The service depends only on the
        :class:`~device_ai.ledger.backend.LedgerBackend` protocol, so this works
        identically across the memory, mock-Fabric and mock-Ethereum backends.

        Args:
            chain: The :class:`~device_ai.ledger.models.Blockchain` to persist.

        Returns:
            The :class:`~device_ai.ledger.backend.LedgerReceipt` from the backend.

        Raises:
            LedgerError: If the chain is empty (no genesis block to key on).
        """
        return self._backend.write(self.chain_id(chain), chain)

    def load(self, chain_id: str) -> Blockchain | None:
        """Return a persisted chain by id, or ``None`` if the backend has none.

        Args:
            chain_id: The id returned by :meth:`chain_id` or a receipt.

        Returns:
            The stored :class:`~device_ai.ledger.models.Blockchain`, or ``None``.
        """
        return self._backend.read(chain_id)

    def exists(self, chain_id: str) -> bool:
        """Return whether the backend holds a chain for ``chain_id``.

        Args:
            chain_id: The id returned by :meth:`chain_id` or a receipt.

        Returns:
            ``True`` when the backend holds the chain, ``False`` otherwise.
        """
        return self._backend.exists(chain_id)

    def list_ids(self) -> list[str]:
        """Return every chain id the backend currently holds.

        Returns:
            The stored chain ids (order is not guaranteed).
        """
        return self._backend.list_ids()
