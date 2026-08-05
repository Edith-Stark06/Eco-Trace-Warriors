"""Trust & Provenance Engine (milestone M2.5).

An internal-only, deterministic **trust evaluator** that consumes the four
upstream artefacts the pipeline already produced — the immutable
:class:`~device_ai.passport.models.DevicePassport` (M2.3), its
:class:`~device_ai.integrity.models.PassportIntegrityReport` (M2.4), the
normalized :class:`~device_ai.decision.models.DecisionKnowledgeReport` (M2.1) and
the actionable :class:`~device_ai.circular.models.DecisionReport` (M2.2) — and
emits a single, immutable :class:`PassportTrustReport`. It answers one question
about the passport: *how much can this document be trusted as a faithful
representation of the device?* — expressed as a normalized trust score, a mapped
trust level and four transparent sub-axes (identity confidence, evidence
consistency, decision confidence and integrity confidence).

Unlike the M2.3 core (which *assembles* the passport) and the M2.4 engine (which
*checks* it), the trust engine carries **no inference and no evidence collection
of its own**: it reads the existing confidence and consistency signals the four
reports already carry, blends them into a weighted-average score, and maps that
score to a level. Its scoring policy lives in an external, versioned YAML/JSON
catalogue (loaded by a strict validating loader); its scoring is deterministic
and its report serialization is canonical, so the same inputs always yield
byte-identical output (modulo an optional timestamp).

There is no HTTP surface — orchestrating code consumes the
:class:`PassportTrustReport` directly. This engine deliberately implements no
blockchain, smart-contract, digital-signature, QR, wallet, ownership-history,
marketplace, carbon-credit or persistence concern; those are out of scope for
M2.5.
"""

from __future__ import annotations

from .config import DEFAULT_RULES_PATH, TrustConfig
from .engine import TrustEngine
from .models import (
    PassportTrustReport,
    TrustAxis,
    TrustLevel,
)
from .rules import (
    CANONICAL_AXES,
    AxisWeight,
    TrustLevelRule,
    TrustRuleSet,
    load_rules,
)
from .service import TRUST_ENGINE_VERSION, TrustService

__all__ = [
    "CANONICAL_AXES",
    "DEFAULT_RULES_PATH",
    "TRUST_ENGINE_VERSION",
    "AxisWeight",
    "PassportTrustReport",
    "TrustAxis",
    "TrustConfig",
    "TrustEngine",
    "TrustLevel",
    "TrustLevelRule",
    "TrustRuleSet",
    "TrustService",
    "load_rules",
]
