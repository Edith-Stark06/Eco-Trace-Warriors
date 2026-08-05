"""Trust & provenance engine (milestone M2.5).

Deterministic scoring and leveling over a resolved
:class:`~device_ai.trust.rules.TrustRuleSet` and the four upstream inputs (the
:class:`~device_ai.passport.models.DevicePassport` the passport core (M2.3)
produced, the :class:`~device_ai.integrity.models.PassportIntegrityReport` the
integrity engine (M2.4) validated, the normalized
:class:`~device_ai.decision.models.DecisionKnowledgeReport` (M2.1), and the
actionable :class:`~device_ai.circular.models.DecisionReport` (M2.2)). There is
no model and no I/O here — given the same inputs the engine always produces the
same :class:`~device_ai.trust.models.PassportTrustReport`, which is what makes
the trust verdict auditable and reproducible.

The evaluation has three clean stages:

1. **Project** the four upstream reports onto the four normalized ``[0, 1]``
   trust sub-axes (:data:`~device_ai.trust.rules.CANONICAL_AXES`). Identity
   confidence blends identity completeness (the fraction of strong identity
   fields present) with classification confidence; evidence consistency checks
   cross-report device-type agreement and the conflict flag; decision confidence
   averages the circular and decision-knowledge confidences; integrity
   confidence reads the integrity report's validation status and damps by
   warnings.
2. **Score** the weighted average of the four axes using the catalogue's
   per-axis blend weights, then clamp and round. The trust score is transparent
   — an operator can see exactly which axis moved it and by how much.
3. **Level** the score by finding the first catalogue level whose floor the
   score meets or exceeds (the levels are sorted by descending floor). Because
   the loader guarantees a ``0.0`` floor, every score resolves to exactly one
   level.

The engine emits **a trust verdict** — a score, a level, the four sub-axes with
their weights and reasons, and ordered reasoning/warnings. It performs no new
inference, no new evidence collection and no decision recommendation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..integrity.models import ValidationStatus
from .models import PassportTrustReport, TrustAxis, TrustLevel

if TYPE_CHECKING:
    from datetime import datetime

    from ..circular.models import DecisionReport
    from ..decision.models import DecisionKnowledgeReport
    from ..integrity.models import PassportIntegrityReport
    from ..passport.models import DevicePassport
    from .config import TrustConfig
    from .rules import TrustRuleSet

# Decimal places every emitted confidence/score is rounded to. Matches the
# fusion, recoverability, decision, environmental, circular and integrity engines
# so all engines' numbers compare cleanly.
_SCORE_PRECISION = 6

# The canonical trust sub-axes in fixed declaration order. Emitting the axes in
# this order (rather than iterating the unordered ``CANONICAL_AXES`` frozenset)
# keeps every produced report byte-for-byte reproducible.
_AXIS_ORDER: tuple[str, ...] = (
    "identity_confidence",
    "evidence_consistency",
    "decision_confidence",
    "integrity_confidence",
)


def _clamp_round(value: float) -> float:
    """Clamp ``value`` to ``[0, 1]`` and round to the score precision."""
    return round(max(0.0, min(1.0, value)), _SCORE_PRECISION)


class TrustEngine:
    """Score and level a passport's trustworthiness from the upstream reports."""

    def __init__(self, config: TrustConfig) -> None:
        self._config = config

    @property
    def config(self) -> TrustConfig:
        """Return the configuration this engine scores with."""
        return self._config

    def evaluate(
        self,
        passport: DevicePassport,
        integrity: PassportIntegrityReport,
        knowledge: DecisionKnowledgeReport,
        decision: DecisionReport,
        rules: TrustRuleSet,
        *,
        rules_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> PassportTrustReport:
        """Score and level a passport's trust into a :class:`PassportTrustReport`.

        Args:
            passport: The device passport whose trustworthiness is being
                assessed.
            integrity: The passport's integrity report (validation + hash).
            knowledge: The device's normalized decision-knowledge report.
            decision: The device's actionable circular decision report.
            rules: The resolved trust rule catalogue.
            rules_version: Catalogue version stamped onto the report.
            engine_version: Engine version stamped onto the report.
            created_at: Timestamp stamped onto the report, or ``None``.

        Returns:
            The immutable, auditable :class:`PassportTrustReport`.
        """
        # Stage 1 — project the four upstream reports onto the four trust axes.
        identity = self._identity_confidence(passport)
        evidence = self._evidence_consistency(passport, knowledge, decision)
        decision_axis = self._decision_confidence(knowledge, decision)
        integrity_axis = self._integrity_confidence(integrity)

        axes = self._build_axes(
            values={
                "identity_confidence": identity,
                "evidence_consistency": evidence,
                "decision_confidence": decision_axis,
                "integrity_confidence": integrity_axis,
            },
            rules=rules,
        )

        # Stage 2 — blend the four axes into the normalized trust score.
        trust_score = self._score(axes, rules)

        # Stage 3 — map the score to a trust level via the catalogue thresholds.
        trust_level = rules.level_for(trust_score)

        reasoning, warnings = self._explain(
            passport=passport,
            integrity=integrity,
            trust_score=trust_score,
            trust_level=trust_level,
            axes=axes,
        )

        return PassportTrustReport(
            passport_id=passport.passport_id,
            trust_score=trust_score,
            trust_level=trust_level,
            identity_confidence=identity[0],
            evidence_consistency=evidence[0],
            decision_confidence=decision_axis[0],
            integrity_confidence=integrity_axis[0],
            axes=axes,
            reasoning=reasoning,
            warnings=warnings,
            engine_version=engine_version,
            rules_version=rules_version,
            created_at=created_at,
        )

    def _identity_confidence(self, passport: DevicePassport) -> tuple[float, str]:
        """Project the identity-confidence axis from the passport.

        Identity confidence blends two signals: how many strong identity fields
        the passport carries (model, serial, IMEI, MAC — a proxy for how
        device-specific the evidence is) and how confident fusion was in the
        resolved device type. A passport with all four identity fields and high
        classification confidence scores full identity confidence; one with no
        resolved identity and low classification confidence scores near zero.

        Returns:
            A ``(value, reason)`` pair; the value is clamped to ``[0, 1]``.
        """
        identity = passport.device_identity
        strong_fields = (
            identity.model,
            identity.serial_number,
            identity.imei,
            identity.mac_address,
        )
        field_count = self._config.identity_field_count
        if field_count <= 0:
            completeness = 0.0
        else:
            present = sum(1 for field in strong_fields if field.strip() != "")
            completeness = present / field_count

        classification_conf = passport.classification.confidence
        # Simple mean of the two signals: completeness + classification confidence.
        value = _clamp_round((completeness + classification_conf) / 2.0)
        reason = (
            f"Identity completeness {completeness:g} (strong identity fields "
            f"present) blended with classification confidence "
            f"{classification_conf:g}."
        )
        return value, reason

    def _evidence_consistency(
        self,
        passport: DevicePassport,
        knowledge: DecisionKnowledgeReport,
        decision: DecisionReport,
    ) -> tuple[float, str]:
        """Project the evidence-consistency axis from cross-report agreement.

        Evidence consistency checks whether the three upstream reports that carry
        a device type (passport, knowledge, decision) agree, and whether fusion
        flagged any cross-module conflict. Perfect consistency (all present types
        agree, no conflict flagged) scores ``1.0``; disagreement or a flagged
        conflict lowers the score.

        Returns:
            A ``(value, reason)`` pair; the value is clamped to ``[0, 1]``.
        """
        has_conflicts = passport.classification.has_conflicts
        types = {
            device_type
            for device_type in (
                passport.classification.device_type,
                knowledge.device_type,
                decision.device_type,
            )
            if device_type.strip()
        }

        if not types:
            # No upstream report resolved a device type — consistency is
            # undefined, so it is neither affirmed nor heavily penalized.
            value = 0.5
            reason = (
                "No upstream report resolved a device type; cross-report "
                "consistency is undefined."
            )
        elif len(types) == 1:
            device_type = next(iter(types))
            if has_conflicts:
                value = 0.8
                reason = (
                    f"Upstream reports agree on device type '{device_type}', but "
                    "fusion flagged a cross-module conflict."
                )
            else:
                value = 1.0
                reason = (
                    f"All upstream reports agree on device type '{device_type}' "
                    "with no conflicts flagged."
                )
        else:
            listed = ", ".join(f"'{device_type}'" for device_type in sorted(types))
            if has_conflicts:
                value = 0.2
                reason = (
                    f"Upstream reports disagree on device type ({listed}) and "
                    "fusion flagged a cross-module conflict."
                )
            else:
                value = 0.4
                reason = (
                    f"Upstream reports disagree on device type ({listed}) with no "
                    "additional conflict flagged."
                )

        return _clamp_round(value), reason

    def _decision_confidence(
        self,
        knowledge: DecisionKnowledgeReport,
        decision: DecisionReport,
    ) -> tuple[float, str]:
        """Project the decision-confidence axis from the two decision reports.

        Decision confidence is the arithmetic mean of the circular decision
        report's confidence and the decision-knowledge report's overall
        confidence. Both are already normalized ``[0, 1]`` values from their
        respective engines.

        Returns:
            A ``(value, reason)`` pair; the value is clamped to ``[0, 1]``.
        """
        knowledge_conf = knowledge.overall_confidence
        decision_conf = decision.confidence
        value = _clamp_round((knowledge_conf + decision_conf) / 2.0)
        reason = (
            f"Mean of decision-knowledge confidence {knowledge_conf:g} and "
            f"circular-decision confidence {decision_conf:g}."
        )
        return value, reason

    def _integrity_confidence(
        self, integrity: PassportIntegrityReport
    ) -> tuple[float, str]:
        """Project the integrity-confidence axis from the integrity report.

        Integrity confidence reads the passport's validation status: a VALID
        passport scores ``1.0``, a VALID_WITH_WARNINGS passport is damped one
        penalty per warning, and an INVALID passport scores ``0.0``.

        Returns:
            A ``(value, reason)`` pair; the value is clamped to ``[0, 1]``.
        """
        status = integrity.status
        warning_count = integrity.warning_count

        if status is ValidationStatus.INVALID:
            value = 0.0
            reason = "Passport failed integrity validation (status 'invalid')."
        elif status is ValidationStatus.VALID_WITH_WARNINGS:
            penalty = self._config.integrity_warning_penalty * warning_count
            value = _clamp_round(1.0 - penalty)
            reason = (
                f"Passport passed validation with {warning_count} warning(s); "
                f"integrity damped by {penalty:g}."
            )
        else:  # ValidationStatus.VALID
            value = 1.0
            reason = "Passport passed integrity validation with no warnings."

        return value, reason

    def _build_axes(
        self,
        *,
        values: dict[str, tuple[float, str]],
        rules: TrustRuleSet,
    ) -> tuple[TrustAxis, ...]:
        """Build the ordered axis records with their catalogue weights.

        The axes are emitted in fixed canonical order (identity, evidence,
        decision, integrity) so the report is byte-for-byte reproducible.
        """
        axes: list[TrustAxis] = []
        for axis_name in _AXIS_ORDER:
            value, reason = values[axis_name]
            axes.append(
                TrustAxis(
                    name=axis_name,
                    value=value,
                    weight=rules.weight_for(axis_name),
                    reason=reason,
                )
            )
        return tuple(axes)

    def _score(self, axes: tuple[TrustAxis, ...], rules: TrustRuleSet) -> float:
        """Blend the four axes into the normalized trust score.

        The trust score is the weighted average of the four axes: the sum of
        (value × weight) divided by the total weight. Because the loader
        guarantees a positive total weight, the average is always well-defined.
        """
        total_weight = rules.total_weight
        if total_weight <= 0.0:
            return 0.0
        weighted_sum = sum(axis.value * axis.weight for axis in axes)
        return _clamp_round(weighted_sum / total_weight)

    def _explain(
        self,
        *,
        passport: DevicePassport,
        integrity: PassportIntegrityReport,
        trust_score: float,
        trust_level: TrustLevel,
        axes: tuple[TrustAxis, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Build the ordered report-level reasoning and warnings."""
        reasoning: list[str] = [
            f"Trust score {trust_score:g} maps to level '{trust_level.value}' via "
            "the catalogue thresholds.",
            "The score is the weighted average of the four trust sub-axes: "
            "identity confidence, evidence consistency, decision confidence and "
            "integrity confidence.",
        ]
        for axis in axes:
            reasoning.append(
                f"Axis '{axis.name}': value {axis.value:g} (weight {axis.weight:g}). "
                f"{axis.reason}"
            )

        warnings: list[str] = []
        if trust_score <= self._config.min_trust_score:
            warnings.append(
                f"Trust score ({trust_score:g}) is at or below the configured floor "
                f"({self._config.min_trust_score:g}); treat this passport as "
                "low-trust and confirm its claims before relying on it."
            )
        if not integrity.is_valid:
            warnings.append(
                "Passport failed integrity validation; its structural soundness is "
                "questionable and the trust verdict should not be relied upon "
                "without manual verification."
            )
        if integrity.warning_count > 0:
            warnings.append(
                f"Passport integrity report carries {integrity.warning_count} "
                "warning(s); review the integrity report for details."
            )
        if passport.warnings:
            warnings.append(
                f"Passport itself carries {len(passport.warnings)} warning(s) from "
                "its upstream reports; review the passport for details."
            )

        return tuple(reasoning), tuple(warnings)
