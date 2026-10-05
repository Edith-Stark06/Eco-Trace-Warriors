"""OCR domain models (milestone M1.6).

Value objects the OCR Intelligence Engine passes between its stages. They are
frozen, slotted dataclasses (no HTTP concerns, no I/O) so every collaborator —
the backends, the barcode reader, the parser and the service — is independently
testable and the whole engine is deterministic.

The pipeline is:

* :class:`TextSpan` — one raw text detection from an OCR backend.
* :class:`BarcodeResult` — one decoded QR/barcode payload.
* :class:`ExtractedField` — a normalized, confidence-scored identity field the
  parser derives from spans/barcodes, tagged with its :class:`FieldType`.
* :class:`OCRExtraction` — the full result: the extracted fields plus the raw
  spans/barcodes and provenance (engine identity, creation time, source hashes).
* :class:`OCRIdentity` — the small projection the fingerprint engine optionally
  consumes (manufacturer/model/serial/IMEI/MAC), each an empty string when the
  field was not found.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import cast


class FieldType(str, Enum):
    """The structured identity fields the engine extracts.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from an API/settings string (e.g. ``"serial_number"``).
    """

    MANUFACTURER = "manufacturer"
    MODEL = "model"
    SERIAL_NUMBER = "serial_number"
    IMEI = "imei"
    MAC_ADDRESS = "mac_address"
    QR_CODE = "qr_code"
    BARCODE = "barcode"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every field type, in declaration order."""
        return [member.value for member in cls]


class FieldSource(str, Enum):
    """Where an :class:`ExtractedField` value originated."""

    TEXT = "text"
    BARCODE = "barcode"
    QR = "qr"


@dataclass(frozen=True, slots=True)
class TextSpan:
    """A single raw text detection produced by an OCR backend.

    Attributes:
        text: The recognized text exactly as returned by the backend.
        confidence: Backend recognition confidence in ``[0, 1]``.
        bounding_box: Optional ``(x1, y1, x2, y2)`` pixel box of the detection,
            or ``None`` when the backend does not report geometry.
    """

    text: str
    confidence: float
    bounding_box: tuple[int, int, int, int] | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the span."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "bounding_box": list(self.bounding_box) if self.bounding_box else None,
        }


@dataclass(frozen=True, slots=True)
class BarcodeResult:
    """A single decoded barcode or QR code.

    Attributes:
        kind: ``"qr"`` for 2-D QR codes, ``"barcode"`` for 1-D barcodes.
        payload: The decoded string payload.
        symbology: Detected symbology/format (e.g. ``"QRCODE"``, ``"EAN13"``),
            empty when the reader does not report it.
        confidence: Decoder confidence in ``[0, 1]``.
    """

    kind: str
    payload: str
    symbology: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the barcode."""
        return {
            "kind": self.kind,
            "payload": self.payload,
            "symbology": self.symbology,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class ExtractedField:
    """A normalized, confidence-scored identity field.

    Attributes:
        field_type: Which identity field this is.
        value: The normalized field value.
        confidence: Combined confidence in ``[0, 1]`` (recognition strength ×
            pattern strength × validator pass).
        raw_text: The raw span/payload text the value was derived from.
        source: Whether the value came from recognized text, a barcode or a QR.
    """

    field_type: FieldType
    value: str
    confidence: float
    raw_text: str = ""
    source: FieldSource = FieldSource.TEXT

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the field."""
        return {
            "field_type": self.field_type.value,
            "value": self.value,
            "confidence": self.confidence,
            "raw_text": self.raw_text,
            "source": self.source.value,
        }


@dataclass(frozen=True, slots=True)
class OCRIdentity:
    """The identity projection the fingerprint engine optionally consumes.

    Every field defaults to an empty string, so an absent field never breaks a
    consumer and :meth:`is_empty` cleanly reports "nothing was extracted".

    Attributes:
        manufacturer: Extracted manufacturer/brand, empty when absent.
        model: Extracted model identifier, empty when absent.
        serial_number: Extracted serial number, empty when absent.
        imei: Extracted IMEI, empty when absent.
        mac_address: Extracted MAC address, empty when absent.
    """

    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    imei: str = ""
    mac_address: str = ""

    @property
    def is_empty(self) -> bool:
        """Whether no identity field carries a value."""
        return not any(
            (
                self.manufacturer,
                self.model,
                self.serial_number,
                self.imei,
                self.mac_address,
            )
        )

    def to_dict(self) -> dict[str, str]:
        """Return a plain ``dict`` of the identity fields (all keys present)."""
        return {
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "imei": self.imei,
            "mac_address": self.mac_address,
        }

    def non_empty(self) -> dict[str, str]:
        """Return only the identity fields that carry a value."""
        return {key: value for key, value in self.to_dict().items() if value}


