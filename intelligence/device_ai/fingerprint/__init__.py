"""Device fingerprinting engine (milestone M1.5).

Turns a device's photos into a compact, comparable **fingerprint** and
verifies whether two fingerprints represent the same device. It builds
directly on the existing inference contracts (the pluggable
:class:`~device_ai.inference.predictor.EmbeddingEncoder`) and reuses the
:class:`~device_ai.inference.ecoid.EcoIDGenerator` and content-hashing
utilities — no infrastructure is duplicated.

Components (each independently testable, free of HTTP concerns):

* **Embedding** — a normalized visual embedding from the pluggable encoder
  (real OpenCLIP adapter, or the deterministic mock in the base environment).
* **Fingerprint** — :class:`~device_ai.fingerprint.models.DeviceFingerprint`,
  a hash-backed identifier derived from the normalized embedding.
* **Similarity** — configurable ``cosine``/``euclidean``/``manhattan`` metrics.
* **Verification** — :class:`~device_ai.fingerprint.verification.VerificationEngine`
  returning a similarity score plus a match/no-match decision.
* **Persistence** — the storage-agnostic
  :class:`~device_ai.fingerprint.repository.FingerprintRepository` protocol
  with in-memory and JSON-file implementations.

The :class:`~device_ai.fingerprint.service.FingerprintService` facade composes
them for the ``/fingerprint`` API surface.
"""

from __future__ import annotations

from .models import DeviceFingerprint
from .repository import (
    FingerprintRepository,
    InMemoryFingerprintRepository,
    JsonFileFingerprintRepository,
)
from .service import FingerprintService
from .similarity import SimilarityMetric, SimilarityScore, compute_similarity
from .verification import (
    VerificationDecision,
    VerificationEngine,
    VerificationResult,
)

__all__ = [
    "DeviceFingerprint",
    "FingerprintRepository",
    "FingerprintService",
    "InMemoryFingerprintRepository",
    "JsonFileFingerprintRepository",
    "SimilarityMetric",
    "SimilarityScore",
    "VerificationDecision",
    "VerificationEngine",
    "VerificationResult",
    "compute_similarity",
]
