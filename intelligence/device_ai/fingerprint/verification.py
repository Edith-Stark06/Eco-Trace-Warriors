"""Verification engine (milestone M1.5).

The :class:`VerificationEngine` compares two :class:`DeviceFingerprint`
records and returns a :class:`VerificationResult` carrying the similarity
score and a **match / no-match decision**. The decision is a metric-agnostic
threshold applied to the normalized similarity in ``[0, 1]`` produced by
:mod:`device_ai.fingerprint.similarity`, so switching metrics never changes
the decision semantics.

The engine is deliberately tiny and pure: threshold and default metric are
injected (from settings), and the comparison itself defers to the similarity
module. Fingerprints from different-dimensioned embeddings cannot be compared
and raise :class:`FingerprintMismatchError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import DeviceFingerprint
from .similarity import SimilarityMetric, compute_similarity


class VerificationDecision(str, Enum):
    """The outcome of a fingerprint verification."""

    MATCH = "match"
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Result of verifying two fingerprints against each other.

    Attributes:
        metric: The similarity metric used.
        similarity: Normalized similarity in ``[0, 1]`` (``1.0`` = identical).
        distance: Raw geometric distance for the metric (lower = more similar).
        threshold: Similarity threshold the decision was taken against.
        decision: ``MATCH`` when ``similarity >= threshold`` else ``NO_MATCH``.
        left_eco_id: EcoID of the first fingerprint.
        right_eco_id: EcoID of the second fingerprint.
    """

    metric: SimilarityMetric
    similarity: float
    distance: float
    threshold: float
    decision: VerificationDecision
    left_eco_id: str
    right_eco_id: str

    @property
    def is_match(self) -> bool:
        """Whether the verification decided the fingerprints match."""
        return self.decision is VerificationDecision.MATCH


class VerificationEngine:
    """Compare fingerprints and decide match/no-match against a threshold.

    Args:
        threshold: Similarity (``0..1``) at or above which two fingerprints are
            judged a match.
        metric: Default similarity metric used when a comparison does not
            specify one.
    """

    def __init__(
        self,
        *,
        threshold: float,
        metric: str | SimilarityMetric = SimilarityMetric.COSINE,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        self._threshold = threshold
        self._metric = SimilarityMetric.from_name(metric)

    @property
    def threshold(self) -> float:
        """The configured match threshold."""
        return self._threshold

    @property
    def metric(self) -> SimilarityMetric:
        """The configured default similarity metric."""
        return self._metric

    def verify(
        self,
        left: DeviceFingerprint,
        right: DeviceFingerprint,
        *,
        metric: str | SimilarityMetric | None = None,
    ) -> VerificationResult:
        """Verify whether two fingerprints represent the same device.

        Args:
            left: The first fingerprint.
            right: The second fingerprint.
            metric: Optional metric override for this comparison; defaults to
                the engine's configured metric.

        Returns:
            A :class:`VerificationResult` with the similarity and decision.

        Raises:
            FingerprintMismatchError: If the embeddings differ in dimension.
            UnknownSimilarityMetricError: If ``metric`` is unsupported.
        """
        resolved_metric = (
            self._metric if metric is None else SimilarityMetric.from_name(metric)
        )
        score = compute_similarity(left.embedding, right.embedding, resolved_metric)
        decision = (
            VerificationDecision.MATCH
            if score.similarity >= self._threshold
            else VerificationDecision.NO_MATCH
        )
        return VerificationResult(
            metric=score.metric,
            similarity=score.similarity,
            distance=score.distance,
            threshold=self._threshold,
            decision=decision,
            left_eco_id=left.eco_id,
            right_eco_id=right.eco_id,
        )
