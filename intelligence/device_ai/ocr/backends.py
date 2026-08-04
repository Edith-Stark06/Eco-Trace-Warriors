"""OCR text-recognition backends (milestone M1.6).

Defines the :class:`OCRBackend` contract and two implementations, following
the optional-dependency adapter pattern established by the M1.4 detector and
M1.5 CLIP encoder:

* :class:`EasyOCRBackend` — a real, pretrained EasyOCR reader behind an import
  guard. ``easyocr`` is a heavy optional dependency
  (``requirements-models.txt``); its import and every backend-present code path
  are ``# pragma: no cover`` because no backend is installed in the base test
  environment. Construction never raises — on any failure the backend is simply
  *not ready* and the caller falls back to the mock. The row→span mapping is
  injectable (``recognize_fn``) so it is unit-testable with a tiny fake.
* :class:`MockOCRBackend` — a deterministic stand-in that derives synthetic
  spans from the batch content hash, so the parser and service run end to end
  in the base environment without any weights. It is intentionally distinct
  from :class:`device_ai.inference.predictor.MockOCREngine` (which is bound to
  the frozen ``/predict`` serial+model envelope and left untouched).

EasyOCR is *pretrained* — a serving-only plug-in with no trainer, exactly like
the CLIP encoder. Weights/model-storage are resolved from settings relative to
``MODEL_DIR`` (never a hardcoded path).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from loguru import logger

from ..preprocessing.image_loader import LoadedImage
from ..utils.hashing import hash_bytes
from .models import TextSpan

#: A callable mapping a batch of images to raw backend rows. Each row is the
#: EasyOCR ``readtext`` shape: ``(bbox, text, confidence)``.
RecognizeFn = Callable[[list[LoadedImage]], Any]


class OCRBackend(ABC):
    """Abstract text-recognition backend.

    Subclasses turn a decoded image into raw :class:`TextSpan` detections. They
    carry the same ``name``/``version``/``is_ready`` metadata contract as the
    other model adapters so a not-ready backend can be detected and swapped for
    the mock via dependency injection.
    """

    #: Machine-readable backend name.
    name: str = "ocr"
    #: Semantic version of the underlying model artifact.
    version: str = "mock-1.0.0"

    @property
    def is_ready(self) -> bool:
        """Whether the backend is loaded and ready to serve.

        Mocks are always ready; real adapters override this to reflect the
        state of their loaded reader.
        """
        return True

    @abstractmethod
    def recognize(self, image: LoadedImage) -> list[TextSpan]:
        """Return raw text detections for a single image."""

    def recognize_batch(self, images: list[LoadedImage]) -> list[TextSpan]:
        """Return the concatenated detections across a batch of images.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            All :class:`TextSpan` detections across the batch, in image order.
        """
        spans: list[TextSpan] = []
        for image in images:
            spans.extend(self.recognize(image))
        return spans


# ---------------------------------------------------------------------------
# Deterministic mock backend
# ---------------------------------------------------------------------------

#: Synthetic label templates the mock emits. Kept realistic (labelled IDs) so
#: the parser's label-aware paths are exercised. ``{h}`` is filled from the
#: image content hash to keep outputs deterministic yet input-dependent.
_MOCK_TEMPLATES = (
    ("Dell", 0.97),
    ("Model: XPS-{h4}", 0.9),
    ("S/N: SN{h8}", 0.92),
    ("IMEI: {imei}", 0.88),
    ("MAC: {mac}", 0.9),
)


def _luhn_complete(fourteen: str) -> str:
    """Return the 15-digit IMEI for a 14-digit prefix with a Luhn check digit.

    Args:
        fourteen: Exactly fourteen decimal digits.

    Returns:
        The fifteen-digit string whose final digit makes it Luhn-valid.
    """
    total = 0
    for index, char in enumerate(reversed(fourteen)):
        value = int(char)
        # The eventual check digit sits at position 0, so the doubled positions
        # for a 14-digit prefix are the even indices here.
        if index % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    check = (10 - total % 10) % 10
    return fourteen + str(check)


class MockOCRBackend(OCRBackend):
    """Deterministic OCR backend deriving synthetic spans from image hashes.

    Same images → same spans, so the parser and service are fully exercised in
    the base environment. This is *not* the ``/predict`` mock: it emits rich,
    labelled identity text (manufacturer/model/serial/IMEI/MAC) to drive the
    M1.6 parser, whereas ``predictor.MockOCREngine`` returns empty serial+model.
    """

    name = "ocr"
    version = "mock-ocr-m16-1.0.0"

    def recognize(self, image: LoadedImage) -> list[TextSpan]:
        """Return deterministic synthetic spans derived from the image hash."""
        digest = image.sha256 or hash_bytes(image.raw)
        # Derive stable digit fills from the content hash.
        numeric = "".join(ch for ch in digest if ch.isdigit()).ljust(14, "0")
        h4 = digest[:4].upper()
        h8 = digest[:8].upper()
        imei = _luhn_complete(numeric[:14])
        mac = ":".join(digest[i : i + 2].upper() for i in range(0, 12, 2))
        spans: list[TextSpan] = []
        for template, confidence in _MOCK_TEMPLATES:
            text = template.format(h4=h4, h8=h8, imei=imei, mac=mac)
            spans.append(TextSpan(text=text, confidence=confidence))
        return spans


# ---------------------------------------------------------------------------
# Real EasyOCR adapter (optional backend, honest degradation)
# ---------------------------------------------------------------------------


def _import_easyocr() -> Any | None:
    """Return the ``easyocr`` module, or ``None`` when unavailable."""
    try:  # pragma: no cover - easyocr is not installed in the base env
        import easyocr
    except ImportError:
        return None
    return easyocr  # pragma: no cover


class EasyOCRBackend(OCRBackend):
    """EasyOCR-backed implementation of the :class:`OCRBackend` contract.

    Args:
        languages: Language codes passed to EasyOCR (e.g. ``["en"]``).
        weights_path: Model-storage directory locating EasyOCR's artifacts,
            resolved from settings relative to ``MODEL_DIR`` by the caller.
            Ignored when ``recognize_fn`` is supplied.
        use_gpu: Whether to request GPU inference from EasyOCR.
        min_confidence: Recognition confidence below which rows are dropped.
        recognize_fn: Optional injected per-batch recognize callable returning
            raw ``(bbox, text, confidence)`` rows. When given, the backend is
            not loaded and is immediately ready (used by tests).
    """

    name = "ocr"

    def __init__(
        self,
        *,
        languages: Sequence[str] = ("en",),
        weights_path: Path | None = None,
        use_gpu: bool = False,
        min_confidence: float = 0.0,
        recognize_fn: RecognizeFn | None = None,
    ) -> None:
        self._languages = list(languages)
        self._weights_path = weights_path
        self._use_gpu = use_gpu
        self._min_confidence = min_confidence
        self.version = "easyocr-1.7.2"
        if recognize_fn is not None:
            self._recognize_fn: RecognizeFn | None = recognize_fn
        else:
            self._recognize_fn = self._build_backend(weights_path)

    # -- Readiness --------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Whether a reader/recognize function is loaded and can serve."""
        return self._recognize_fn is not None

    # -- Loading ----------------------------------------------------------

    def _build_backend(self, weights_path: Path | None) -> RecognizeFn | None:
        """Build the EasyOCR recognize function, degrading honestly.

        Returns ``None`` (leaving the backend not-ready) when ``easyocr`` is not
        installed or the reader cannot be constructed — never raising, so the
        caller can fall back to the mock backend.

        Args:
            weights_path: Model-storage directory for EasyOCR artifacts.

        Returns:
            A per-batch recognize callable, or ``None`` on any failure.
        """
        easyocr = _import_easyocr()
        if easyocr is None:
            logger.warning("easyocr not installed; OCR backend not loaded.")
            return None
        return self._load_reader(easyocr, weights_path)  # pragma: no cover

    def _load_reader(  # pragma: no cover - requires optional easyocr backend
        self,
        easyocr: Any,
        weights_path: Path | None,
    ) -> RecognizeFn | None:
        """Construct the real EasyOCR reader and return a recognize closure.

        Args:
            easyocr: The imported ``easyocr`` module.
            weights_path: Model-storage directory for EasyOCR artifacts.

        Returns:
            A per-batch recognize callable, or ``None`` when construction fails.
        """
        model_dir = str(weights_path) if weights_path is not None else None
        try:
            reader = easyocr.Reader(
                self._languages,
                gpu=self._use_gpu,
                model_storage_directory=model_dir,
                download_enabled=False,
            )
        except Exception as exc:  # noqa: BLE001 - degrade to mock on any error
            logger.warning("Failed to load EasyOCR reader: {}", exc)
            return None
        logger.info("Loaded EasyOCR reader (languages={}).", self._languages)

        def recognize(images: list[LoadedImage]) -> Any:
            import numpy as np

            rows: list[Any] = []
            for image in images:
                array = np.asarray(image.image)
                rows.append(reader.readtext(array))
            return rows

        return recognize

    # -- Inference --------------------------------------------------------

    def recognize(self, image: LoadedImage) -> list[TextSpan]:
        """Return recognized text spans for a single image.

        Args:
            image: A validated, decoded image.

        Returns:
            The image's :class:`TextSpan` detections (possibly empty).

        Raises:
            RuntimeError: Never for a not-ready backend here — readiness is
                enforced by the service/DI layer, which swaps in the mock.
        """
        return self.recognize_batch([image])

    def recognize_batch(self, images: list[LoadedImage]) -> list[TextSpan]:
        """Recognize a batch and map raw rows to :class:`TextSpan` objects.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            All detections across the batch, filtered by ``min_confidence``.
        """
        if self._recognize_fn is None:  # pragma: no cover - guarded by DI layer
            return []
        raw_rows = self._recognize_fn(images)
        return self._map_rows(raw_rows)

    def _map_rows(self, raw_rows: Any) -> list[TextSpan]:
        """Map EasyOCR ``readtext`` output to :class:`TextSpan` objects.

        Accepts either a per-image list of row-lists or a flat list of rows,
        each row being ``(bbox, text, confidence)``. Rows below the configured
        minimum confidence are dropped.

        Args:
            raw_rows: The backend/fake output.

        Returns:
            The mapped, confidence-filtered spans.
        """
        spans: list[TextSpan] = []
        for group in _iter_row_groups(raw_rows):
            for row in group:
                span = _row_to_span(row)
                if span is not None and span.confidence >= self._min_confidence:
                    spans.append(span)
        return spans


