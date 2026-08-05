"""Trust & provenance domain models (milestone M2.5).

The Trust & Provenance Engine is a **scoring and leveling** engine, not an
inference or composition engine. It consumes four upstream artefacts — the
immutable :class:`~device_ai.passport.models.DevicePassport` the passport core
(M2.3) produced, the :class:`~device_ai.integrity.models.PassportIntegrityReport`
the integrity engine (M2.4) validated and hashed, the normalized
:class:`~device_ai.decision.models.DecisionKnowledgeReport` (M2.1), and the
actionable :class:`~device_ai.circular.models.DecisionReport` (M2.2) — and emits
a single, immutable :class:`PassportTrustReport` that answers one question:
*how trustworthy is this passport as a representation of the device?*

The engine derives **no new inference** and **no new evidence**. It reads the
four upstream reports' existing confidence and consistency signals (identity
completeness + classification confidence; cross-report device-type agreement;
decision/knowledge confidence mean; integrity soundness), blends them into a
normalized **trust score** via catalogue-driven weights, and maps that score to
a **trust level** (HIGH / MEDIUM / LOW / UNTRUSTED) via catalogue thresholds.
The result is a transparent, auditable trust verdict with ordered reasoning and
warnings — so an operator or a later blockchain/anchor layer knows how much
confidence to place in the passport's claim.

The value objects here are the vocabulary of that verdict:

* :class:`TrustLevel` — the overall trust verdict mapped from the score
  (``high`` / ``medium`` / ``low`` / ``untrusted``). A ``str`` enum so members
  serialize to their wire value directly and are the single source of truth the
  external trust catalogue is validated against.
* :class:`TrustAxis` — one normalized ``[0, 1]`` trust sub-axis (Identity
  Confidence, Evidence Consistency, Decision Confidence, Integrity Confidence),
  its blend weight, and a human-readable reason. Retaining the axes on the
  report is what makes the trust score explainable — an operator can see which
  upstream evidence moved it and by how much.
* :class:`PassportTrustReport` — the immutable verdict: the normalized trust
  score, the trust level, the four sub-axes, the ordered reasoning/warnings
  and provenance (passport id, engine/catalogue versions, timestamp).

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the
passport, integrity, decision and circular domain layers it builds on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "PassportTrustReport",
    "TrustAxis",
    "TrustLevel",
]


class TrustLevel(str, Enum):
    """The overall trust verdict mapped from the normalized trust score.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a catalogue string (e.g. ``"medium"``). This enum is the
    single source of truth the external trust catalogue is validated against on
    load — a catalogue naming a level outside this set is rejected.

    Ordering is by descending trust: ``HIGH`` is the most trustworthy, ``LOW``
    flags caution, and ``UNTRUSTED`` marks a passport that should not be relied
    upon without manual verification.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNTRUSTED = "untrusted"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every trust level, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class TrustAxis:
    """One normalized trust sub-axis's weighted contribution to the trust score.

    The trust score is the weighted average of the four axes: each axis carries
    a normalized ``value`` in ``[0, 1]`` (projected from the upstream reports)
    and a non-negative ``weight`` from the trust catalogue. Retaining both on
    the report is what makes a score explainable — an operator can see exactly
    which upstream evidence moved it and by how much.

    Attributes:
        name: Machine-readable axis name (e.g. ``"identity_confidence"``); one
            of the engine's canonical four axis names.
        value: The normalized ``[0, 1]`` axis value projected from upstream.
        weight: The non-negative weight this axis carries within the trust
            score (as configured in the trust catalogue).
        reason: Human-readable explanation of how the axis value was derived.
    """

    name: str
    value: float
    weight: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the trust axis."""
        return {
            "name": self.name,
            "value": self.value,
            "weight": self.weight,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PassportTrustReport:
    """The immutable trust verdict of one device passport.

    Produced by the :class:`~device_ai.trust.service.TrustService` from the
    passport and its three upstream reports. It is a **verdict on the
    passport's trustworthiness** — downstream operators or blockchain/anchor
    layers consume this to decide how much confidence to place in the
    passport's claim. The trust score and level are transparent functions of
    the four sub-axes, which are themselves transparent projections from
    upstream confidence and consistency signals.

    Attributes:
        passport_id: The id of the passport that was assessed (provenance).
        trust_score: Normalized ``[0, 1]`` trust score — the weighted average
            of the four sub-axes.
        trust_level: The :class:`TrustLevel` verdict mapped from the score via
            catalogue thresholds.
        identity_confidence: Axis value measuring identity completeness and
            classification confidence.
        evidence_consistency: Axis value measuring cross-report agreement.
        decision_confidence: Axis value measuring decision/knowledge confidence.
        integrity_confidence: Axis value measuring integrity soundness.
        axes: The ordered four sub-axes with their values, weights and reasons,
            in canonical order (identity, consistency, decision, integrity).
        reasoning: Ordered, human-readable reasons behind the verdict.
        warnings: Ordered operator-facing cautions (may be empty).
        engine_version: Version of the trust engine that produced this.
        rules_version: Version of the external trust catalogue used.
        created_at: UTC timestamp the report was produced (``None`` when the
            service was constructed without a clock).
    """

    passport_id: str
    trust_score: float
    trust_level: TrustLevel
    identity_confidence: float
    evidence_consistency: float
    decision_confidence: float
    integrity_confidence: float
    axes: tuple[TrustAxis, ...]
    reasoning: tuple[str, ...]
    warnings: tuple[str, ...]
    engine_version: str = ""
    rules_version: str = ""
    created_at: datetime | None = None

    @property
    def axis_count(self) -> int:
        """Return the number of trust axes (always four)."""
        return len(self.axes)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report.

        The keys are emitted in a fixed, logical order, so the mapping is a
        deterministic function of the inputs (the only source of variation is
        the optional ``created_at`` timestamp).

        Returns:
            A plain ``dict`` with the trust score and level, the four axis
            values, the ordered axes breakdown, the reasoning/warnings,
            provenance and an ISO-8601 ``created_at`` (or ``None``).
        """
        return {
            "passport_id": self.passport_id,
            "trust_score": self.trust_score,
            "trust_level": self.trust_level.value,
            "identity_confidence": self.identity_confidence,
            "evidence_consistency": self.evidence_consistency,
            "decision_confidence": self.decision_confidence,
            "integrity_confidence": self.integrity_confidence,
            "axes": [axis.to_dict() for axis in self.axes],
            "axis_count": self.axis_count,
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
            "engine_version": self.engine_version,
            "rules_version": self.rules_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the report.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same report always serializes to the exact
        same bytes. Because :meth:`to_dict` is a pure function of the inputs,
        the only source of variation is the optional ``created_at`` timestamp.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )
