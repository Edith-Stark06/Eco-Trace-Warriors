"""Condition intelligence interface and baseline policy (P5.3).

Adheres strictly to the principle:
- Never pretend the object detector determines physical wear or functional condition.
- Return explicit UNKNOWN state with pending_assessment provenance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .enrichment_models import ConditionAssessment

VALID_CONDITION_STATES = frozenset({"EXCELLENT", "GOOD", "FAIR", "POOR", "UNKNOWN"})


@runtime_checkable
class ConditionIntelligence(Protocol):
    """Protocol interface for condition intelligence."""

    def assess_condition(
        self,
        manual_override: str | None = None,
    ) -> ConditionAssessment:
        """Assess condition of a device."""
        ...


class BaselineConditionIntelligence:
    """Conservative baseline condition policy returning explicit UNKNOWN when no model exists."""

    def assess_condition(
        self,
        manual_override: str | None = None,
    ) -> ConditionAssessment:
        """Evaluate condition state according to baseline policy.

        Args:
            manual_override: Optional manual inspection condition label.

        Returns:
            A :class:`ConditionAssessment`.
        """
        if manual_override and manual_override.upper() in VALID_CONDITION_STATES:
            state = manual_override.upper()
            return ConditionAssessment(
                value=state,
                status="AVAILABLE" if state != "UNKNOWN" else "UNAVAILABLE",
                source="manual_inspection",
                confidence=1.0 if state != "UNKNOWN" else None,
                notes=f"Condition set via manual inspection: {state}",
            )

        return ConditionAssessment(
            value="UNKNOWN",
            status="UNAVAILABLE",
            source="pending_assessment",
            confidence=None,
            notes="Baseline condition policy: visual condition assessment model pending.",
        )
