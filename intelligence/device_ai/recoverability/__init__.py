"""Recoverability Intelligence Engine (milestone M1.8).

Turns the immutable :class:`~device_ai.fusion.models.DeviceContext` produced by
the fusion engine into an explainable, rule-driven
:class:`~device_ai.recoverability.models.RecoverabilityReport`: normalized
repairability / reusability / recyclability scores, a hazard level, an
aggregated confidence and a recommended end-of-life action, each backed by
ordered human-readable reasoning and warnings.

The engine is **deterministic and rule-based** — no learned damage
classification, no material/carbon/blockchain/passport — so it runs in the base
environment with zero weights:

* **Profiles** — :func:`~device_ai.recoverability.profiles.profile_for` resolves
  a :class:`~device_ai.recoverability.profiles.DeviceProfile` (baseline scores,
  intrinsic hazard, battery flag) for the device type.
* **Rules** — :class:`~device_ai.recoverability.rules.RuleEngine` runs small
  independent :class:`~device_ai.recoverability.rules.Rule` s that emit uniform,
  additive :class:`~device_ai.recoverability.models.RuleOutcome` s.
* **Scoring** — :class:`~device_ai.recoverability.scoring.ScoringEngine` folds
  the outcomes (summed deltas, max hazard floor, product of confidence factors)
  and selects the action from an explicit decision table.
* **Service** — :class:`~device_ai.recoverability.service.RecoverabilityService`
  wires profile + rules + scoring into :meth:`assess
  <device_ai.recoverability.service.RecoverabilityService.assess>`.

The engine is **internal-only**: it exposes no endpoints and does not touch the
frozen ``/predict`` contract. It is imported directly by the orchestrating code.
"""

from __future__ import annotations

from .config import RecoverabilityConfig
from .models import (
    HazardLevel,
    RecommendedAction,
    RecoverabilityReport,
    RuleOutcome,
    max_hazard,
)
from .profiles import DeviceProfile, profile_for
from .rules import (
    DEFAULT_RULES,
    BaselineProfileRule,
    BatteryHazardRule,
    ConflictPenaltyRule,
    HighHazardDisposalRule,
    IdentityCompletenessRule,
    LowConfidenceRule,
    Rule,
    RuleEngine,
    UnknownDeviceRule,
)
from .scoring import ScoringEngine
from .service import RECOVERABILITY_ENGINE_VERSION, RecoverabilityService

__all__ = [
    "RECOVERABILITY_ENGINE_VERSION",
    "DEFAULT_RULES",
    "BaselineProfileRule",
    "BatteryHazardRule",
    "ConflictPenaltyRule",
    "DeviceProfile",
    "HazardLevel",
    "HighHazardDisposalRule",
    "IdentityCompletenessRule",
    "LowConfidenceRule",
    "RecommendedAction",
    "RecoverabilityConfig",
    "RecoverabilityReport",
    "RecoverabilityService",
    "Rule",
    "RuleEngine",
    "RuleOutcome",
    "ScoringEngine",
    "UnknownDeviceRule",
    "max_hazard",
    "profile_for",
]
