"""OCR service: orchestration facade for the OCR engine (milestone M1.6).

:class:`OCRService` is the single collaborator the API layer depends on for
text/identity extraction. It wires the injected text backend, barcode reader
and parser into the operations the ``/ocr`` surface exposes:

* :meth:`extract` — recognize text + decode barcodes over a batch, run the
  parser once over the union, and stamp engine identity + creation time +
  source hashes.
* :meth:`parse` — run the parser over client-supplied spans/barcodes (no
  images), so the normalization layer is demonstrable without a backend.
* :meth:`identity_for` — the small :class:`OCRIdentity` projection the
  fingerprint engine optionally consumes.

Every collaborator (backend, barcode reader, parser, clock) is injected, so the
whole engine is exercised deterministically in tests with the mock backend and
mock reader — no trained weights, no filesystem, no clock.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ..preprocessing.image_loader import LoadedImage
from .backends import OCRBackend
from .barcode import BarcodeReader
from .models import BarcodeResult, OCRExtraction, OCRIdentity, TextSpan
from .parser import OCRParser


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class OCRService:
    """High-level orchestration of the OCR Intelligence Engine.

    Args:
        backend: The text-recognition backend (real EasyOCR adapter or mock).
        parser: The pure normalization/parsing layer.
        barcode_reader: Optional barcode/QR reader. When ``None``, barcode
            decoding is skipped (``barcode_enabled=False``).
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests.
    """

    def __init__(
        self,
        *,
        backend: OCRBackend,
        parser: OCRParser,
        barcode_reader: BarcodeReader | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._backend = backend
        self._parser = parser
        self._barcode_reader = barcode_reader
        self._clock = clock

    def extract(self, images: list[LoadedImage]) -> OCRExtraction:
        """Extract structured identity fields from a batch of images.

        Recognizes text across the batch, decodes barcodes/QR codes (when a
        reader is configured), runs the parser once over the union, and stamps
        provenance: the backend identity, the creation time and the sorted
        source-image content hashes.

        Args:
            images: Validated, decoded images for a single device.

        Returns:
            The stamped :class:`OCRExtraction`.
        """
        spans = self._backend.recognize_batch(images)
        barcodes: list[BarcodeResult] = []
        if self._barcode_reader is not None:
            barcodes = self._barcode_reader.decode_batch(images)
        extraction = self._parser.parse(spans, barcodes)
        return self._stamp(extraction, images)

    def parse(
        self,
        spans: list[TextSpan],
        barcodes: list[BarcodeResult] | None = None,
    ) -> OCRExtraction:
        """Run the parser over client-supplied spans/barcodes (no images).

        Powers the ``POST /ocr/parse`` endpoint, exposing the normalization
        layer without requiring an image or a backend. Provenance is stamped
        with the backend identity and creation time (no source hashes).

        Args:
            spans: Raw text spans supplied by the client.
            barcodes: Optional decoded barcodes supplied by the client.

        Returns:
            The stamped :class:`OCRExtraction`.
        """
        extraction = self._parser.parse(spans, barcodes)
        return self._stamp(extraction, [])

    def identity_for(self, images: list[LoadedImage]) -> OCRIdentity:
        """Return the identity projection extracted from ``images``.

        Convenience for the optional fingerprint-identity seam: the fingerprint
        service can be handed this :class:`OCRIdentity` without importing the
        OCR engine.

        Args:
            images: Validated, decoded images for a single device.

        Returns:
            The extracted :class:`OCRIdentity` (empty fields when not found).
        """
        return self.extract(images).identity

    def _stamp(
        self,
        extraction: OCRExtraction,
        images: list[LoadedImage],
    ) -> OCRExtraction:
        """Attach engine identity, creation time and source hashes."""
        from dataclasses import replace

        return replace(
            extraction,
            engine_name=self._backend.name,
            engine_version=self._backend.version,
            created_at=self._clock(),
            source_hashes=tuple(sorted(image.sha256 for image in images)),
        )
