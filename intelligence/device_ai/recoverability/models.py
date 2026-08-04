"""Recoverability domain models (milestone M1.8).

The Recoverability Intelligence Engine turns the immutable
:class:`~device_ai.fusion.models.DeviceContext` produced by the fusion engine
into an explainable, rule-driven :class:`RecoverabilityReport`. The value
objects here are the vocabulary that makes that assessment auditable:

* :class:`HazardLevel` — the ordered severity of environmental/safety hazard a
  device carries (batteries, CRT phosphors, toner), from ``NONE`` to ``HIGH``,
  plus an ``UNKNOWN`` sentinel for insufficient evidence.
* :class:`RecommendedAction` — the end-of-life disposition the engine advises
  (refurbish, repair, recycle, hazardous disposal, manual review).
* :class:`RuleOutcome` — the uniform, additive contribution one rule makes: score
  deltas per dimension, an optional hazard floor, a confidence factor, a human
  reason, an optional warning and an optional forced action. Making every rule
  speak this single language is what keeps the rule engine modular and the
  scoring pure.
* :class:`RecoverabilityReport` — the normalized, immutable outcome: three
  recoverability scores, a hazard level, an aggregated confidence, the
  recommended action and the ordered reasoning/warnings behind it.

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the
fusion, fingerprint and OCR domain layers it builds on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class HazardLevel(str, Enum):
    """The severity of hazard a device poses at end of life.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a settings/API string. The members are *unordered* as an
    enum; use :func:`max_hazard` (or the module-level ``_HAZARD_ORDER``) to
    combine or compare severities — never rely on definition order.

    ``UNKNOWN`` means the engine had insufficient evidence to rule a hazard in
    or out; it is deliberately treated as more severe than ``NONE`` (it demands
    review) but is never allowed to mask a concrete ``LOW``/``MEDIUM``/``HIGH``
    finding.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


# Severity ranking for combining hazard floors. ``UNKNOWN`` sits just above
# ``NONE``: it signals "needs review" without overriding an evidenced hazard.
_HAZARD_ORDER: dict[HazardLevel, int] = {
    HazardLevel.NONE: 0,
    HazardLevel.UNKNOWN: 1,
    HazardLevel.LOW: 2,
    HazardLevel.MEDIUM: 3,
    HazardLevel.HIGH: 4,
}


def max_hazard(*levels: HazardLevel | None) -> HazardLevel:
    """Return the most severe hazard level among ``levels``.

    ``None`` entries are ignored (a rule that asserts no hazard floor). With no
    non-``None`` argument the result is :attr:`HazardLevel.NONE`.

    Args:
        *levels: Hazard levels (or ``None``) to combine.

    Returns:
        The single most severe :class:`HazardLevel`.
    """
    present = [level for level in levels if level is not None]
    if not present:
        return HazardLevel.NONE
    return max(present, key=lambda level: _HAZARD_ORDER[level])


class RecommendedAction(str, Enum):
    """The end-of-life disposition the engine advises for a device.

    A ``str`` enum for direct serialization. Ordering is *not* semantic; the
    scoring engine selects an action from an explicit decision table rather than
    from member order.
    """

    REFURBISH = "refurbish"
    REPAIR = "repair"
    RECYCLE = "recycle"
    HAZARDOUS_DISPOSAL = "hazardous_disposal"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """One rule's additive contribution to a recoverability assessment.

    Every rule emits zero or more of these; the scoring engine folds them into
    the final report by summing the deltas, taking the most severe hazard floor
    and multiplying the confidence factors. Keeping the contribution uniform is
    what lets rules stay small, independent and reorderable.

    Attributes:
        rule: Machine-readable name of the emitting rule (provenance).
        repairability_delta: Signed adjustment to the repairability score.
        reusability_delta: Signed adjustment to the reusability score.
        recyclability_delta: Signed adjustment to the recyclability score.
        hazard_floor: A hazard level the final report must be at least as severe
            as, or ``None`` when the rule asserts no hazard.
        confidence_factor: Multiplicative factor in ``[0, 1]`` applied to the
            report confidence (``1.0`` leaves confidence unchanged).
        reason: Human-readable explanation of why the rule fired (always set).
        warning: Optional operator-facing caution (e.g. missing identity).
        force_action: Optional action the rule demands regardless of scores
            (e.g. force ``MANUAL_REVIEW`` on very low confidence).
    """

    rule: str
    reason: str
    repairability_delta: float = 0.0
    reusability_delta: float = 0.0
    recyclability_delta: float = 0.0
    hazard_floor: HazardLevel | None = None
    confidence_factor: float = 1.0
    warning: str | None = None
    force_action: RecommendedAction | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the outcome."""
        return {
            "rule": self.rule,
            "reason": self.reason,
            "repairability_delta": self.repairability_delta,
            "reusability_delta": self.reusability_delta,
            "recyclability_delta": self.recyclability_delta,
            "hazard_floor": (
                self.hazard_floor.value if self.hazard_floor is not None else None
            ),
            "confidence_factor": self.confidence_factor,
            "warning": self.warning,
            "force_action": (
                self.force_action.value if self.force_action is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class RecoverabilityReport:
    """The normalized, immutable recoverability assessment of one device.

    Produced by the :class:`~device_ai.recoverability.service.RecoverabilityService`
    from a fused :class:`~device_ai.fusion.models.DeviceContext`. Downstream
    modules (material, carbon, passport) and operators consume this rather than
    re-deriving disposition from raw scores.

    Attributes:
        device_type: The resolved device type the assessment is for (may be
            empty when fusion could not determine it).
        repairability: Normalized ``[0, 1]`` ease-of-repair score.
        reusability: Normalized ``[0, 1]`` fitness-for-reuse score.
        recyclability: Normalized ``[0, 1]`` material-recovery score.
        hazard_level: The combined hazard severity of the device.
        confidence: Aggregated confidence ``[0, 1]`` in this assessment.
        recommended_action: The advised end-of-life disposition.
        reasoning: Ordered, human-readable reasons behind the assessment.
        warnings: Ordered operator-facing cautions (may be empty).
        eco_id: Public EcoID carried over from the device context (empty when
            the context had no fingerprint).
        engine_version: Version of the recoverability engine that produced this.
        created_at: UTC timestamp the report was produced (``None`` when the
            service was constructed without a clock).
    """

    device_type: str
    repairability: float
    reusability: float
    recyclability: float
    hazard_level: HazardLevel
    confidence: float
    recommended_action: RecommendedAction
    reasoning: tuple[str, ...]
    warnings: tuple[str, ...]
    eco_id: str = ""
    engine_version: str = ""
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report.

        Returns:
            A plain ``dict`` with the three scores, hazard level and action as
            their wire strings, the ordered reasoning/warnings, provenance and
            an ISO-8601 ``created_at`` (or ``None``).
        """
        return {
            "eco_id": self.eco_id,
            "device_type": self.device_type,
            "repairability": self.repairability,
            "reusability": self.reusability,
            "recyclability": self.recyclability,
            "hazard_level": self.hazard_level.value,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action.value,
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
            "engine_version": self.engine_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }
