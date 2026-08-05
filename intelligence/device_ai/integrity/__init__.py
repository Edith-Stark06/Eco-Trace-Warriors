"""Device Passport Validation & Integrity Engine (milestone M2.4).

An internal-only, deterministic **checker** that consumes the immutable
:class:`~device_ai.passport.models.DevicePassport` the passport core (M2.3)
produced and emits a single, immutable :class:`PassportIntegrityReport`. It
answers two questions about that document: *is it structurally sound?* — by
re-validating every section against an external, versioned rule-set (sections
present, kinds correct, required object fields present, normalized confidences
within ``[0, 1]``) and reporting the outcome as ordered errors and warnings; and
*what is its integrity anchor?* — by computing a deterministic **SHA-256** hash
over the passport's canonical serialization so any later mutation is detectable.

Unlike the M2.3 core (which *assembles* the passport), the integrity engine
carries **no inference and no assembly of its own**: it re-checks a document the
pipeline already produced and hashes it. Its validation contract lives in an
external, versioned YAML/JSON rule-set (loaded by a strict validating loader); its
validator is deterministic and its report serialization is canonical, so the same
passport always yields byte-identical output (modulo an optional timestamp).

There is no HTTP surface — orchestrating code consumes the
:class:`PassportIntegrityReport` directly. This engine deliberately implements no
blockchain, digital signature, QR, CBOR, ownership-history, lifecycle-event or
persistence concern; those are out of scope for M2.4.
"""

from __future__ import annotations

from .config import (
    DEFAULT_HASH_ALGORITHM,
    DEFAULT_RULES_PATH,
    IntegrityConfig,
)
from .models import (
    CheckedSection,
    PassportIntegrityReport,
    ValidationStatus,
)
from .rules import (
    IntegrityRuleSet,
    SectionKind,
    SectionRule,
    load_rules,
)
from .service import INTEGRITY_ENGINE_VERSION, IntegrityService
from .validator import PassportIntegrityValidator

__all__ = [
    "DEFAULT_HASH_ALGORITHM",
    "DEFAULT_RULES_PATH",
    "INTEGRITY_ENGINE_VERSION",
    "CheckedSection",
    "IntegrityConfig",
    "IntegrityRuleSet",
    "IntegrityService",
    "PassportIntegrityReport",
    "PassportIntegrityValidator",
    "SectionKind",
    "SectionRule",
    "ValidationStatus",
    "load_rules",
]
