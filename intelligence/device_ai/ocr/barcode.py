"""Barcode and QR decoding (milestone M1.6).

Defines the :class:`BarcodeReader` contract and two implementations, following
the same optional-dependency adapter pattern as the OCR backends:

* :class:`OpenCVBarcodeReader` — real QR/barcode decoding via OpenCV
  (``cv2.QRCodeDetector`` for QR, ``cv2.barcode.BarcodeDetector`` for 1-D
  barcodes) behind an import guard. ``opencv-python-headless`` is an optional
  dependency (``requirements-models.txt``); its import and the decode paths are
  ``# pragma: no cover`` (no backend in the base env). Construction never
  raises → not-ready on failure. The decode step is injectable for testing.
* :class:`MockBarcodeReader` — a deterministic reader that derives a stable
  QR payload from the image content hash, so the parser and service run end to
  end in the base environment.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from loguru import logger

from ..preprocessing.image_loader import LoadedImage
from ..utils.hashing import hash_bytes
from .models import BarcodeResult

#: A callable mapping a single image to raw decoded barcodes.
DecodeFn = Callable[[LoadedImage], list[BarcodeResult]]


class BarcodeReader(ABC):
    """Abstract barcode/QR decoder.

    Subclasses decode a decoded image into zero or more
    :class:`BarcodeResult` payloads, carrying the same
    ``name``/``version``/``is_ready`` metadata contract as the OCR backends.
    """

    #: Machine-readable reader name.
    name: str = "barcode"
    #: Semantic version of the underlying decoder.
    version: str = "mock-1.0.0"

    @property
    def is_ready(self) -> bool:
        """Whether the reader is ready to serve (mocks are always ready)."""
        return True

    @abstractmethod
    def decode(self, image: LoadedImage) -> list[BarcodeResult]:
        """Return decoded barcodes/QR codes for a single image."""

    def decode_batch(self, images: list[LoadedImage]) -> list[BarcodeResult]:
        """Return the concatenated decoded codes across a batch.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            All :class:`BarcodeResult` payloads across the batch, in order.
        """
        results: list[BarcodeResult] = []
        for image in images:
            results.extend(self.decode(image))
        return results


# ---------------------------------------------------------------------------
# Deterministic mock reader
# ---------------------------------------------------------------------------


class MockBarcodeReader(BarcodeReader):
    """Deterministic barcode reader deriving a stable payload from the hash.

    Emits one QR code and one 1-D barcode whose payloads are derived from the
    image content hash, so the same image always decodes to the same codes and
    the parser's barcode-mining path is exercised in the base environment.
    """

    name = "barcode"
    version = "mock-barcode-1.0.0"

    def decode(self, image: LoadedImage) -> list[BarcodeResult]:
        """Return deterministic QR + barcode payloads from the image hash."""
        digest = image.sha256 or hash_bytes(image.raw)
        qr_payload = f"SN{digest[:8].upper()}"
        code_digits = "".join(ch for ch in digest if ch.isdigit()).ljust(12, "0")
        return [
            BarcodeResult(
                kind="qr",
                payload=qr_payload,
                symbology="QRCODE",
                confidence=0.99,
            ),
            BarcodeResult(
                kind="barcode",
                payload=code_digits[:12],
                symbology="EAN13",
                confidence=0.95,
            ),
        ]


# ---------------------------------------------------------------------------
# Real OpenCV adapter (optional backend, honest degradation)
# ---------------------------------------------------------------------------


def _import_cv2() -> Any | None:
    """Return the ``cv2`` module, or ``None`` when unavailable."""
    try:  # pragma: no cover - opencv is not installed in the base env
        import cv2
    except ImportError:
        return None
    return cv2  # pragma: no cover


class OpenCVBarcodeReader(BarcodeReader):
    """OpenCV-backed QR and 1-D barcode reader.

    Args:
        decode_fn: Optional injected per-image decode callable returning
            :class:`BarcodeResult` objects. When given, the OpenCV backend is
            not loaded and the reader is immediately ready (used by tests).
    """

    name = "barcode"

    def __init__(self, *, decode_fn: DecodeFn | None = None) -> None:
        self.version = "opencv-barcode-1.0.0"
        if decode_fn is not None:
            self._decode_fn: DecodeFn | None = decode_fn
        else:
            self._decode_fn = self._build_backend()

    @property
    def is_ready(self) -> bool:
        """Whether a decode function is loaded and can serve."""
        return self._decode_fn is not None

    def _build_backend(self) -> DecodeFn | None:
        """Build the OpenCV decode function, degrading honestly.

        Returns ``None`` (leaving the reader not-ready) when ``cv2`` is not
        installed — never raising, so the caller can fall back to the mock.
        """
        cv2 = _import_cv2()
        if cv2 is None:
            logger.warning("opencv not installed; barcode reader not loaded.")
            return None
        return self._build_decoder(cv2)  # pragma: no cover

    def _build_decoder(  # pragma: no cover - requires optional cv2 backend
        self, cv2: Any
    ) -> DecodeFn | None:
        """Return an OpenCV decode closure for QR and 1-D barcodes.

        Args:
            cv2: The imported ``cv2`` module.

        Returns:
            A per-image decode callable, or ``None`` when detectors are absent.
        """
        try:
            qr_detector = cv2.QRCodeDetector()
            barcode_detector = (
                cv2.barcode.BarcodeDetector() if hasattr(cv2, "barcode") else None
            )
        except Exception as exc:  # noqa: BLE001 - degrade to mock on any error
            logger.warning("Failed to construct OpenCV detectors: {}", exc)
            return None

        def decode(image: LoadedImage) -> list[BarcodeResult]:
            import numpy as np

            array = np.asarray(image.image)
            results: list[BarcodeResult] = []
            qr_value, _points, _straight = qr_detector.detectAndDecode(array)
            if qr_value:
                results.append(
                    BarcodeResult(
                        kind="qr",
                        payload=str(qr_value),
                        symbology="QRCODE",
                        confidence=1.0,
                    )
                )
            if barcode_detector is not None:
                ok, decoded, types, _points = barcode_detector.detectAndDecode(array)
                if ok and decoded:
                    for value, kind in zip(decoded, types, strict=False):
                        if value:
                            results.append(
                                BarcodeResult(
                                    kind="barcode",
                                    payload=str(value),
                                    symbology=str(kind),
                                    confidence=1.0,
                                )
                            )
            return results

        return decode

    def decode(self, image: LoadedImage) -> list[BarcodeResult]:
        """Return decoded barcodes/QR codes for a single image.

        Args:
            image: A validated, decoded image.

        Returns:
            The decoded codes, or an empty list when the backend is not ready.
        """
        if self._decode_fn is None:  # pragma: no cover - guarded by DI layer
            return []
        return self._decode_fn(image)
