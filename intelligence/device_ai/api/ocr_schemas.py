"""Pydantic v2 schemas for the OCR endpoints (milestone M1.6).

These models define the public contract of the ``/ocr`` surface. They validate
request bodies at the transport boundary and serialise the OCR value objects
into JSON payloads, keeping the OCR domain layer free of HTTP concerns.

The request models for ``POST /ocr/parse`` mirror :class:`TextSpan` /
:class:`BarcodeResult` so the pure normalization layer is exercisable without an
image or a backend; the response models mirror
:meth:`~device_ai.ocr.models.OCRExtraction.to_dict`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ``model_*`` field names (e.g. ``model``) collide with Pydantic's protected
# namespace; disabling it keeps the wire contract aligned with FieldType values.
_ALLOW_MODEL_FIELDS = ConfigDict(protected_namespaces=())

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class TextSpanModel(BaseModel):
    """A raw OCR text span supplied to ``POST /ocr/parse``."""

    text: str = Field(description="The recognized text exactly as detected.")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Recognition confidence in [0, 1]."
    )
    bounding_box: tuple[int, int, int, int] | None = Field(
        default=None,
        description="Optional (x1, y1, x2, y2) pixel box of the detection.",
    )


class BarcodeModel(BaseModel):
    """A decoded barcode/QR supplied to ``POST /ocr/parse`` or returned."""

    kind: str = Field(description="'qr' for 2-D QR codes, 'barcode' for 1-D.")
    payload: str = Field(description="The decoded string payload.")
    symbology: str = Field(
        default="", description="Detected symbology (e.g. 'QRCODE', 'EAN13')."
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Decoder confidence in [0, 1]."
    )


class ParseRequest(BaseModel):
    """Request body for ``POST /ocr/parse``.

    Carries raw spans (and optional barcodes) for the parser to normalize into
    structured identity fields, so the normalization layer is demonstrable and
    testable without images.
    """

    spans: list[TextSpanModel] = Field(
        default_factory=list, description="Raw OCR text spans to parse."
    )
    barcodes: list[BarcodeModel] = Field(
        default_factory=list, description="Optional decoded barcodes/QR codes."
    )


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class ExtractedFieldModel(BaseModel):
    """A normalized, confidence-scored identity field in a response."""

    model_config = _ALLOW_MODEL_FIELDS

    field_type: str = Field(description="Which identity field this is.")
    value: str = Field(description="The normalized field value.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Combined confidence in [0, 1]."
    )
    raw_text: str = Field(
        default="", description="Raw span/payload the value was derived from."
    )
    source: str = Field(
        default="text", description="Origin of the value: 'text', 'barcode' or 'qr'."
    )


class IdentityModel(BaseModel):
    """The identity projection (manufacturer/model/serial/IMEI/MAC)."""

    model_config = _ALLOW_MODEL_FIELDS

    manufacturer: str = Field(default="", description="Extracted manufacturer.")
    model: str = Field(default="", description="Extracted model identifier.")
    serial_number: str = Field(default="", description="Extracted serial number.")
    imei: str = Field(default="", description="Extracted IMEI.")
    mac_address: str = Field(default="", description="Extracted MAC address.")


class TextSpanResponseModel(BaseModel):
    """A raw OCR text span echoed in a response."""

    text: str = Field(description="The recognized text.")
    confidence: float = Field(ge=0.0, le=1.0, description="Recognition confidence.")
    bounding_box: list[int] | None = Field(
        default=None, description="Optional (x1, y1, x2, y2) pixel box."
    )


class OCRResponse(BaseModel):
    """Response body for ``POST /ocr/extract`` and ``POST /ocr/parse``.

    Mirrors :meth:`~device_ai.ocr.models.OCRExtraction.to_dict`: the winning
    field per type, the raw spans/barcodes, the identity projection and
    provenance metadata.
    """

    fields: list[ExtractedFieldModel] = Field(
        default_factory=list, description="Winning identity field per type."
    )
    spans: list[TextSpanResponseModel] = Field(
        default_factory=list, description="Raw text detections the fields came from."
    )
    barcodes: list[BarcodeModel] = Field(
        default_factory=list, description="Decoded barcode/QR results."
    )
    identity: IdentityModel = Field(
        default_factory=IdentityModel, description="Identity projection."
    )
    engine_name: str = Field(description="Name of the OCR backend.")
    engine_version: str = Field(description="Version of that backend.")
    created_at: str | None = Field(
        default=None, description="ISO-8601 UTC creation timestamp (or null)."
    )
    source_hashes: list[str] = Field(
        default_factory=list,
        description="SHA-256 content hashes of the source images (provenance).",
    )


class FieldTypesResponse(BaseModel):
    """Response body for ``GET /ocr/fields`` (supported field-type discovery)."""

    field_types: list[str] = Field(
        description="Wire values of every supported identity field type."
    )
