"""Tests for the FingerprintService orchestration facade (milestone M1.5)."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from device_ai.exceptions import FingerprintNotFoundError
from device_ai.fingerprint.repository import InMemoryFingerprintRepository
from device_ai.fingerprint.service import FingerprintService
from device_ai.fingerprint.verification import (
    VerificationDecision,
    VerificationEngine,
)
from device_ai.inference.ecoid import EcoIDGenerator
from device_ai.inference.predictor import MockEmbeddingEncoder
from device_ai.preprocessing.image_loader import LoadedImage, load_image

from .conftest import make_image_bytes

_FIXED_CLOCK: Callable[[], datetime] = lambda: datetime(  # noqa: E731
    2026, 8, 1, 12, 0, 0, tzinfo=UTC
)


def _load(color: tuple[int, int, int]) -> LoadedImage:
    """Return a decoded LoadedImage of a solid colour for service tests."""
    return load_image(
        make_image_bytes(color=color),
        filename="device.png",
        content_type="image/png",
    )


def _make_service(
    *,
    repository: InMemoryFingerprintRepository | None = None,
    threshold: float = 0.85,
    metric: str = "cosine",
) -> FingerprintService:
    """Build a service wired to the mock encoder and an in-memory store."""
    return FingerprintService(
        encoder=MockEmbeddingEncoder(),
        repository=repository or InMemoryFingerprintRepository(),
        ecoid_generator=EcoIDGenerator(year=2026),
        verifier=VerificationEngine(threshold=threshold, metric=metric),
        clock=_FIXED_CLOCK,
    )


def test_generate_persists_and_is_retrievable():
    """generate() saves a fingerprint that get() returns unchanged."""
    repository = InMemoryFingerprintRepository()
    service = _make_service(repository=repository)
    fingerprint = service.generate([_load((10, 20, 30))])
    assert repository.exists(fingerprint.eco_id)
    assert service.get(fingerprint.eco_id) == fingerprint


def test_generated_fingerprint_has_expected_shape():
    """The generated fingerprint carries encoder metadata and a hex hash."""
    service = _make_service()
    fingerprint = service.generate(
        [_load((10, 20, 30))], device_type="Laptop", brand="Dell"
    )
    assert fingerprint.eco_id.startswith("ET-2026-")
    assert len(fingerprint.fingerprint) == 64
    assert fingerprint.dimension == len(fingerprint.embedding) == 512
    assert fingerprint.encoder_name == "clip"
    assert fingerprint.encoder_version == "mock-clip-1.0.0"
    assert fingerprint.metric == "cosine"
    assert fingerprint.created_at == _FIXED_CLOCK()
    assert fingerprint.device_type == "Laptop"
    assert fingerprint.brand == "Dell"


def test_generated_embedding_is_unit_length():
    """The stored embedding is L2-normalized (unit length)."""
    service = _make_service()
    fingerprint = service.generate([_load((10, 20, 30))])
    norm = sum(component * component for component in fingerprint.embedding) ** 0.5
    assert norm == pytest.approx(1.0)


def test_generate_records_source_hashes():
    """Provenance hashes come from the source images (sorted, deduplicated)."""
    image = _load((10, 20, 30))
    service = _make_service()
    fingerprint = service.generate([image])
    assert fingerprint.source_hashes == (image.sha256,)


def test_generate_without_persist_does_not_store():
    """generate(persist=False) returns a fingerprint but stores nothing."""
    repository = InMemoryFingerprintRepository()
    service = _make_service(repository=repository)
    fingerprint = service.generate([_load((10, 20, 30))], persist=False)
    assert repository.list_ids() == []
    assert repository.exists(fingerprint.eco_id) is False


def test_generate_is_deterministic_for_identical_images():
    """Identical images produce an identical embedding and fingerprint hash."""
    service = _make_service()
    first = service.generate([_load((10, 20, 30))], persist=False)
    second = service.generate([_load((10, 20, 30))], persist=False)
    assert first.fingerprint == second.fingerprint
    assert first.embedding == second.embedding


def test_get_unknown_eco_id_raises():
    """get() raises the typed not-found error for an unknown EcoID."""
    service = _make_service()
    with pytest.raises(FingerprintNotFoundError):
        service.get("ET-2026-DEADBEEF")


def test_compare_identical_stored_fingerprints_matches():
    """Comparing a stored fingerprint with itself yields a MATCH."""
    service = _make_service()
    fingerprint = service.generate([_load((10, 20, 30))])
    result = service.compare(fingerprint.eco_id, fingerprint.eco_id)
    assert result.decision is VerificationDecision.MATCH
    assert result.similarity == pytest.approx(1.0)


def test_compare_distinct_devices_below_threshold():
    """Two visually distinct devices score below a high threshold."""
    service = _make_service(threshold=0.999)
    left = service.generate([_load((10, 20, 30))])
    right = service.generate([_load((200, 100, 50))])
    result = service.compare(left.eco_id, right.eco_id)
    assert result.decision is VerificationDecision.NO_MATCH


def test_compare_unknown_eco_id_raises():
    """compare() propagates not-found when either EcoID is unknown."""
    service = _make_service()
    stored = service.generate([_load((10, 20, 30))])
    with pytest.raises(FingerprintNotFoundError):
        service.compare(stored.eco_id, "ET-2026-DEADBEEF")


def test_compare_images_does_not_persist():
    """compare_images() verifies ad-hoc batches without storing anything."""
    repository = InMemoryFingerprintRepository()
    service = _make_service(repository=repository)
    result = service.compare_images([_load((10, 20, 30))], [_load((10, 20, 30))])
    assert result.decision is VerificationDecision.MATCH
    assert repository.list_ids() == []


def test_compare_accepts_metric_override():
    """compare() honours a per-call metric override."""
    service = _make_service()
    fingerprint = service.generate([_load((10, 20, 30))])
    result = service.compare(fingerprint.eco_id, fingerprint.eco_id, metric="euclidean")
    assert result.metric.value == "euclidean"
