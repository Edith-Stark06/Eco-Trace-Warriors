"""Tests for the DeviceFingerprint domain model (milestone M1.5)."""

from datetime import UTC, datetime

from device_ai.fingerprint.models import (
    DeviceFingerprint,
    canonical_embedding_bytes,
    compute_fingerprint,
)


def test_fingerprint_is_deterministic_for_identical_embeddings():
    """The same embedding always hashes to the same fingerprint."""
    embedding = (0.1, 0.2, 0.3, 0.4)
    assert compute_fingerprint(embedding) == compute_fingerprint(embedding)


def test_fingerprint_differs_for_different_embeddings():
    """Distinct embeddings produce distinct fingerprints."""
    assert compute_fingerprint((0.1, 0.2)) != compute_fingerprint((0.2, 0.1))


def test_fingerprint_is_sha256_hex():
    """The fingerprint is a 64-char hexadecimal SHA-256 digest."""
    fingerprint = compute_fingerprint((0.5, 0.5))
    assert len(fingerprint) == 64
    int(fingerprint, 16)  # raises if not valid hex


def test_fingerprint_is_stable_under_tiny_float_noise():
    """Rounding makes the fingerprint robust to sub-precision float noise."""
    base = (0.123456, 0.654321)
    noisy = (0.1234561, 0.6543209)  # differ below the 6-decimal precision
    assert compute_fingerprint(base) == compute_fingerprint(noisy)


def test_canonical_encoding_rounds_to_precision():
    """Canonical bytes round each component to the configured precision."""
    assert canonical_embedding_bytes((0.1, 0.2), precision=2) == b"0.10,0.20"


def test_to_dict_from_dict_round_trip(sample_fingerprint):
    """Serialization and reconstruction preserve every field."""
    restored = DeviceFingerprint.from_dict(sample_fingerprint.to_dict())
    assert restored == sample_fingerprint


def test_to_dict_is_json_friendly(sample_fingerprint):
    """to_dict emits an ISO timestamp and list-typed sequences."""
    payload = sample_fingerprint.to_dict()
    assert payload["created_at"] == sample_fingerprint.created_at.isoformat()
    assert isinstance(payload["embedding"], list)
    assert isinstance(payload["source_hashes"], list)


def test_from_dict_defaults_optional_fields():
    """Optional provenance fields default when absent from the mapping."""
    payload = {
        "eco_id": "ET-2026-00000001",
        "fingerprint": "0" * 64,
        "embedding": [0.6, 0.8],
        "dimension": 2,
        "encoder_name": "clip",
        "encoder_version": "mock-clip-1.0.0",
        "metric": "cosine",
        "created_at": datetime(2026, 8, 1, tzinfo=UTC).isoformat(),
    }
    restored = DeviceFingerprint.from_dict(payload)
    assert restored.source_hashes == ()
    assert restored.device_type == ""
    assert restored.brand == ""