def _iter_row_groups(raw_rows: Any) -> list[list[Any]]:
    """Normalise backend output into a list of row groups (one per image).

    A flat list of ``(bbox, text, conf)`` rows is wrapped in a single group so
    both the per-image and flat shapes are handled uniformly.
    """
    rows = list(raw_rows)
    if rows and _is_row(rows[0]):
        return [rows]
    return [list(group) for group in rows]


def _is_row(item: Any) -> bool:
    """Return whether ``item`` looks like a ``(bbox, text, confidence)`` row."""
    return (
        isinstance(item, list | tuple) and len(item) >= 2 and isinstance(item[1], str)
    )


def _row_to_span(row: Any) -> TextSpan | None:
    """Convert a single EasyOCR row to a :class:`TextSpan`, or ``None``.

    Args:
        row: A ``(bbox, text, confidence)`` triple (confidence optional).

    Returns:
        The mapped span, or ``None`` when the row is malformed.
    """
    if not _is_row(row):
        return None
    bbox = row[0]
    text = str(row[1])
    confidence = float(row[2]) if len(row) > 2 else 1.0
    return TextSpan(text=text, confidence=confidence, bounding_box=_bbox(bbox))


def _bbox(points: Any) -> tuple[int, int, int, int] | None:
    """Convert an EasyOCR polygon into an ``(x1, y1, x2, y2)`` box, or ``None``.

    EasyOCR returns a 4-point polygon; the axis-aligned bounds are derived from
    its extremes. Malformed geometry yields ``None`` rather than raising.
    """
    try:
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