@dataclass(frozen=True, slots=True)
class OCRExtraction:
    """The full structured result of running the OCR engine over a batch.

    Attributes:
        fields: The extracted, normalized identity fields (highest-confidence
            candidate per field type).
        spans: The raw text detections the extraction was derived from.
        barcodes: The decoded barcode/QR results.
        engine_name: Name of the OCR backend that produced the spans.
        engine_version: Version of that backend.
        created_at: UTC timestamp the extraction was produced.
        source_hashes: SHA-256 content hashes of the source images (provenance).
    """

    fields: tuple[ExtractedField, ...] = field(default_factory=tuple)
    spans: tuple[TextSpan, ...] = field(default_factory=tuple)
    barcodes: tuple[BarcodeResult, ...] = field(default_factory=tuple)
    engine_name: str = "ocr"
    engine_version: str = ""
    created_at: datetime | None = None
    source_hashes: tuple[str, ...] = field(default_factory=tuple)

    def get(self, field_type: FieldType) -> ExtractedField | None:
        """Return the extracted field of ``field_type``, or ``None`` if absent.

        Args:
            field_type: The field type to look up.

        Returns:
            The matching :class:`ExtractedField`, or ``None`` when the engine
            did not extract that field.
        """
        for extracted in self.fields:
            if extracted.field_type is field_type:
                return extracted
        return None

    def value_of(self, field_type: FieldType) -> str:
        """Return the value of ``field_type``, or ``""`` when absent."""
        found = self.get(field_type)
        return found.value if found is not None else ""

    @property
    def identity(self) -> OCRIdentity:
        """Project the extracted fields onto an :class:`OCRIdentity`."""
        return OCRIdentity(
            manufacturer=self.value_of(FieldType.MANUFACTURER),
            model=self.value_of(FieldType.MODEL),
            serial_number=self.value_of(FieldType.SERIAL_NUMBER),
            imei=self.value_of(FieldType.IMEI),
            mac_address=self.value_of(FieldType.MAC_ADDRESS),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the extraction.

        Returns:
            A plain ``dict`` with an ISO-8601 ``created_at`` (or ``None``) and
            list-typed sequences, suitable for JSON persistence or a response.
        """
        return {
            "fields": [field_.to_dict() for field_ in self.fields],
            "spans": [span.to_dict() for span in self.spans],
            "barcodes": [barcode.to_dict() for barcode in self.barcodes],
            "identity": self.identity.to_dict(),
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
            "source_hashes": list(self.source_hashes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> OCRExtraction:
        """Reconstruct an :class:`OCRExtraction` from :meth:`to_dict` output.

        Args:
            data: A mapping previously produced by :meth:`to_dict`.

        Returns:
            The reconstructed extraction.
        """
        raw_fields = cast(Iterable[dict[str, object]], data.get("fields", ()))
        raw_spans = cast(Iterable[dict[str, object]], data.get("spans", ()))
        raw_barcodes = cast(Iterable[dict[str, object]], data.get("barcodes", ()))
        raw_created = data.get("created_at")
        return cls(
            fields=tuple(_field_from_dict(item) for item in raw_fields),
            spans=tuple(_span_from_dict(item) for item in raw_spans),
            barcodes=tuple(_barcode_from_dict(item) for item in raw_barcodes),
            engine_name=str(data.get("engine_name", "ocr")),
            engine_version=str(data.get("engine_version", "")),
            created_at=(
                datetime.fromisoformat(str(raw_created))
                if raw_created is not None
                else None
            ),
            source_hashes=tuple(
                str(h) for h in cast(Iterable[object], data.get("source_hashes", ()))
            ),
        )


def _span_from_dict(data: dict[str, object]) -> TextSpan:
    """Reconstruct a :class:`TextSpan` from its dict representation."""
    box = data.get("bounding_box")
    bounding_box: tuple[int, int, int, int] | None = None
    if box is not None:
        coords = [int(v) for v in cast(Sequence[float], box)]
        bounding_box = (coords[0], coords[1], coords[2], coords[3])
    return TextSpan(
        text=str(data["text"]),
        confidence=float(cast(float, data["confidence"])),
        bounding_box=bounding_box,
    )


def _barcode_from_dict(data: dict[str, object]) -> BarcodeResult:
    """Reconstruct a :class:`BarcodeResult` from its dict representation."""
    return BarcodeResult(
        kind=str(data["kind"]),
        payload=str(data["payload"]),
        symbology=str(data.get("symbology", "")),
        confidence=float(cast(float, data.get("confidence", 1.0))),
    )


def _field_from_dict(data: dict[str, object]) -> ExtractedField:
    """Reconstruct an :class:`ExtractedField` from its dict representation."""
    return ExtractedField(
        field_type=FieldType(str(data["field_type"])),
        value=str(data["value"]),
        confidence=float(cast(float, data["confidence"])),
        raw_text=str(data.get("raw_text", "")),
        source=FieldSource(str(data.get("source", "text"))),
    )
