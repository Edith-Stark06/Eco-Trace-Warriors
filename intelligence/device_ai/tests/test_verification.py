"""Tests for the fingerprint verification engine (milestone M1.5)."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from device_ai.exceptions import FingerprintMismatchError
from device_ai.fingerprint.models import DeviceFingerprint, compute_fingerprint
from device_ai.fingerprint.similarity import SimilarityMetric
from device_ai.fingerprint.verification import (
    VerificationDecision,
    VerificationEngine,
)
from device_ai.inference.predictor import l2_normalize

_CREATED_AT = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _make_fingerprint(eco_id: str, values: Sequence[float]) -> DeviceFingerprint:
    """Build a deterministic fingerprint from a raw embedding vector."""
    embedding = l2_normalize(tuple(values))
    return DeviceFingerprint(
        eco_id=eco_id,
        fingerprint=compute_fingerprint(embedding),
        embedding=embedding,
        dimension=len(embedding),
        encoder_name="mock",
        encoder_version="1.0.0",
        metric="cosine",
        created_at=_CREATED_AT,
    )


def test_identical_fingerprints_always_match(sample_fingerprint):
    """Identical fingerprints are a guaranteed match regardless of threshold."""
    engine = VerificationEngine(threshold=0.85, metric=SimilarityMetric.COSINE)
    result = engine.verify(sample_fingerprint, sample_fingerprint)
    assert result.decision is VerificationDecision.MATCH
    assert result.is_match is True
    assert result.similarity == pytest.approx(1.0)


def test_match_decision_when_above_threshold():
    """Fingerprints score above threshold and produce a MATCH decision."""
    engine = VerificationEngine(threshold=0.80, metric=SimilarityMetric.COSINE)
    fp_a = _make_fingerprint("ET-2026-AAAA0001", (1.0, 0.0, 0.0, 0.0))
    fp_b = _make_fingerprint("ET-2026-BBBB0002", (0.99, 0.01, 0.0, 0.0))
    result = engine.verify(fp_a, fp_b)
    assert result.decision is VerificationDecision.MATCH
    assert result.is_match is True
    assert result.similarity >= 0.80


def test_no_match_decision_when_below_threshold():
    """Fingerprints score below threshold and produce a NO_MATCH decision."""
    engine = VerificationEngine(threshold=0.95, metric=SimilarityMetric.COSINE)
    # Orthogonal vectors → cosine similarity 0.5, well below 0.95.
    fp_a = _make_fingerprint("ET-2026-AAAA0001", (1.0, 0.0))
    fp_b = _make_fingerprint("ET-2026-BBBB0002", (0.0, 1.0))
    result = engine.verify(fp_a, fp_b)
    assert result.decision is VerificationDecision.NO_MATCH
    assert result.is_match is False
    assert result.similarity < 0.95


def test_threshold_boundary_is_inclusive_match():
    """Similarity exactly at threshold is a MATCH (inclusive comparison)."""
    engine = VerificationEngine(threshold=0.50, metric=SimilarityMetric.COSINE)
    # Orthogonal vectors → cosine similarity exactly 0.5.
    fp_a = _make_fingerprint("ET-2026-AAAA0001", (1.0, 0.0))
    fp_b = _make_fingerprint("ET-2026-BBBB0002", (0.0, 1.0))
    result = engine.verify(fp_a, fp_b)
    assert result.decision is VerificationDecision.MATCH
    assert result.is_match is True
    assert result.similarity == pytest.approx(0.50)


def test_metric_override_at_verify():
    """Verify accepts a metric override independent of the engine default."""
    engine = VerificationEngine(threshold=0.85, metric=SimilarityMetric.COSINE)
    fp = _make_fingerprint("ET-2026-00000001", (0.6, 0.8))
    result = engine.verify(fp, fp, metric=SimilarityMetric.EUCLIDEAN)
    assert result.metric is SimilarityMetric.EUCLIDEAN
    assert result.similarity == pytest.approx(1.0)


def test_string_metric_override_is_accepted():
    """A metric override supplied as a string is resolved to the enum member."""
    engine = VerificationEngine(threshold=0.85)
    fp = _make_fingerprint("ET-2026-00000001", (0.6, 0.8))
    result = engine.verify(fp, fp, metric="manhattan")
    assert result.metric is SimilarityMetric.MANHATTAN


def test_dimension_mismatch_raises():
    """Comparing fingerprints with different dimensions raises the typed error."""
    engine = VerificationEngine(threshold=0.85)
    fp_a = _make_fingerprint("ET-2026-AAAA0001", (0.6, 0.8))
    fp_b = _make_fingerprint("ET-2026-BBBB0002", (0.5, 0.5, 0.5))
    with pytest.raises(FingerprintMismatchError):
        engine.verify(fp_a, fp_b)


def test_threshold_must_be_in_unit_interval():
    """VerificationEngine constructor validates threshold is in [0, 1]."""
    with pytest.raises(ValueError, match="threshold"):
        VerificationEngine(threshold=-0.1)
    with pytest.raises(ValueError, match="threshold"):
        VerificationEngine(threshold=1.5)


def test_result_contains_both_eco_ids():
    """VerificationResult carries both EcoIDs for traceability."""
    engine = VerificationEngine(threshold=0.85)
    fp_a = _make_fingerprint("ET-2026-AAAA1111", (0.6, 0.8))
    fp_b = _make_fingerprint("ET-2026-BBBB2222", (0.6, 0.8))
    result = engine.verify(fp_a, fp_b)
    assert result.left_eco_id == "ET-2026-AAAA1111"
    assert result.right_eco_id == "ET-2026-BBBB2222"


def test_engine_exposes_threshold_and_metric():
    """The engine surfaces its configured threshold and default metric."""
    engine = VerificationEngine(threshold=0.9, metric="euclidean")
    assert engine.threshold == pytest.approx(0.9)
    assert engine.metric is SimilarityMetric.EUCLIDEAN
