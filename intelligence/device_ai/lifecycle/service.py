"""Device lifecycle ledger service (milestone M3.3).

The thin, injectable façade over the device lifecycle ledger engine: it owns the
loaded transition rules, the validation engine and — for anchoring — a
:class:`~device_ai.ledger.service.LedgerService`. It builds and validates
immutable :class:`~device_ai.lifecycle.models.LifecycleRecord` histories from
lifecycle events, and stamps provenance (engine/rules versions and an optional
timestamp) onto every record.

Like the trust, ledger, integrity and passport services it mirrors, every
collaborator is constructor-injected with a sensible default, so production
wires nothing while tests can inject a hand-built rule set, a fixed clock, a
custom engine or a specific ledger. The rules are loaded exactly once, at
construction, and held immutably.

**Ledger integration.** The lifecycle engine models a device's *history*; the
blockchain ledger core (M3.1) anchors a passport's *verdicts*. The lifecycle
service ties the two together **through the ledger's backend abstraction**
(M3.2): it depends only on the injected
:class:`~device_ai.ledger.service.LedgerService` — whose storage and blockchain
operations go through the technology-agnostic
:class:`~device_ai.ledger.backend.LedgerBackend` protocol — so it can confirm a
device's passport chain is anchored, list anchored chains and load one to
correlate it with a lifecycle history, without ever touching a concrete store.
The service is **internal-only**: it exposes no HTTP surface and does not touch
the frozen ``/predict`` contract. It performs no inference, no networking, no GPS
tracking and no persistence of its own.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..ledger.service import LedgerService
from .config import LifecycleConfig
from .engine import LifecycleEngine
from .models import LifecycleEvent, LifecycleEventType
from .rules import LifecycleRuleSet, load_rules

if TYPE_CHECKING:
    from ..ledger.models import Blockchain
    from .models import LifecycleRecord

#: Version tag stamped onto every produced :class:`LifecycleRecord`.
LIFECYCLE_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative rules path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class LifecycleService:
    """Build, validate and anchor device lifecycle histories.

    Args:
        config: The engine configuration (rules locator). Defaults to the
            reference :class:`LifecycleConfig`.
        rules: The loaded transition rules. Defaults to loading the rules named
            by ``config`` from disk exactly once at construction.
        engine: The validation engine. Defaults to a :class:`LifecycleEngine`.
        ledger: The :class:`~device_ai.ledger.service.LedgerService` used to
            anchor and correlate passport chains (M3.1/M3.2). Defaults to a
            fresh :class:`~device_ai.ledger.service.LedgerService` (memory
            backend). The lifecycle service depends only on this façade, whose
            persistence goes through the
            :class:`~device_ai.ledger.backend.LedgerBackend` protocol.
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests. Pass ``None`` to omit ``created_at`` entirely
            (keeping every record a pure function of its inputs).
        engine_version: Version tag stamped onto every produced record.
    """

    def __init__(
        self,
        *,
        config: LifecycleConfig | None = None,
        rules: LifecycleRuleSet | None = None,
        engine: LifecycleEngine | None = None,
        ledger: LedgerService | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = LIFECYCLE_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else LifecycleConfig()
        self._rules = (
            rules
            if rules is not None
            else load_rules(
                self._config.resolved_rules_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._engine = engine if engine is not None else LifecycleEngine()
        self._ledger = ledger if ledger is not None else LedgerService()
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> LifecycleConfig:
        """Return the configuration this service validates with."""
        return self._config

    @property
    def rules(self) -> LifecycleRuleSet:
        """Return the loaded transition rules."""
        return self._rules

    @property
    def engine(self) -> LifecycleEngine:
        """Return the validation engine this service drives."""
        return self._engine

    @property
    def ledger(self) -> LedgerService:
        """Return the ledger service this service anchors histories through."""
        return self._ledger

    def event(
        self,
        event_type: LifecycleEventType,
        *,
        actor: str = "",
        location: str = "",
        note: str = "",
    ) -> LifecycleEvent:
        """Create a single lifecycle event stamped with the current time.

        A convenience factory that applies the service's clock so callers do not
        thread timestamps by hand. Pass ``clock=None`` at construction to omit
        the timestamp entirely.

        Args:
            event_type: The :class:`~device_ai.lifecycle.models.LifecycleEventType`.
            actor: Optional party that recorded the event.
            location: Optional free-text location label (no GPS tracking).
            note: Optional free-form annotation.

        Returns:
            The immutable :class:`~device_ai.lifecycle.models.LifecycleEvent`.
        """
        occurred_at = self._clock() if self._clock is not None else None
        return LifecycleEvent(
            event_type=event_type,
            actor=actor,
            location=location,
            note=note,
            occurred_at=occurred_at,
        )

    def build(
        self,
        device_id: str,
        events: Sequence[LifecycleEvent],
    ) -> LifecycleRecord:
        """Validate an ordered event sequence and compose a lifecycle record.

        Delegates to the engine against the loaded rules and stamps provenance
        (engine/rules versions and an optional timestamp). A sequence that
        violates the state machine still returns a record — with
        ``is_valid=False`` — rather than raising.

        Args:
            device_id: The id of the device this lifecycle belongs to.
            events: The ordered lifecycle events, from genesis onward.

        Returns:
            The immutable :class:`~device_ai.lifecycle.models.LifecycleRecord`.
        """
        created_at = self._clock() if self._clock is not None else None
        return self._engine.build_record(
            device_id,
            events,
            self._rules,
            rules_version=self._rules.version,
            engine_version=self._engine_version,
            created_at=created_at,
        )

    def append(
        self,
        record: LifecycleRecord,
        event: LifecycleEvent,
    ) -> LifecycleRecord:
        """Return a new record with ``event`` appended and re-validated.

        Builds a fresh :class:`~device_ai.lifecycle.models.LifecycleRecord` from
        the record's existing events plus ``event`` (re-running validation), so
        an illegal transition is reflected as ``is_valid=False`` on the result.

        Args:
            record: The existing :class:`~device_ai.lifecycle.models.LifecycleRecord`.
            event: The :class:`~device_ai.lifecycle.models.LifecycleEvent` to append.

        Returns:
            A new :class:`~device_ai.lifecycle.models.LifecycleRecord`.
        """
        return self.build(record.device_id, (*record.events, event))

    def can_append(
        self,
        record: LifecycleRecord,
        event: LifecycleEvent,
    ) -> bool:
        """Return whether ``event`` may legally extend ``record`` (see engine)."""
        return self._engine.can_append(record, event, self._rules)

    # -- Ledger integration via the ledger's backend abstraction (M3.2) ------

    def is_anchored(self, chain_id: str) -> bool:
        """Return whether the ledger holds an anchored chain for ``chain_id``.

        Delegates to the injected :class:`~device_ai.ledger.service.LedgerService`,
        whose lookup goes through the
        :class:`~device_ai.ledger.backend.LedgerBackend` protocol — so this works
        identically across the memory, mock-Fabric and mock-Ethereum backends.

        Args:
            chain_id: The ledger chain id (e.g. from a passport's anchored chain).

        Returns:
            ``True`` when the ledger holds the chain, ``False`` otherwise.
        """
        return self._ledger.exists(chain_id)

    def anchored_chain(self, chain_id: str) -> Blockchain | None:
        """Return the anchored chain for ``chain_id``, or ``None`` if absent.

        Lets a caller correlate a lifecycle history with the device's anchored
        passport chain without reaching past the ledger façade into a concrete
        store.

        Args:
            chain_id: The ledger chain id.

        Returns:
            The stored :class:`~device_ai.ledger.models.Blockchain`, or ``None``.
        """
        return self._ledger.load(chain_id)

    def anchored_ids(self) -> list[str]:
        """Return every chain id the ledger currently holds (order unspecified)."""
        return self._ledger.list_ids()
