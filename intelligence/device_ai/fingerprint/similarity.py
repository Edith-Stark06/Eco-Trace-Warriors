"""Configurable similarity metrics for embedding comparison (milestone M1.5).

Each metric maps a pair of equal-length embedding vectors to a
:class:`SimilarityScore` carrying both the raw geometric quantity (cosine
value or distance) and a **normalized similarity in ``[0, 1]``** where ``1.0``
means "identical". Normalizing every metric onto the same scale lets the
verification engine apply a single, metric-agnostic decision threshold.

The implementations are **pure Python** and dependency-free (``math.fsum`` for
numerically stable summation, no NumPy), so the whole engine runs unchanged in
the base environment.

Metrics
-------
* ``cosine``    — ``(1 + cos θ) / 2``; distance reported as ``1 - cos θ``.
* ``euclidean`` — ``1 / (1 + d)`` where ``d`` is the L2 distance.
* ``manhattan`` — ``1 / (1 + d)`` where ``d`` is the L1 distance.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from ..exceptions import FingerprintMismatchError, UnknownSimilarityMetricError

Vector = Sequence[float]


class SimilarityMetric(str, Enum):
    """Supported similarity metrics.

    A ``str`` enum so members serialize to their wire value directly and can
    be constructed from the settings/API string (e.g. ``"cosine"``).
    """

    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"

    @classmethod
    def from_name(cls, name: str | SimilarityMetric) -> SimilarityMetric:
        """Return the metric for ``name``, raising on an unknown value.

        Args:
            name: A metric name (case-insensitive) or an existing member.

        Returns:
            The matching :class:`SimilarityMetric`.

        Raises:
            UnknownSimilarityMetricError: If ``name`` is not a supported metric.
        """
        if isinstance(name, cls):
            return name
        try:
            return cls(str(name).lower())
        except ValueError as exc:
            supported = ", ".join(metric.value for metric in cls)
            raise UnknownSimilarityMetricError(
                f"Unknown similarity metric '{name}'. Supported: {supported}.",
                details={"metric": str(name), "supported": supported},
            ) from exc


@dataclass(frozen=True, slots=True)
class SimilarityScore:
    """Outcome of comparing two embedding vectors.

    Attributes:
        metric: The metric used for the comparison.
        similarity: Normalized similarity in ``[0, 1]`` (``1.0`` = identical).
        distance: The raw geometric distance/dissimilarity for the metric
            (``1 - cos θ`` for cosine, the L2/L1 distance otherwise). Lower
            means more similar.
    """

    metric: SimilarityMetric
    similarity: float
    distance: float


def _check_dimensions(a: Vector, b: Vector) -> None:
    """Raise :class:`FingerprintMismatchError` when lengths differ."""
    if len(a) != len(b):
        raise FingerprintMismatchError(
            "Cannot compare embeddings of different dimensionality.",
            details={"left_dimension": len(a), "right_dimension": len(b)},
        )


def _dot(a: Vector, b: Vector) -> float:
    """Return the dot product of two equal-length vectors."""
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def _norm(a: Vector) -> float:
    """Return the Euclidean (L2) norm of a vector."""
    return math.sqrt(math.fsum(x * x for x in a))


def cosine_similarity(a: Vector, b: Vector) -> SimilarityScore:
    """Compare two vectors by cosine of the angle between them.

    The cosine value in ``[-1, 1]`` is mapped to a similarity in ``[0, 1]`` via
    ``(1 + cos θ) / 2``. When either vector is the zero vector the cosine is
    undefined and similarity is reported as ``0.0``.

    Args:
        a: First embedding vector.
        b: Second embedding vector (same length as ``a``).

    Returns:
        The :class:`SimilarityScore` with ``distance = 1 - cos θ``.
    """
    _check_dimensions(a, b)
    norm_a = _norm(a)
    norm_b = _norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return SimilarityScore(SimilarityMetric.COSINE, similarity=0.0, distance=1.0)
    cosine = _dot(a, b) / (norm_a * norm_b)
    # Guard against tiny floating-point excursions beyond the valid range.
    cosine = max(-1.0, min(1.0, cosine))
    similarity = (1.0 + cosine) / 2.0
    return SimilarityScore(
        SimilarityMetric.COSINE,
        similarity=similarity,
        distance=1.0 - cosine,
    )


def euclidean_similarity(a: Vector, b: Vector) -> SimilarityScore:
    """Compare two vectors by Euclidean (L2) distance.

    The distance ``d`` is mapped to a bounded similarity via ``1 / (1 + d)`` so
    identical vectors score ``1.0`` and similarity decreases monotonically as
    distance grows.

    Args:
        a: First embedding vector.
        b: Second embedding vector (same length as ``a``).

    Returns:
        The :class:`SimilarityScore` with ``distance`` = the L2 distance.
    """
    _check_dimensions(a, b)
    distance = math.sqrt(math.fsum((x - y) ** 2 for x, y in zip(a, b, strict=True)))
    return SimilarityScore(
        SimilarityMetric.EUCLIDEAN,
        similarity=1.0 / (1.0 + distance),
        distance=distance,
    )


def manhattan_similarity(a: Vector, b: Vector) -> SimilarityScore:
    """Compare two vectors by Manhattan (L1) distance.

    The distance ``d`` is mapped to a bounded similarity via ``1 / (1 + d)``.

    Args:
        a: First embedding vector.
        b: Second embedding vector (same length as ``a``).

    Returns:
        The :class:`SimilarityScore` with ``distance`` = the L1 distance.
    """
    _check_dimensions(a, b)
    distance = math.fsum(abs(x - y) for x, y in zip(a, b, strict=True))
    return SimilarityScore(
        SimilarityMetric.MANHATTAN,
        similarity=1.0 / (1.0 + distance),
        distance=distance,
    )


#: Registry mapping each metric to its implementation. New metrics are added
#: here in one place; callers dispatch via :func:`compute_similarity`.
_METRICS: dict[SimilarityMetric, Callable[[Vector, Vector], SimilarityScore]] = {
    SimilarityMetric.COSINE: cosine_similarity,
    SimilarityMetric.EUCLIDEAN: euclidean_similarity,
    SimilarityMetric.MANHATTAN: manhattan_similarity,
}


def compute_similarity(
    a: Vector,
    b: Vector,
    metric: str | SimilarityMetric = SimilarityMetric.COSINE,
) -> SimilarityScore:
    """Compare two vectors using the named metric.

    Args:
        a: First embedding vector.
        b: Second embedding vector (same length as ``a``).
        metric: The metric to use (name or :class:`SimilarityMetric`).

    Returns:
        The :class:`SimilarityScore` for the chosen metric.

    Raises:
        UnknownSimilarityMetricError: If ``metric`` is not supported.
        FingerprintMismatchError: If the vectors differ in length.
    """
    resolved = SimilarityMetric.from_name(metric)
    return _METRICS[resolved](a, b)
