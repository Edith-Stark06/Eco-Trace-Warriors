"""Decision-knowledge domain models (milestone M2.1).

The Decision Knowledge Engine turns the five upstream device-intelligence
reports — a fused :class:`~device_ai.fusion.models.DeviceContext` (M1.7), its
:class:`~device_ai.recoverability.models.RecoverabilityReport` (M1.8), its
:class:`~device_ai.components.models.ComponentReport` (M1.9), its
:class:`~device_ai.materials.models.MaterialReport` (M1.10) and its
:class:`~device_ai.environmental.models.EnvironmentalImpactReport` (M1.11) — into
a single, normalized :class:`DecisionKnowledgeReport`.

The report is **normalized evidence only**. It answers *"how much does each
decision dimension weigh for this device"* on a common ``[0, 1]`` scale; it does
**not** answer *"what should be done"*. There is deliberately no recommended
action, no economic valuation and no optimization here — the engine consolidates
the upstream signals into comparable evidence so that a later decision layer (out
of scope for this milestone) has one clean, auditable input.

The value objects here are the vocabulary that makes that consolidation
auditable:

* :class:`DecisionDimension` — the six normalized dimensions the engine scores
  (repairability, reusability, recycling, hazard, environmental priority and
  material value). A ``str`` enum so members serialize to their wire value
  directly and are the single source of truth the external knowledge catalogue
  is validated against.
* :class:`EvidenceSignal` — one normalized ``[0, 1]`` input signal (projected
  from an upstream report) and the weight it carries within a dimension. Summing
  ``value × weight`` over a dimension's signals and dividing by the total weight
  yields that dimension's score, so every score is a transparent weighted average
  rather than a black-box number.
* :class:`DimensionEvidence` — one dimension's normalized score together with the
  ordered signals it blended and a human-readable reason.
* :class:`DecisionKnowledgeReport` — the normalized, immutable outcome: the six
  dimension scores, a **separate** overall-confidence axis, the per-dimension
  evidence breakdown, ordered reasoning/warnings and provenance (EcoID, device
  type, engine and knowledge-catalogue versions, timestamp).

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the fusion,
recoverability, component, material and environmental domain layers it builds on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DecisionDimension(str, Enum):
    """The normalized decision dimension the engine scores.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a catalogue string (e.g. ``"environmental_priority"``). This
    enum is the single source of truth the external knowledge catalogue is
    validated against on load — a catalogue naming a dimension outside this set,
    or omitting one of these, is rejected.

    Every dimension is normalized evidence in ``[0, 1]``; none is a recommended
    action. ``HAZARD`` is the *amount of hazard evidence* (higher = more
    hazardous), not a disposal instruction.
    """

    REPAIRABILITY = "repairability"
    REUSABILITY = "reusability"
    RECYCLING = "recycling"
    HAZARD = "hazard"
    ENVIRONMENTAL_PRIORITY = "environmental_priority"
    MATERIAL_VALUE = "material_value"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every dimension, in declaration order."""
        return [member.value for member in cls]


