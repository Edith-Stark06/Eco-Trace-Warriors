"""Decision Knowledge Engine (milestone M2.1).

An internal-only, deterministic engine that turns the five upstream
device-intelligence reports — a fused
:class:`~device_ai.fusion.models.DeviceContext` (M1.7), its
:class:`~device_ai.recoverability.models.RecoverabilityReport` (M1.8), its
:class:`~device_ai.components.models.ComponentReport` (M1.9), its
:class:`~device_ai.materials.models.MaterialReport` (M1.10) and its
:class:`~device_ai.environmental.models.EnvironmentalImpactReport` (M1.11) — into
a single, normalized :class:`DecisionKnowledgeReport`: six comparable ``[0, 1]``
decision dimensions (repairability, reusability, recycling, hazard, environmental
priority and material value), each a transparent weighted mean of upstream
signals, plus a separate overall-confidence axis and an auditable per-dimension
evidence breakdown.

The report is **normalized evidence only** — it consolidates what the upstream
engines found so a later decision layer has one clean input. It deliberately
contains no recommended action, no economic valuation and no optimization.

The engine mirrors the M1.11 environmental engine: its weighting knowledge lives
in an external, versioned YAML/JSON catalogue (loaded by a strict validating
loader), its operational knobs live in an immutable config, and its service is
fully injectable. There is no HTTP surface — orchestrating code consumes the
:class:`DecisionKnowledgeReport` directly.
"""

from __future__ import annotations

from .config import DEFAULT_KNOWLEDGE_PATH, DecisionConfig
from .inference import DecisionInferenceEngine
from .knowledge import (
    CANONICAL_SIGNALS,
    CONFIDENCE_SOURCES,
    KnowledgeBase,
    Normalization,
    load_knowledge,
)
from .models import (
    DecisionDimension,
    DecisionKnowledgeReport,
    DimensionEvidence,
    EvidenceSignal,
)
from .service import DECISION_ENGINE_VERSION, DecisionService

__all__ = [
    "CANONICAL_SIGNALS",
    "CONFIDENCE_SOURCES",
    "DECISION_ENGINE_VERSION",
    "DEFAULT_KNOWLEDGE_PATH",
    "DecisionConfig",
    "DecisionDimension",
    "DecisionInferenceEngine",
    "DecisionKnowledgeReport",
    "DecisionService",
    "DimensionEvidence",
    "EvidenceSignal",
    "KnowledgeBase",
    "Normalization",
    "load_knowledge",
]
