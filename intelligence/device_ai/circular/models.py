"""Circular-decision domain models (milestone M2.2).

The Circular Decision Engine turns the consolidated device-intelligence evidence
— a fused :class:`~device_ai.fusion.models.DeviceContext` (M1.7), the normalized
:class:`~device_ai.decision.models.DecisionKnowledgeReport` (M2.1), the
:class:`~device_ai.recoverability.models.RecoverabilityReport` (M1.8) and the
:class:`~device_ai.environmental.models.EnvironmentalImpactReport` (M1.11) — into
a single, actionable :class:`DecisionReport`.

Unlike the M2.1 report (which is *normalized evidence only*), this is the first
report in the pipeline that carries an actual **recommendation**: a recommended
end-of-life action, a triage priority, an aggregated confidence, the exact rules
that fired, and the ordered reasoning/warnings behind them. It deliberately
contains no economic valuation, no optimization and no marketplace/blockchain
concern — it recommends *what to do*, not *what it is worth*.

The value objects here are the vocabulary that makes that recommendation
auditable:

* :class:`Priority` — the triage urgency of acting on the device
  (``high``/``medium``/``low``). A ``str`` enum so members serialize to their
  wire value directly and can be constructed from a catalogue string.
* :class:`RecommendedAction` — the advised end-of-life disposition, re-used from
  the recoverability engine so a circular :class:`DecisionReport` and a
  :class:`~device_ai.recoverability.models.RecoverabilityReport` speak the same
  action vocabulary.
* :class:`TriggeredRule` — the provenance of one rule that matched the evidence:
  its identifier, the action/priority it advises, its precedence and whether it
  *won* the recommendation. Retaining every triggered rule (not just the winner)
  is what makes the precedence decision transparent.
* :class:`DecisionReport` — the immutable outcome: the recommended action, the
  priority, the aggregated confidence, the ordered triggered rules, the ordered
  reasoning/warnings and provenance (EcoID, device type, engine and
  rule-catalogue versions, timestamp).

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the fusion,
recoverability, decision-knowledge and environmental domain layers it builds on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# Re-used verbatim from the recoverability engine so the circular decision and
# the upstream recoverability assessment share one action vocabulary (refurbish,
# repair, recycle, hazardous disposal, manual review) rather than two divergent
# ones. The circular engine recommends the action; it does not redefine it.
from ..recoverability.models import RecommendedAction

__all__ = [
    "DecisionReport",
    "Priority",
    "RecommendedAction",
    "TriggeredRule",
]


class Priority(str, Enum):
    """The triage urgency of acting on a device's recommended disposition.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a rule-catalogue string (e.g. ``"high"``). Ordering is
    *not* semantic; the engine reads a rule's priority from the catalogue rather
    than from member order.

    ``HIGH`` marks a device that demands prompt attention (an assessed hazard, a
    high-value recovery or a forced review); ``LOW`` marks the routine fallback.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every priority, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class TriggeredRule:
    """One rule that matched the consolidated evidence, with its provenance.

    The engine evaluates every catalogue rule against the projected signals and
    records each rule whose conditions all held. The rule with the highest
    precedence determines the recommendation (``won`` is ``True`` for it); the
    others are retained as lower-precedence alternatives so an operator can see
    exactly what else applied and why it was overridden.

    Attributes:
        rule_id: Machine-readable identifier of the rule (catalogue provenance).
        action: The end-of-life action this rule advises.
        priority: The triage priority this rule advises.
        precedence: The rule's precedence rank (lower wins); recorded for audit.
        reason: Human-readable explanation of why the rule matched.
        won: Whether this rule determined the report's recommendation (exactly
            one triggered rule is the winner).
    """

    rule_id: str
    action: RecommendedAction
    priority: Priority
    precedence: int
    reason: str
    won: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the triggered rule."""
        return {
            "rule_id": self.rule_id,
            "action": self.action.value,
            "priority": self.priority.value,
            "precedence": self.precedence,
            "reason": self.reason,
            "won": self.won,
        }


@dataclass(frozen=True, slots=True)
class DecisionReport:
    """The immutable circular-decision recommendation for one device.

    Produced by the :class:`~device_ai.circular.service.CircularService` from the
    fused context and its three consolidated reports. It is the first report in
    the pipeline that carries an actual recommendation rather than normalized
    evidence — downstream operators and orchestration consume this to route a
    device, so it is deliberately explainable end to end.

    Attributes:
        device_type: The resolved device type the recommendation is for (may be
            empty when fusion could not determine it).
        recommended_action: The advised end-of-life disposition.
        priority: The triage priority of acting on the recommendation.
        confidence: Aggregated confidence ``[0, 1]`` in the recommendation,
            blended from the consolidated decision confidence and every
            triggered rule's confidence factor.
        triggered_rules: The rules that matched, ordered by precedence (winner
            first); may be empty when only the catalogue fallback applied.
        reasoning: Ordered, human-readable reasons behind the recommendation.
        warnings: Ordered operator-facing cautions (may be empty).
        eco_id: Public EcoID carried over from the device context (empty when the
            context had no fingerprint).
        engine_version: Version of the circular engine that produced this.
        rules_version: Version of the external rule catalogue used.
        created_at: UTC timestamp the report was produced (``None`` when the
            service was constructed without a clock).
    """

    device_type: str
    recommended_action: RecommendedAction
    priority: Priority
    confidence: float
    triggered_rules: tuple[TriggeredRule, ...]
    reasoning: tuple[str, ...]
    warnings: tuple[str, ...]
    eco_id: str = ""
    engine_version: str = ""
    rules_version: str = ""
    created_at: datetime | None = None

    @property
    def triggered_count(self) -> int:
        """Return the number of rules that matched the evidence."""
        return len(self.triggered_rules)

    @property
    def winning_rule(self) -> TriggeredRule | None:
        """Return the rule that determined the recommendation, or ``None``.

        ``None`` means no rule matched and the catalogue fallback supplied the
        recommendation.
        """
        for rule in self.triggered_rules:
            if rule.won:
                return rule
        return None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report.

        Returns:
            A plain ``dict`` with the recommended action and priority as their
            wire strings, the aggregated confidence, the ordered triggered rules,
            the reasoning/warnings, provenance and an ISO-8601 ``created_at`` (or
            ``None``).
        """
        return {
            "eco_id": self.eco_id,
            "device_type": self.device_type,
            "recommended_action": self.recommended_action.value,
            "priority": self.priority.value,
            "confidence": self.confidence,
            "triggered_rules": [rule.to_dict() for rule in self.triggered_rules],
            "triggered_count": self.triggered_count,
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
            "engine_version": self.engine_version,
            "rules_version": self.rules_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }
