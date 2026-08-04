"""Pluggable model interfaces and mock implementations.

This module defines the *contracts* every device-intelligence model must
satisfy and ships deterministic **mock** implementations for milestone
M1.1. Real models (YOLO detector, OpenCLIP encoder, condition classifier,
EasyOCR) are added later by implementing the same abstract base classes and
swapping them in via dependency injection — no pipeline or API change
required.

Design goals (``CLAUDE.md`` → AI Rules):

* No business logic inside models — they answer "what is this", nothing more.
* Preprocessing is separate (see :mod:`preprocessing`).
* Model artifact locations come from configuration, never hardcoded.
* Each component is independently testable.

The mocks are **deterministic**: outputs are derived from a stable content
hash of the input images, so the same images always yield the same
prediction. This makes tests reproducible and demos predictable without any
trained weights.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..preprocessing.image_loader import LoadedImage
from ..utils.hashing import short_hash

# ---------------------------------------------------------------------------
# Result value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Detection:
    """A single detected object within an image.

    Attributes:
        label: Detected device/object class label.
        confidence: Model confidence in the range [0.0, 1.0].
        bounding_box: ``(x1, y1, x2, y2)`` pixel coordinates.
    """

    label: str
    confidence: float
    bounding_box: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Aggregated detector output for a batch of images.

    Attributes:
        device_type: The dominant device type across the batch.
        brand: Predicted manufacturer/brand.
        confidence: Confidence in the dominant device type.
        detections: All raw detections (may be empty for mocks).
    """

    device_type: str
    brand: str
    confidence: float
    detections: list[Detection] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ConditionResult:
    """Condition assessment output.

    Attributes:
        label: Human-readable condition class (e.g. ``"Good"``).
        score: Confidence in the assessed condition, range [0.0, 1.0].
    """

    label: str
    score: float


@dataclass(frozen=True, slots=True)
class OCRResult:
    """Text extraction output.

    Attributes:
        serial_number: Extracted serial number, empty when none found.
        model: Extracted model identifier, empty when none found.
    """

    serial_number: str = ""
    model: str = ""


@dataclass(frozen=True, slots=True)
class MaterialResult:
    """Estimated recoverable material composition.

    Attributes:
        composition: Mapping of material name to fractional weight in the
            range [0.0, 1.0]. Fractions sum to approximately 1.0.
    """

    composition: dict[str, float]


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """A dense visual embedding produced by an :class:`EmbeddingEncoder`.

    Unlike :class:`EmbeddingResult` (an opaque reference surfaced over the
    ``/predict`` contract), this value object carries the *actual* numeric
    vector so downstream components — notably the M1.5 fingerprinting engine —
    can compute similarity and derive hash-backed identifiers.

    Attributes:
        values: The embedding components. When ``normalized`` is True this is a
            unit-length (L2) vector.
        dimension: Length of ``values`` (kept explicit for validation/serdes).
        normalized: Whether ``values`` has been L2-normalized.
    """

    values: tuple[float, ...]
    dimension: int
    normalized: bool = True


def l2_normalize(values: tuple[float, ...]) -> tuple[float, ...]:
    """Return the L2 (unit-length) normalization of ``values``.

    A zero vector is returned unchanged (its norm is zero and cannot be scaled
    to unit length).

    Args:
        values: The raw embedding components.

    Returns:
        The unit-length vector, or the input unchanged when its norm is zero.
    """
    norm = math.sqrt(sum(component * component for component in values))
    if norm == 0.0:
        return values
    return tuple(component / norm for component in values)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Visual embedding reference.

    The raw vector is not returned over the ``/predict`` API; instead an
    identifier is surfaced so the backend can reference it if embeddings are
    later persisted to a vector store. The M1.5 fingerprinting engine consumes
    the full vector via :meth:`EmbeddingEncoder.embed` instead.

    Attributes:
        embedding_id: Stable identifier for the computed embedding.
        dimension: Dimensionality of the underlying vector.
    """

    embedding_id: str
    dimension: int


# ---------------------------------------------------------------------------
# Abstract interfaces (contracts for real + mock implementations)
# ---------------------------------------------------------------------------


class BaseModel(ABC):  # noqa: B024 - intentional ABC base for shared metadata
    """Common metadata contract shared by every model component.

    This base is abstract by design even though it declares no abstract
    methods itself: it exists so every component subclass inherits the
    ``name``/``version``/``is_ready`` contract, while each concrete
    capability (detect/assess/extract/...) is declared abstract on the
    respective interface below.
    """

    #: Machine-readable component name (e.g. ``"detector"``).
    name: str = "base"
    #: Semantic version of the underlying model artifact.
    version: str = "mock-1.0.0"

    @property
    def is_ready(self) -> bool:
        """Whether the component is loaded and ready to serve.

        Mocks are always ready; real adapters override this to reflect the
        state of their loaded artifact.
        """
        return True


class Detector(BaseModel):
    """Detects the device type and brand from images."""

    name = "detector"

    @abstractmethod
    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        """Return the device type/brand for a batch of images."""


class ConditionAssessor(BaseModel):
    """Assesses the physical condition of the device."""

    name = "condition"

    @abstractmethod
    def assess(self, images: list[LoadedImage]) -> ConditionResult:
        """Return a condition label and confidence for the batch."""


class OCREngine(BaseModel):
    """Extracts printed text (serial number, model) from images."""

    name = "ocr"

    @abstractmethod
    def extract(self, images: list[LoadedImage]) -> OCRResult:
        """Return extracted serial number and model identifiers."""


class MaterialEstimator(BaseModel):
    """Estimates recoverable material composition of the device."""

    name = "material"

    @abstractmethod
    def estimate(self, images: list[LoadedImage], device_type: str) -> MaterialResult:
        """Return a normalized material composition for the device."""


class EmbeddingEncoder(BaseModel):
    """Produces a visual embedding reference for similarity/search.

    Milestone M1.5 extends the encoder contract: the new :meth:`embed` returns
    the actual normalized vector (used by the fingerprinting engine), while
    the existing :meth:`encode` returns only an opaque identifier (used by
    ``/predict`` and unchanged for backward compatibility). A default
    implementation of ``encode`` derives its identifier from ``embed`` so a
    single ``embed()`` override powers both.
    """

    name = "clip"

    @abstractmethod
    def embed(self, images: list[LoadedImage]) -> EmbeddingVector:
        """Return the L2-normalized visual embedding for a batch.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            An :class:`EmbeddingVector` with ``normalized=True``.
        """

    def encode(self, images: list[LoadedImage]) -> EmbeddingResult:
        """Return an embedding identifier for the batch.

        The default implementation derives a stable identifier from the
        normalized embedding returned by :meth:`embed` so subclasses need
        only override ``embed()``. Subclasses may override this method to
        preserve their existing deterministic ``embedding_id`` behaviour
        (e.g. :class:`MockEmbeddingEncoder` does so to avoid breaking tests).

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            An :class:`EmbeddingResult` with a stable identifier.
        """
        vector = self.embed(images)
        # Derive a stable 12-char identifier from the hash of the canonical
        # serialization of the (rounded, normalized) embedding vector.
        canonical = ",".join(f"{v:.6f}" for v in vector.values).encode("utf-8")
        embedding_id = short_hash(canonical, length=12)
        return EmbeddingResult(embedding_id=embedding_id, dimension=vector.dimension)


# ---------------------------------------------------------------------------
# Deterministic helpers for the mock implementations
# ---------------------------------------------------------------------------


def _batch_seed(images: list[LoadedImage]) -> int:
    """Derive a stable integer seed from a batch of images.

    The seed is computed from the concatenated per-image content hashes so
    identical inputs always yield identical mock predictions.

    Args:
        images: The validated images for the request.

    Returns:
        A non-negative integer seed.
    """
    joined = "".join(sorted(img.sha256 for img in images)).encode("utf-8")
    digest = hashlib.sha256(joined).hexdigest()
    return int(digest[:8], 16)


def _pick(options: list[str], seed: int) -> str:
    """Deterministically pick one option from a list using ``seed``."""
    return options[seed % len(options)]


def _confidence(seed: int, *, low: float = 0.80, high: float = 0.99) -> float:
    """Map a seed to a plausible confidence value in ``[low, high]``."""
    span = high - low
    return round(low + (seed % 1000) / 1000.0 * span, 4)


# ---------------------------------------------------------------------------
# Mock implementations (M1.1 — no trained weights, deterministic outputs)
# ---------------------------------------------------------------------------

# Illustrative vocabularies used only by the mocks. Real adapters obtain
# their label spaces from the trained model artifacts.
_DEVICE_TYPES = ["Laptop", "Smartphone", "Tablet", "Monitor", "Desktop"]
_BRANDS = ["Dell", "HP", "Apple", "Samsung", "Lenovo", "Asus"]
_CONDITIONS = ["Excellent", "Good", "Fair", "Poor"]

# Per-device-type nominal material composition (fractions sum to ~1.0).
_MATERIAL_PROFILES: dict[str, dict[str, float]] = {
    "Laptop": {
        "plastic": 0.42,
        "aluminum": 0.26,
        "copper": 0.15,
        "pcb": 0.10,
        "battery": 0.07,
    },
    "Smartphone": {
        "plastic": 0.30,
        "aluminum": 0.22,
        "copper": 0.14,
        "pcb": 0.18,
        "battery": 0.16,
    },
    "Tablet": {
        "plastic": 0.35,
        "aluminum": 0.28,
        "copper": 0.12,
        "pcb": 0.13,
        "battery": 0.12,
    },
    "Monitor": {
        "plastic": 0.50,
        "aluminum": 0.18,
        "copper": 0.17,
        "pcb": 0.12,
        "battery": 0.03,
    },
    "Desktop": {
        "plastic": 0.30,
        "aluminum": 0.20,
        "copper": 0.25,
        "pcb": 0.20,
        "battery": 0.05,
    },
}

# Fallback profile for any device type without an explicit entry.
_DEFAULT_MATERIAL_PROFILE = {
    "plastic": 0.40,
    "aluminum": 0.25,
    "copper": 0.15,
    "pcb": 0.12,
    "battery": 0.08,
}


class MockDetector(Detector):
    """Deterministic stand-in for the future YOLO detector."""

    version = "mock-detector-1.0.0"

    def __init__(self, model_dir: Path | None = None) -> None:
        # ``model_dir`` is accepted for interface parity with real adapters
        # (which resolve artifact paths from configuration); the mock does
        # not load any weights.
        self._model_dir = model_dir

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        """Return a deterministic device type/brand for the batch."""
        seed = _batch_seed(images)
        return DetectionResult(
            device_type=_pick(_DEVICE_TYPES, seed),
            brand=_pick(_BRANDS, seed >> 3),
            confidence=_confidence(seed),
            detections=[],
        )


class MockConditionAssessor(ConditionAssessor):
    """Deterministic stand-in for the future condition classifier."""

    version = "mock-condition-1.0.0"

    def assess(self, images: list[LoadedImage]) -> ConditionResult:
        """Return a deterministic condition label and score."""
        seed = _batch_seed(images) >> 5
        return ConditionResult(
            label=_pick(_CONDITIONS, seed),
            score=_confidence(seed, low=0.70, high=0.98),
        )


class MockOCREngine(OCREngine):
    """Deterministic stand-in for the future OCR engine.

    Returns empty strings by default, mirroring the reference response where
    no serial/model text has been extracted yet.
    """

    version = "mock-ocr-1.0.0"

    def extract(self, images: list[LoadedImage]) -> OCRResult:
        """Return empty OCR fields (no text extracted in mock mode)."""
        return OCRResult(serial_number="", model="")


class MockMaterialEstimator(MaterialEstimator):
    """Deterministic stand-in for the future material estimation engine."""

    version = "mock-material-1.0.0"

    def estimate(self, images: list[LoadedImage], device_type: str) -> MaterialResult:
        """Return the nominal material profile for the device type."""
        profile = _MATERIAL_PROFILES.get(device_type, _DEFAULT_MATERIAL_PROFILE)
        # Return a copy so callers cannot mutate the shared profile table.
        return MaterialResult(composition=dict(profile))


class MockEmbeddingEncoder(EmbeddingEncoder):
    """Deterministic stand-in for the future OpenCLIP encoder.

    Produces a stable pseudo-embedding derived purely from the batch content
    hash — no ``random`` module, no trained weights — so the same images
    always yield the same normalized vector. This lets the whole M1.5
    fingerprinting engine be exercised end to end in the base environment
    without ``open-clip-torch``/``torch`` installed.
    """

    version = "mock-clip-1.0.0"
    #: Dimensionality the real CLIP model is expected to produce.
    dimension = 512

    def embed(self, images: list[LoadedImage]) -> EmbeddingVector:
        """Return a deterministic, L2-normalized pseudo-embedding for a batch.

        The vector is expanded from the batch's stable SHA-256 seed via a
        simple linear-congruential recurrence (pure arithmetic), then
        L2-normalized. Identical inputs therefore always produce an identical
        unit vector.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            A unit-length :class:`EmbeddingVector` of :attr:`dimension` values.
        """
        seed = _batch_seed(images)
        # Deterministic LCG (Numerical Recipes constants) over a 32-bit space;
        # map each drawn integer into [-1, 1) before normalizing.
        state = seed
        raw: list[float] = []
        for _ in range(self.dimension):
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            raw.append(state / 0x7FFFFFFF - 1.0)
        return EmbeddingVector(
            values=l2_normalize(tuple(raw)),
            dimension=self.dimension,
            normalized=True,
        )

    def encode(self, images: list[LoadedImage]) -> EmbeddingResult:
        """Return a stable embedding identifier derived from the batch.

        Overrides the ABC default to preserve the milestone-M1.1 identifier
        shape (``mock_embedding_XXXXXXXX``) that existing ``/predict`` tests
        assert, keeping the prediction contract byte-compatible.
        """
        seed = _batch_seed(images)
        return EmbeddingResult(
            embedding_id=f"mock_embedding_{seed:08x}",
            dimension=self.dimension,
        )
