"""OCR parser: noisy spans/barcodes → structured identity fields (M1.6).

The :class:`OCRParser` is the normalization layer at the heart of the engine.
It is **pure and deterministic**: given a list of :class:`TextSpan` and
:class:`BarcodeResult` it returns an :class:`OCRExtraction` with the
highest-confidence, normalized value per :class:`FieldType`. No image, no OCR
backend and no clock are involved, so it is fully unit-testable from hand-built
inputs — which is exactly what the ``POST /ocr/parse`` endpoint exposes.

How a field is scored::

    field_confidence = clamp(recognition_conf * pattern_strength, 0, 1)

* ``recognition_conf`` — the backend's confidence in the span (``1.0`` for a
  clean barcode payload).
* ``pattern_strength`` — how strongly the text matches the expected shape (see
  :mod:`device_ai.ocr.patterns`); a Luhn-valid IMEI outscores a bare digit run.

Label awareness: a span like ``"S/N: ABC123"`` both *labels* the value (raising
its serial pattern strength) and *isolates* it (the label is stripped before
matching). Barcode/QR payloads become :class:`FieldType.QR_CODE` /
:class:`FieldType.BARCODE` fields and are additionally mined for an embedded
serial or IMEI, since device labels frequently encode the serial in the barcode.
"""

from __future__ import annotations

from . import patterns
from .models import (
    BarcodeResult,
    ExtractedField,
    FieldSource,
    FieldType,
    OCRExtraction,
    TextSpan,
)


def _clamp(value: float) -> float:
    """Clamp ``value`` into the ``[0, 1]`` range."""
    return max(0.0, min(1.0, value))


class OCRParser:
    """Convert raw OCR spans and barcodes into structured identity fields.

    The parser is stateless; a single instance is safe to share. Every method
    is pure, so results depend only on the inputs.
    """

    def parse(
        self,
        spans: list[TextSpan],
        barcodes: list[BarcodeResult] | None = None,
    ) -> OCRExtraction:
        """Extract normalized identity fields from spans and barcodes.

        Args:
            spans: Raw text detections (from a backend or a client).
            barcodes: Optional decoded barcode/QR results.

        Returns:
            An :class:`OCRExtraction` carrying the winning field per type plus
            the raw spans/barcodes. Provenance fields (engine identity,
            ``created_at``, ``source_hashes``) are left at their defaults for
            the service layer to stamp.
        """
        barcodes = barcodes or []
        # Collect every candidate per field type, then keep the strongest.
        candidates: dict[FieldType, list[ExtractedField]] = {}

        for span in spans:
            for extracted in self._fields_from_span(span):
                candidates.setdefault(extracted.field_type, []).append(extracted)

        for barcode in barcodes:
            for extracted in self._fields_from_barcode(barcode):
                candidates.setdefault(extracted.field_type, []).append(extracted)

        fields = tuple(
            self._best(candidates[field_type])
            for field_type in FieldType
            if field_type in candidates
        )
        return OCRExtraction(
            fields=fields,
            spans=tuple(spans),
            barcodes=tuple(barcodes),
        )

    # -- Span extraction --------------------------------------------------

    def _fields_from_span(self, span: TextSpan) -> list[ExtractedField]:
        """Return every identity field a single text span yields."""
        text = span.text
        fields: list[ExtractedField] = []

        # IMEI — label boosts confidence but the shape (15 digits) stands alone.
        imei = patterns.find_imei(text)
        if imei is not None:
            boost = 1.05 if patterns.has_imei_label(text) else 1.0
            fields.append(
                self._field(FieldType.IMEI, imei, span, FieldSource.TEXT, boost)
            )

        # MAC address — self-describing shape.
        mac = patterns.find_mac(text)
        if mac is not None:
            fields.append(
                self._field(FieldType.MAC_ADDRESS, mac, span, FieldSource.TEXT)
            )

        # Serial — label-aware; strip the label from the value first.
        serial_labelled = patterns.has_serial_label(text)
        serial_value_text = patterns.strip_label(text) if serial_labelled else text
        serial = patterns.find_serial(serial_value_text, labelled=serial_labelled)
        if serial is not None:
            fields.append(
                self._field(FieldType.SERIAL_NUMBER, serial, span, FieldSource.TEXT)
            )

        # Model — only from a labelled span.
        if patterns.has_model_label(text):
            model = patterns.find_model(patterns.strip_label(text), labelled=True)
            if model is not None:
                fields.append(
                    self._field(FieldType.MODEL, model, span, FieldSource.TEXT)
                )

        # Manufacturer — keyword table.
        manufacturer = patterns.find_manufacturer(text)
        if manufacturer is not None:
            fields.append(
                self._field(
                    FieldType.MANUFACTURER, manufacturer, span, FieldSource.TEXT
                )
            )

        return fields

    # -- Barcode extraction -----------------------------------------------

    def _fields_from_barcode(self, barcode: BarcodeResult) -> list[ExtractedField]:
        """Return fields a barcode/QR yields: the code itself plus mined IDs."""
        source = FieldSource.QR if barcode.kind == "qr" else FieldSource.BARCODE
        field_type = FieldType.QR_CODE if barcode.kind == "qr" else FieldType.BARCODE
        fields: list[ExtractedField] = [
            ExtractedField(
                field_type=field_type,
                value=barcode.payload,
                confidence=_clamp(barcode.confidence),
                raw_text=barcode.payload,
                source=source,
            )
        ]

        # Mine the payload for an embedded IMEI or serial (device labels often
        # encode the serial in the barcode). A synthetic span carries the
        # decoder confidence so the shared scoring applies uniformly.
        payload_span = TextSpan(text=barcode.payload, confidence=barcode.confidence)
        imei = patterns.find_imei(barcode.payload)
        if imei is not None:
            fields.append(self._field(FieldType.IMEI, imei, payload_span, source))
        else:
            serial = patterns.find_serial(barcode.payload, labelled=False)
            if serial is not None:
                fields.append(
                    self._field(FieldType.SERIAL_NUMBER, serial, payload_span, source)
                )
        return fields

    # -- Scoring helpers --------------------------------------------------

    def _field(
        self,
        field_type: FieldType,
        candidate: patterns.PatternCandidate,
        span: TextSpan,
        source: FieldSource,
        boost: float = 1.0,
    ) -> ExtractedField:
        """Build an :class:`ExtractedField` with combined confidence.

        Confidence combines the span's recognition confidence with the pattern
        strength (and an optional label boost), clamped to ``[0, 1]``.
        """
        confidence = _clamp(span.confidence * candidate.strength * boost)
        return ExtractedField(
            field_type=field_type,
            value=candidate.value,
            confidence=confidence,
            raw_text=candidate.raw_text,
            source=source,
        )

    @staticmethod
    def _best(fields: list[ExtractedField]) -> ExtractedField:
        """Return the highest-confidence field, tie-broken by value.

        Sorting by ``(-confidence, value)`` keeps the result deterministic when
        two candidates share a confidence.
        """
        return sorted(fields, key=lambda f: (-f.confidence, f.value))[0]
