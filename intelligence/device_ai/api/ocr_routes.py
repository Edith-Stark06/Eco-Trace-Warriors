"""OCR API routes (milestone M1.6).

Three endpoints make up the ``/ocr`` surface:

* ``POST /ocr/extract`` — multipart image upload → recognize text, decode
  barcodes/QR and parse structured identity fields.
* ``POST /ocr/parse``   — JSON spans/barcodes → run the normalization layer
  without an image or a backend.
* ``GET  /ocr/fields``  — discover the supported identity field types.

Routes are thin: they validate/convert input, delegate to the injected
:class:`~device_ai.ocr.service.OCRService`, and serialise the result. No
business logic lives here, and the existing prediction/fingerprint endpoints are
left untouched (this router is mounted under a separate prefix).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from loguru import logger

from ..ocr.models import BarcodeResult, FieldType, OCRExtraction, TextSpan
from ..ocr.service import OCRService
from ..preprocessing.validator import ImageValidator, RawUpload
from .dependencies import get_ocr_service, get_validator
from .ocr_schemas import (
    BarcodeModel,
    ExtractedFieldModel,
    FieldTypesResponse,
    IdentityModel,
    OCRResponse,
    ParseRequest,
    TextSpanResponseModel,
)

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.post("/extract", response_model=OCRResponse)
async def extract_ocr(
    images: Annotated[list[UploadFile], File(description="Device images.")],
    service: Annotated[OCRService, Depends(get_ocr_service)],
    validator: Annotated[ImageValidator, Depends(get_validator)],
) -> OCRResponse:
    """Recognize text, decode barcodes and parse identity fields from images.

    Args:
        images: One to ``MAX_IMAGES`` multipart image files.
        service: Injected OCR service.
        validator: Injected image validator.

    Returns:
        An :class:`OCRResponse` with the extracted fields, raw spans/barcodes,
        identity projection and provenance.

    Raises:
        DeviceAIError: Any validation/OCR failure, translated to the standard
            error envelope by the registered exception handlers.
    """
    uploads = [
        RawUpload(
            filename=upload.filename,
            content_type=upload.content_type,
            data=await upload.read(),
        )
        for upload in images
    ]
    loaded = validator.validate_batch(uploads)
    extraction = service.extract(loaded)
    logger.bind(field_count=len(extraction.fields)).info("OCR extraction complete")
    return _to_ocr_response(extraction)


@router.post("/parse", response_model=OCRResponse)
def parse_ocr(
    payload: ParseRequest,
    service: Annotated[OCRService, Depends(get_ocr_service)],
) -> OCRResponse:
    """Parse client-supplied spans/barcodes into structured identity fields.

    Exposes the pure normalization layer without requiring an image or a
    backend, so the parser behaviour is demonstrable and testable directly.

    Args:
        payload: The raw spans and optional barcodes to normalize.
        service: Injected OCR service.

    Returns:
        An :class:`OCRResponse` for the parsed fields.
    """
    spans = [
        TextSpan(
            text=span.text,
            confidence=span.confidence,
            bounding_box=span.bounding_box,
        )
        for span in payload.spans
    ]
    barcodes = [
        BarcodeResult(
            kind=barcode.kind,
            payload=barcode.payload,
            symbology=barcode.symbology,
            confidence=barcode.confidence,
        )
        for barcode in payload.barcodes
    ]
    extraction = service.parse(spans, barcodes)
    logger.bind(field_count=len(extraction.fields)).info("OCR parse complete")
    return _to_ocr_response(extraction)


@router.get("/fields", response_model=FieldTypesResponse)
def list_field_types() -> FieldTypesResponse:
    """Return the identity field types the OCR engine can extract.

    Returns:
        A :class:`FieldTypesResponse` listing every supported field-type value.
    """
    return FieldTypesResponse(field_types=FieldType.values())


def _to_ocr_response(extraction: OCRExtraction) -> OCRResponse:
    """Convert an :class:`OCRExtraction` into the API schema."""
    identity = extraction.identity
    return OCRResponse(
        fields=[
            ExtractedFieldModel(
                field_type=field_.field_type.value,
                value=field_.value,
                confidence=field_.confidence,
                raw_text=field_.raw_text,
                source=field_.source.value,
            )
            for field_ in extraction.fields
        ],
        spans=[
            TextSpanResponseModel(
                text=span.text,
                confidence=span.confidence,
                bounding_box=(list(span.bounding_box) if span.bounding_box else None),
            )
            for span in extraction.spans
        ],
        barcodes=[
            BarcodeModel(
                kind=barcode.kind,
                payload=barcode.payload,
                symbology=barcode.symbology,
                confidence=barcode.confidence,
            )
            for barcode in extraction.barcodes
        ],
        identity=IdentityModel(
            manufacturer=identity.manufacturer,
            model=identity.model,
            serial_number=identity.serial_number,
            imei=identity.imei,
            mac_address=identity.mac_address,
        ),
        engine_name=extraction.engine_name,
        engine_version=extraction.engine_version,
        created_at=(
            extraction.created_at.isoformat()
            if extraction.created_at is not None
            else None
        ),
        source_hashes=list(extraction.source_hashes),
    )
