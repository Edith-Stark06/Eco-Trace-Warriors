"""Fingerprint service: orchestration facade for the engine (milestone M1.5).

:class:`FingerprintService` is the single collaborator the API layer depends
on for fingerprinting. It wires together the injected encoder, EcoID
generator, verification engine and persistence repository into the three
operations the ``/fingerprint`` surface exposes:

* :meth:`generate` — embed images, derive a hash-backed fingerprint, persist.
* :meth:`get`      — fetch a stored fingerprint (or raise not-found).
* :meth:`compare`  — verify two stored fingerprints by EcoID.

Every collaborator (encoder, repository, EcoID generator, verifier, clock) is
injected, so the whole engine is exercised deterministically in tests with a
mock encoder and an in-memory repository — no trained weights, no filesystem.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..exceptions import FingerprintNotFoundError
from ..inference.ecoid import EcoIDGenerator
from ..inference.predictor import EmbeddingEncoder, l2_normalize
from ..preprocessing.image_loader import LoadedImage
from .models import DeviceFingerprint, compute_fingerprint
from .repository import FingerprintRepository
from .similarity import SimilarityMetric
from .verification import VerificationEngine, VerificationResult

if TYPE_CHECKING:  # Type-only import keeps the fingerprint core free of a hard
    # runtime dependency on the OCR engine (identity is passed in, not imported).
    from ..ocr.models import OCRIdentity


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class FingerprintService:
    """High-level orchestration of the device fingerprinting engine.

    Args:
        encoder: The embedding encoder (real OpenCLIP adapter or the mock).
        repository: Storage-agnostic fingerprint persistence.
        ecoid_generator: Generator for public EcoIDs.
        verifier: The verification engine (threshold + default metric).
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests.
    """

    def __init__(
        self,
        *,
        encoder: EmbeddingEncoder,
        repository: FingerprintRepository,
        ecoid_generator: EcoIDGenerator,
        verifier: VerificationEngine,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._encoder = encoder
        self._repository = repository
        self._ecoid = ecoid_generator
        self._verifier = verifier
        self._clock = clock

    def generate(
        self,
        images: list[LoadedImage],
        *,
        device_type: str = "",
        brand: str = "",
        identity: OCRIdentity | None = None,
        persist: bool = True,
    ) -> DeviceFingerprint:
        """Generate (and by default persist) a fingerprint for a batch.

        The encoder's embedding is L2-normalized defensively (real adapters
        already normalize; the guard keeps the fingerprint hash well-defined
        regardless), then hashed to a stable identifier.

        Args:
            images: Validated, decoded images for a single device.
            device_type: Optional device type (e.g. from the detection
                pipeline) recorded for provenance.
            brand: Optional brand recorded for provenance.
            identity: Optional OCR-derived identity (milestone M1.6). When
                supplied, its non-empty fields are attached to the record; the
                default ``None`` leaves the fingerprint byte-identical to M1.5.
            persist: When True (default) the fingerprint is saved to the
                repository before being returned.

        Returns:
            The generated :class:`DeviceFingerprint`.
        """
        vector = self._encoder.embed(images)
        embedding = vector.values if vector.normalized else l2_normalize(vector.values)
        identity_fields = identity.non_empty() if identity is not None else {}
        fingerprint = DeviceFingerprint(
            eco_id=self._ecoid.generate(),
            fingerprint=compute_fingerprint(embedding),
            embedding=embedding,
            dimension=vector.dimension,
            encoder_name=self._encoder.name,
            encoder_version=self._encoder.version,
            metric=self._verifier.metric.value,
            created_at=self._clock(),
            source_hashes=tuple(sorted(img.sha256 for img in images)),
            device_type=device_type,
            brand=brand,
            identity=identity_fields,
        )
        if persist:
            self._repository.save(fingerprint)
        return fingerprint

    def get(self, eco_id: str) -> DeviceFingerprint:
        """Return the stored fingerprint for ``eco_id``.

        Args:
            eco_id: The EcoID to look up.

        Returns:
            The stored :class:`DeviceFingerprint`.

        Raises:
            FingerprintNotFoundError: If no fingerprint is stored for ``eco_id``.
        """
        fingerprint = self._repository.get(eco_id)
        if fingerprint is None:
            raise FingerprintNotFoundError(
                "No fingerprint found for the given EcoID.",
                details={"eco_id": eco_id},
            )
        return fingerprint

    def compare(
        self,
        left_eco_id: str,
        right_eco_id: str,
        *,
        metric: str | SimilarityMetric | None = None,
    ) -> VerificationResult:
        """Verify two stored fingerprints against each other.

        Args:
            left_eco_id: EcoID of the first stored fingerprint.
            right_eco_id: EcoID of the second stored fingerprint.
            metric: Optional metric override; defaults to the engine's metric.

        Returns:
            The :class:`VerificationResult` (similarity + match decision).

        Raises:
            FingerprintNotFoundError: If either EcoID is unknown.
            FingerprintMismatchError: If the embeddings differ in dimension.
        """
        left = self.get(left_eco_id)
        right = self.get(right_eco_id)
        return self._verifier.verify(left, right, metric=metric)

    def compare_images(
        self,
        left_images: list[LoadedImage],
        right_images: list[LoadedImage],
        *,
        metric: str | SimilarityMetric | None = None,
    ) -> VerificationResult:
        """Verify two ad-hoc image batches without persisting them.

        Convenience for one-shot comparisons that do not need durable
        fingerprints: both batches are embedded, wrapped as (unsaved)
        fingerprints and verified.

        Args:
            left_images: First device's images.
            right_images: Second device's images.
            metric: Optional metric override; defaults to the engine's metric.

        Returns:
            The :class:`VerificationResult` (similarity + match decision).
        """
        left = self.generate(left_images, persist=False)
        right = self.generate(right_images, persist=False)
        return self._verifier.verify(left, right, metric=metric)
