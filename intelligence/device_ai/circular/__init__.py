"""Circular Decision Engine (milestone M2.2).

An internal-only, deterministic engine that turns the consolidated
device-intelligence evidence — a fused
:class:`~device_ai.fusion.models.DeviceContext` (M1.7), the normalized
:class:`~device_ai.decision.models.DecisionKnowledgeReport` (M2.1), the
:class:`~device_ai.recoverability.models.RecoverabilityReport` (M1.8) and the
:class:`~device_ai.environmental.models.EnvironmentalImpactReport` (M1.11) — into
a single, actionable :class:`DecisionReport`: a recommended end-of-life action, a
triage priority, an aggregated confidence, the exact rules that fired and ordered
reasoning/warnings.

Unlike the M2.1 report (normalized evidence only), this is the first report in
the pipeline that carries an actual **recommendation**. It deliberately contains
no economic valuation, no optimization and no marketplace/blockchain/passport
concern — it recommends *what to do*, not *what it is worth*.

The engine mirrors the M2.1 decision engine: its decision policy lives in an
external, versioned YAML/JSON rule catalogue (loaded by a strict validating
loader), its operational knobs live in an immutable config, and its service is
fully injectable. Rules are evaluated deterministically with **explicit
precedence** — each rule carries a unique precedence and the lowest-precedence
matching rule wins — so the recommendation is reproducible and auditable. There
is no HTTP surface — orchestrating code consumes the :class:`DecisionReport`
directly.
"""

from __future__ import annotations

from .config import DEFAULT_RULES_PATH, CircularConfig
from .engine import CircularDecisionEngine
from .models import DecisionReport, Priority, RecommendedAction, TriggeredRule
from .rules import (
    CANONICAL_SIGNALS,
    CONDITION_OPERATORS,
    DecisionRule,
    DefaultRule,
    RuleCatalogue,
    RuleCondition,
    load_rules,
)
from .service import CIRCULAR_ENGINE_VERSION, CircularService

__all__ = [
    "CANONICAL_SIGNALS",
    "CIRCULAR_ENGINE_VERSION",
    "CONDITION_OPERATORS",
    "DEFAULT_RULES_PATH",
    "CircularConfig",
    "CircularDecisionEngine",
    "CircularService",
    "DecisionReport",
    "DecisionRule",
    "DefaultRule",
    "Priority",
    "RecommendedAction",
    "RuleCatalogue",
    "RuleCondition",
    "TriggeredRule",
    "load_rules",
]
