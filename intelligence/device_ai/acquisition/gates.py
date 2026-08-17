"""Source verification — compose the license, bbox and semantic gates.

A candidate source is *accepted for acquisition* only when **all three** of the
following hold, each established explicitly and recorded with its exact reason:

1. **License gate** (:mod:`device_ai.acquisition.licenses`) — an explicit,
   allowlisted permissive license. Missing/unknown => ``UNVERIFIED``; restricted
   => ``REJECTED``. Never inferred.
2. **Bbox availability** — the source must carry *bounding boxes*. A
   classification-only source is rejected outright: image-classification tags are
   never promoted to detection labels.
3. **Semantic gate** (:mod:`device_ai.acquisition.semantics`) — at least one of
   the source's own class labels must *explicitly* denote ``router``. Ambiguous
   labels (``modem/router``, ``gateway``, ``networking device``, ...) never
   qualify.

The verdict is deliberately three-valued so an unverifiable source is never
silently downgraded to a rejection nor upgraded to an acceptance: ``ACCEPTED``,
``REJECTED`` (a definite, explicit incompatibility) and ``UNVERIFIED`` (the
evidence needed to decide is absent).

The semantic gate can only be applied to labels the source actually declares.
For a **local** source the pipeline materialises the archive, detects its format
and reads its distinct annotation labels *before* verification, so the gate
always rules on the source's real label set. ``labels=None`` therefore only
arises for a remote coordinate that declared no class label; that is a genuine
evidence gap and yields ``UNVERIFIED`` (``DEFERRED_TO_INGEST`` on the semantic
stage) rather than an acceptance. Acceptance here is a *source-level* clearance;
the per-box semantic gate still rules on every individual annotation at ingest,
so a mixed-label source contributes only its explicit router boxes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .adapters.base import SourceCandidate
from .licenses import LicenseDecision, evaluate_license
from .semantics import SemanticDecision, evaluate_source_label

# Verdicts (stable, machine-readable).
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
UNVERIFIED = "UNVERIFIED"

# Semantic-stage markers used when no label set is available yet.
DEFERRED_TO_INGEST = "DEFERRED_TO_INGEST"


@dataclass(frozen=True, slots=True)
class SourceVerdict:
    """Combined gate outcome for one candidate source.

    Attributes:
        candidate: The candidate that was evaluated.
        verdict: :data:`ACCEPTED`, :data:`REJECTED` or :data:`UNVERIFIED`.
        license_decision: The license gate outcome.
        bbox_verdict: ``ACCEPTED`` when bounding boxes are available, else
            ``REJECTED`` (classification-only) — never inferred.
        bbox_reason: Exact reason for the bbox verdict.
        semantic_verdict: ``ACCEPTED``/``REJECTED``/:data:`DEFERRED_TO_INGEST`.
        semantic_decisions: Per-label semantic decisions (empty when deferred).
        accepted_labels: Source labels that cleared the semantic gate.
        rejected_labels: Source labels the semantic gate rejected.
        reasons: Ordered, exact reasons contributing to the verdict.
    """

    candidate: SourceCandidate
    verdict: str
    license_decision: LicenseDecision
    bbox_verdict: str
    bbox_reason: str
    semantic_verdict: str
    semantic_decisions: tuple[SemanticDecision, ...] = ()
    accepted_labels: tuple[str, ...] = ()
    rejected_labels: tuple[str, ...] = ()
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def accepted(self) -> bool:
        """Whether the source cleared every gate."""
        return self.verdict == ACCEPTED

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "source": self.candidate.to_dict(),
            "verdict": self.verdict,
            "license": self.license_decision.to_dict(),
            "bbox": {"verdict": self.bbox_verdict, "reason": self.bbox_reason},
            "semantic": {
                "verdict": self.semantic_verdict,
                "accepted_labels": list(self.accepted_labels),
                "rejected_labels": list(self.rejected_labels),
                "decisions": [d.to_dict() for d in self.semantic_decisions],
            },
            "reasons": list(self.reasons),
        }


def _bbox_gate(candidate: SourceCandidate) -> tuple[str, str]:
    """Return the ``(verdict, reason)`` of the bbox-availability gate."""
    if candidate.bbox_available:
        return (
            ACCEPTED,
            "source declares bounding-box annotations suitable for detection",
        )
    return (
        REJECTED,
        (
            "no bounding-box annotations available; classification-only data is "
            "never promoted to bbox detection labels"
        ),
    )


def _semantic_gate(
    labels: list[str] | None,
) -> tuple[str, tuple[SemanticDecision, ...], tuple[str, ...], tuple[str, ...], str]:
    """Evaluate every declared source label for the router class.

    Args:
        labels: The source's own class labels, or ``None`` when they are not yet
            known (a local archive before ingestion).

    Returns:
        ``(verdict, decisions, accepted, rejected, reason)``.
    """
    if labels is None:
        return (
            DEFERRED_TO_INGEST,
            (),
            (),
            (),
            (
                "source labels are not declared up front; the per-box semantic "
                "gate is applied to every annotation during ingestion"
            ),
        )

    decisions = tuple(evaluate_source_label(label) for label in labels)
    accepted = tuple(d.raw_label for d in decisions if d.accepted)
    rejected = tuple(d.raw_label for d in decisions if not d.accepted)
    if accepted:
        return (
            ACCEPTED,
            decisions,
            accepted,
            rejected,
            f"{len(accepted)} source label(s) explicitly denote 'router'",
        )
    if not decisions:
        return (
            REJECTED,
            decisions,
            accepted,
            rejected,
            "source declares no class labels; 'router' cannot be established",
        )
    categories = sorted({d.category for d in decisions})
    return (
        REJECTED,
        decisions,
        accepted,
        rejected,
        (
            "no source label explicitly denotes 'router' "
            f"(categories: {', '.join(categories)})"
        ),
    )


def verify_source(
    candidate: SourceCandidate, *, labels: list[str] | None = None
) -> SourceVerdict:
    """Run the license, bbox and semantic gates over one candidate source.

    Args:
        candidate: The discovered source metadata.
        labels: The source's declared class labels. ``None`` defers the semantic
            decision to per-box evaluation at ingest time (a local archive).

    Returns:
        A :class:`SourceVerdict`. The verdict is ``REJECTED`` when any gate
        returns an explicit incompatibility, ``UNVERIFIED`` when required
        evidence (a license, or a declared label set) is absent, and
        ``ACCEPTED`` only when every gate cleared.
    """
    license_decision = evaluate_license(
        candidate.license_raw, license_url=candidate.license_url
    )
    bbox_verdict, bbox_reason = _bbox_gate(candidate)
    (
        semantic_verdict,
        semantic_decisions,
        accepted_labels,
        rejected_labels,
        semantic_reason,
    ) = _semantic_gate(labels)

    reasons: list[str] = [
        f"license: {license_decision.reason}",
        f"bbox: {bbox_reason}",
        f"semantic: {semantic_reason}",
    ]

    # An explicit incompatibility on any gate rejects the source outright.
    if license_decision.verdict == REJECTED or bbox_verdict == REJECTED:
        verdict = REJECTED
    elif semantic_verdict == REJECTED:
        verdict = REJECTED
    elif license_decision.verdict == UNVERIFIED:
        verdict = UNVERIFIED
    elif semantic_verdict == DEFERRED_TO_INGEST:
        # Licence + bbox cleared but router semantics are not yet established.
        verdict = UNVERIFIED
    else:
        verdict = ACCEPTED

    return SourceVerdict(
        candidate=candidate,
        verdict=verdict,
        license_decision=license_decision,
        bbox_verdict=bbox_verdict,
        bbox_reason=bbox_reason,
        semantic_verdict=semantic_verdict,
        semantic_decisions=semantic_decisions,
        accepted_labels=accepted_labels,
        rejected_labels=rejected_labels,
        reasons=tuple(reasons),
    )


def summarize_verdicts(verdicts: list[SourceVerdict]) -> dict[str, object]:
    """Aggregate a set of source verdicts for the run report.

    Args:
        verdicts: Every verified candidate.

    Returns:
        A primitive-only mapping with per-verdict counts and the exact reason
        recorded against every non-accepted source.
    """
    counts = {ACCEPTED: 0, REJECTED: 0, UNVERIFIED: 0}
    for verdict in verdicts:
        counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
    return {
        "discovered": len(verdicts),
        "accepted": counts[ACCEPTED],
        "rejected": counts[REJECTED],
        "unverified": counts[UNVERIFIED],
        "verdicts": [v.to_dict() for v in verdicts],
    }