@dataclass(frozen=True, slots=True)
class EvidenceSignal:
    """One normalized input signal's weighted contribution to a dimension.

    A dimension score is the weighted average of its signals: each signal carries
    a normalized ``value`` in ``[0, 1]`` (projected from an upstream report) and a
    non-negative ``weight`` from the knowledge catalogue. Retaining both on the
    report is what makes a score explainable — an operator can see exactly which
    upstream evidence moved it and by how much.

    Attributes:
        name: Machine-readable signal name (e.g. ``"recyclability"``); one of the
            engine's canonical signal names.
        value: The normalized ``[0, 1]`` signal value projected from upstream.
        weight: The non-negative weight this signal carries within its dimension
            (as configured in the knowledge catalogue).
    """

    name: str
    value: float
    weight: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the signal."""
        return {
            "name": self.name,
            "value": self.value,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class DimensionEvidence:
    """One decision dimension's normalized score and the signals behind it.

    Attributes:
        dimension: The :class:`DecisionDimension` this evidence scores.
        score: The normalized ``[0, 1]`` dimension score — the weighted average of
            the ``signals`` (each ``value`` weighted by its ``weight``).
        signals: The ordered normalized input signals that were blended into the
            score (in knowledge-catalogue order; may be empty when no signal
            carried a positive weight, in which case the score is ``0``).
        reason: Human-readable explanation of how the score was derived.
    """

    dimension: DecisionDimension
    score: float
    signals: tuple[EvidenceSignal, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the dimension evidence."""
        return {
            "dimension": self.dimension.value,
            "score": self.score,
            "signals": [signal.to_dict() for signal in self.signals],
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DecisionKnowledgeReport:
    """The normalized, immutable decision-knowledge evidence of one device.

    Produced by the
    :class:`~device_ai.decision.service.DecisionService` from the five upstream
    reports. It is the consolidated, comparable evidence a later decision layer
    consumes — **not** a decision. The six dimension scores are normalized
    ``[0, 1]`` measures; :attr:`overall_confidence` is a separate axis and never
    scales a score.

    Attributes:
        device_type: The resolved device type the evidence is for (may be empty
            when fusion could not determine it).
        repairability_score: Normalized ``[0, 1]`` weight of the repairability
            evidence (ease of putting the device back into service).
        reusability_score: Normalized ``[0, 1]`` weight of the reuse evidence
            (fitness for a second life as-is).
        recycling_score: Normalized ``[0, 1]`` weight of the material-recovery
            evidence (fitness for the recycling stream).
        hazard_score: Normalized ``[0, 1]`` weight of the hazard evidence (how
            much hazardous handling the device demands; higher = more hazardous).
        environmental_priority: Normalized ``[0, 1]`` weight of the environmental
            stake (how much avoided burden rides on handling this device well).
        material_value_score: Normalized ``[0, 1]`` index of the recoverable
            material worth (critical-material presence + recoverable mass +
            embodied-burden proxy). A unit index, **not** a monetary value.
        overall_confidence: Aggregated confidence ``[0, 1]`` in the evidence as a
            whole, blended from the five upstream confidences and kept wholly
            separate from the scores (it never scales a dimension).
        dimensions: The ordered per-dimension evidence breakdown, in
            :class:`DecisionDimension` order.
        reasoning: Ordered, human-readable reasons behind the evidence.
        warnings: Ordered operator-facing cautions (may be empty).
        eco_id: Public EcoID carried over from the device context (empty when the
            context had no fingerprint).
        engine_version: Version of the decision engine that produced this.
        knowledge_version: Version of the external knowledge catalogue used.
        created_at: UTC timestamp the report was produced (``None`` when the
            service was constructed without a clock).
    """

    device_type: str
    repairability_score: float
    reusability_score: float
    recycling_score: float
    hazard_score: float
    environmental_priority: float
    material_value_score: float
    overall_confidence: float
    dimensions: tuple[DimensionEvidence, ...]
    reasoning: tuple[str, ...]
    warnings: tuple[str, ...]
    eco_id: str = ""
    engine_version: str = ""
    knowledge_version: str = ""
    created_at: datetime | None = None

    @property
    def dimension_count(self) -> int:
        """Return the number of scored decision dimensions."""
        return len(self.dimensions)

    def score_for(self, dimension: DecisionDimension) -> float:
        """Return the normalized score for ``dimension`` (``0.0`` when absent).

        Args:
            dimension: The dimension to read the score of.

        Returns:
            The dimension's normalized ``[0, 1]`` score, or ``0.0`` when the
            dimension is not present in the report.
        """
        for evidence in self.dimensions:
            if evidence.dimension is dimension:
                return evidence.score
        return 0.0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the report.

        Returns:
            A plain ``dict`` with the six normalized dimension scores, the
            separate overall confidence, the ordered per-dimension evidence
            breakdown, the reasoning/warnings, provenance and an ISO-8601
            ``created_at`` (or ``None``).
        """
        return {
            "eco_id": self.eco_id,
            "device_type": self.device_type,
            "repairability_score": self.repairability_score,
            "reusability_score": self.reusability_score,
            "recycling_score": self.recycling_score,
            "hazard_score": self.hazard_score,
            "environmental_priority": self.environmental_priority,
            "material_value_score": self.material_value_score,
            "overall_confidence": self.overall_confidence,
            "dimensions": [evidence.to_dict() for evidence in self.dimensions],
            "dimension_count": self.dimension_count,
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
            "engine_version": self.engine_version,
            "knowledge_version": self.knowledge_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }
