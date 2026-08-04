"""OCR Intelligence Engine (milestone M1.6).

Reads the **printed identity** off a device — manufacturer, model, serial
number, IMEI, MAC address — plus the QR/barcodes that carry them, and converts
noisy recognition output into structured, confidence-scored identity fields.

It builds on the existing infrastructure (preprocessing, hashing, settings/DI,
the exception hierarchy) and is purely **additive**: the frozen ``/predict``
contract and its :class:`~device_ai.inference.predictor.OCREngine` are
untouched. This engine is exposed via the separate ``/ocr`` API surface and an
optional, backward-compatible identity seam into the M1.5 fingerprint engine.

Components (each independently testable, free of HTTP concerns):

* **Backends** — a pluggable :class:`~device_ai.ocr.backends.OCRBackend`
  (real EasyOCR adapter, or the deterministic mock in the base environment).
* **Barcode/QR** — a pluggable :class:`~device_ai.ocr.barcode.BarcodeReader`
  (OpenCV-backed, or the deterministic mock).
* **Patterns** — pure regex + validators (IMEI/Luhn, MAC, serial, manufacturer)
  in :mod:`device_ai.ocr.patterns`.
* **Parser** — the pure, deterministic
  :class:`~device_ai.ocr.parser.OCRParser` normalization layer.
* **Models** — frozen value objects
  (:class:`~device_ai.ocr.models.OCRExtraction`, ...).

The :class:`~device_ai.ocr.service.OCRService` facade composes them for the
``/ocr`` API surface.
"""

from __future__ import annotations

from .backends import EasyOCRBackend, MockOCRBackend, OCRBackend
from .barcode import BarcodeReader, MockBarcodeReader, OpenCVBarcodeReader
from .models import (
    BarcodeResult,
    ExtractedField,
    FieldSource,
    FieldType,
    OCRExtraction,
    OCRIdentity,
    TextSpan,
)
from .parser import OCRParser
from .service import OCRService

__all__ = [
    "BarcodeReader",
    "BarcodeResult",
    "EasyOCRBackend",
    "ExtractedField",
    "FieldSource",
    "FieldType",
    "MockBarcodeReader",
    "MockOCRBackend",
    "OCRBackend",
    "OCRExtraction",
    "OCRIdentity",
    "OCRParser",
    "OCRService",
    "OpenCVBarcodeReader",
    "TextSpan",
]
