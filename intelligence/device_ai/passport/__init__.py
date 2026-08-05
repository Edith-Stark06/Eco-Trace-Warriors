"""Device Passport Core (milestone M2.3).

An internal-only, deterministic **assembler** that composes the reports the
upstream engines already produced — a fused
:class:`~device_ai.fusion.models.DeviceContext` (M1.7), the actionable
:class:`~device_ai.circular.models.DecisionReport` (M2.2), the
:class:`~device_ai.materials.models.MaterialReport` (M1.10), the
:class:`~device_ai.environmental.models.EnvironmentalImpactReport` (M1.11) and the
device's :class:`~device_ai.fingerprint.models.DeviceFingerprint` (M1.5) — into a
single, immutable :class:`DevicePassport` document.

Unlike the M2.1 (normalized evidence) and M2.2 (actionable recommendation)
engines, the passport core carries **no inference of its own**: every value it
holds is copied or plainly summarized from an upstream report, so the passport is
a faithful, auditable snapshot rather than a re-interpretation. Its structural
contract lives in an external, versioned YAML/JSON schema (loaded by a strict
validating loader); its builder is deterministic and its JSON serialization is
canonical, so the same inputs always yield byte-identical output. A strict
validator checks every assembled passport against the schema before it leaves the
service.

There is no HTTP surface — orchestrating code consumes the :class:`DevicePassport`
directly. This core deliberately implements no blockchain, QR, CBOR, digital
signature, ownership-history, lifecycle-event or persistence concern; those are
out of scope for M2.3.
"""

from __future__ import annotations

from .builder import PassportBuilder
from .config import (
    DEFAULT_PASSPORT_VERSION,
    DEFAULT_SCHEMA_PATH,
    PassportConfig,
)
from .models import (
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
from .schema import (
    PassportSchema,
    SectionKind,
    SectionSchema,
    load_schema,
    validate_passport,
)
from .service import PASSPORT_ENGINE_VERSION, PassportService

__all__ = [
    "DEFAULT_PASSPORT_VERSION",
    "DEFAULT_SCHEMA_PATH",
    "PASSPORT_ENGINE_VERSION",
    "Classification",
    "ConfidenceSummary",
    "DecisionSummary",
    "DeviceIdentity",
    "DevicePassport",
    "EnvironmentalSummary",
    "FingerprintSummary",
    "MaterialSummary",
    "PassportBuilder",
    "PassportConfig",
    "PassportMetadata",
    "PassportSchema",
    "PassportService",
    "SectionKind",
    "SectionSchema",
    "load_schema",
    "validate_passport",
]
