"""Tests for the configurable similarity metrics (milestone M1.5)."""

import math

import pytest

from device_ai.exceptions import (
    FingerprintMismatchError,
    UnknownSimilarityMetricError,
)
from device_ai.fingerprint.similarity import (
    SimilarityMetric,
    compute_similarity,
    cosine_similarity,
    euclidean_similarity,
    manhattan_similarity,
)


def test_identical_vectors_score_one_for_every_metric():
    """Identical vectors are maximally similar under every metric."""
    vector = (0.1, 0.2, 0.3, 0.4)
    for metric in SimilarityMetric:
        score = compute_similarity(vector, vector, metric)
        assert score.similarity == pytest.approx(1.0)
        assert score.distance == pytest.approx(0.0)
        assert score.metric is metric


def test_cosine_of_orthogonal_vectors_is_half():
    """Orthogonal vectors map to a cosine similarity of 0.5 ((1 + 0) / 2)."""
    score = cosine_similarity((1.0, 0.0), (0.0, 1.0))
    assert score.similarity == pytest.approx(0.5)
    assert score.distance == pytest.approx(1.0)


def test_cosine_of_opposite_vectors_is_zero():
    """Anti-parallel vectors map to a cosine similarity of 0.0 ((1 + -1) / 2)."""
    score = cosine_similarity((1.0, 0.0), (-1.0, 0.0))
    assert score.similarity == pytest.approx(0.0)
    assert score.distance == pytest.approx(2.0)


def test_cosine_with_zero_vector_is_zero_similarity():
    """A zero vector has an undefined direction and scores 0.0 similarity."""
    score = cosine_similarity((0.0, 0.0), (1.0, 1.0))
    assert score.similarity == 0.0
    assert score.distance == 1.0


def test_euclidean_similarity_matches_formula():
    """Euclidean similarity is 1 / (1 + L2 distance)."""
    a, b = (0.0, 0.0), (3.0, 4.0)
    score = euclidean_similarity(a, b)
    assert score.distance == pytest.approx(5.0)
    assert score.similarity == pytest.approx(1.0 / 6.0)


def test_manhattan_similarity_matches_formula():
    """Manhattan similarity is 1 / (1 + L1 distance)."""
    a, b = (0.0, 0.0), (3.0, 4.0)
    score = manhattan_similarity(a, b)
    assert score.distance == pytest.approx(7.0)
    assert score.similarity == pytest.approx(1.0 / 8.0)


def test_metrics_are_symmetric():
    """Swapping the operands does not change the score for any metric."""
    a = (0.2, 0.9, -0.3, 0.1)
    b = (0.7, -0.1, 0.4, 0.5)
    for metric in SimilarityMetric:
        forward = compute_similarity(a, b, metric)
        backward = compute_similarity(b, a, metric)
        assert forward.similarity == pytest.approx(backward.similarity)
        assert forward.distance == pytest.approx(backward.distance)


def test_similarity_decreases_as_distance_grows():
    """Nearer vectors score higher than farther ones (monotonicity)."""
    reference = (0.0, 0.0)
    near = compute_similarity(reference, (0.1, 0.0), SimilarityMetric.EUCLIDEAN)
    far = compute_similarity(reference, (5.0, 0.0), SimilarityMetric.EUCLIDEAN)
    assert near.similarity > far.similarity


def test_from_name_is_case_insensitive_and_accepts_members():
    """Metric resolution accepts names (any case) and existing members."""
    assert SimilarityMetric.from_name("COSINE") is SimilarityMetric.COSINE
    assert SimilarityMetric.from_name("euclidean") is SimilarityMetric.EUCLIDEAN
    assert (
        SimilarityMetric.from_name(SimilarityMetric.MANHATTAN)
        is SimilarityMetric.MANHATTAN
    )


def test_unknown_metric_raises():
    """An unsupported metric name raises the typed error."""
    with pytest.raises(UnknownSimilarityMetricError):
        compute_similarity((1.0,), (1.0,), "jaccard")


def test_dimension_mismatch_raises():
    """Comparing different-length vectors raises the typed error."""
    with pytest.raises(FingerprintMismatchError):
        compute_similarity((1.0, 2.0), (1.0, 2.0, 3.0))


def test_normalized_similarity_stays_in_unit_interval():
    """Every metric keeps similarity within [0, 1] for arbitrary inputs."""
    a = (5.0, -2.0, 3.5)
    b = (-1.0, 8.0, 0.25)
    for metric in SimilarityMetric:
        score = compute_similarity(a, b, metric)
        assert 0.0 <= score.similarity <= 1.0
        assert math.isfinite(score.distance)
