"""Device Lifecycle Ledger Engine (milestone M3.3).

An internal-only, deterministic **device-history builder** that models the
complete lifecycle of a device as an ordered sequence of immutable events and
validates that sequence against an external, versioned state machine. It sits
*above* the M3.1 blockchain ledger core: where the ledger core chains passport
verdicts, this engine chains a device's history — from registration through use,
collection, transport, assessment, refurbishment or recycling, to disposal — and
ties into the ledger **through the M3.2 backend abstraction** for anchoring and
correlation.

The engine carries **no inference and no evidence collection of its own**: it
accepts :class:`~device_ai.lifecycle.models.LifecycleEvent` objects, validates
their ordering against the external
:class:`~device_ai.lifecycle.rules.LifecycleRuleSet`, and composes them into an
immutable, canonically serializable
:class:`~device_ai.lifecycle.models.LifecycleRecord`. Its state machine (the
legal event-type transitions and the initial events) lives in an external
YAML/JSON file loaded by a strict validating loader; its validation is
deterministic and its serialization canonical, so the same events always yield
byte-identical output (modulo optional timestamps).

The :class:`~device_ai.lifecycle.service.LifecycleService` is the injectable
façade: it builds and validates records and, for anchoring, depends only on an
injected :class:`~device_ai.ledger.service.LedgerService` — whose persistence
goes through the technology-agnostic
:class:`~device_ai.ledger.backend.LedgerBackend` protocol.

There is no HTTP surface — orchestrating code consumes the
:class:`~device_ai.lifecycle.models.LifecycleRecord` directly. This engine
deliberately implements no Hyperledger Fabric, chaincode, smart contract, REST
API, networking, GPS tracking, event streaming, QR scanning, wallet or
digital-signature concern; those are out of scope for M3.3. It is a local,
deterministic, in-memory data structure that models device history and validates
it against external rules, behind a pluggable ledger anchor.
"""

from __future__ import annotations

from .config import DEFAULT_RULES_PATH, LifecycleConfig
from .engine import LifecycleEngine
from .models import (
    LifecycleEvent,
    LifecycleEventType,
    LifecycleRecord,
)
from .rules import (
    LifecycleRuleSet,
    LifecycleTransition,
    load_rules,
)
from .service import LIFECYCLE_ENGINE_VERSION, LifecycleService

__all__ = [
    "DEFAULT_RULES_PATH",
    "LIFECYCLE_ENGINE_VERSION",
    "LifecycleConfig",
    "LifecycleEngine",
    "LifecycleEvent",
    "LifecycleEventType",
    "LifecycleRecord",
    "LifecycleRuleSet",
    "LifecycleService",
    "LifecycleTransition",
    "load_rules",
]
