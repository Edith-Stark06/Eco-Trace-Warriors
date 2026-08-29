"""FastAPI routes for the Device Registration & Intelligence Enrichment API (P5.2 & P5.3).

Exposes:
- ``POST /devices/register``: Register one or more device candidates from capture images.
- ``GET  /devices/{device_id}``: Retrieve a registered device record by ID.
- ``POST /devices/{device_id}/confirm``: Transition device state DETECTED -> CONFIRMED.
- ``POST /devices/{device_id}/finalize``: Transition device state CONFIRMED -> REGISTERED.
- ``POST /devices/{device_id}/enrich``: Run intelligence enrichment (Brand, Condition, Material, Carbon).
- ``GET  /devices/{device_id}/intelligence``: Retrieve latest intelligence enrichment for a device.
- ``GET  /devices``: List/query registered device records.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, UploadFile
from loguru import logger

from ..configs.settings import Settings, get_settings
from ..devices.enrichment_models import DeviceEnrichment
from ..devices.enrichment_service import DeviceIntelligenceService
from ..devices.models import DeviceRecord
from ..devices.service import DeviceRegistrationService
from ..preprocessing.validator import ImageValidator, RawUpload
from .dependencies import (
    get_device_intelligence_service,
    get_device_service,
    get_validator,
)
from .device_schemas import (
    BrandAssessmentPayload,
    CarbonAssessmentPayload,
    ConditionAssessmentPayload,
    DeviceEnrichmentRequest,
    DeviceEnrichmentResponse,
    DeviceIntelligencePayload,
    DeviceListResponse,
    DeviceRecordPayload,
    DeviceRegistrationResponse,
    DeviceStateUpdateResponse,
    MaterialAssessmentPayload,
    MaterialItemPayload,
)
from .schemas import TimingPayload

router = APIRouter(prefix="/devices", tags=["devices"])


def _to_payload(record: DeviceRecord) -> DeviceRecordPayload:
    """Convert a domain DeviceRecord into an API payload."""
    d = record.to_dict()
    return DeviceRecordPayload(**d)


def _to_intelligence_payload(enrichment: DeviceEnrichment) -> DeviceIntelligencePayload:
    """Convert a domain DeviceEnrichment into an API payload."""
    return DeviceIntelligencePayload(
        device_id=enrichment.device_id,
        brand=BrandAssessmentPayload(**enrichment.brand.to_dict()),
        condition=ConditionAssessmentPayload(**enrichment.condition.to_dict()),
        materials=MaterialAssessmentPayload(
            materials=[
                MaterialItemPayload(**item.to_dict())
                for item in enrichment.materials.materials
            ],
            total_mass_g=enrichment.materials.total_mass_g,
            source=enrichment.materials.source,
            version=enrichment.materials.version,
            notes=enrichment.materials.notes,
        ),
        carbon=CarbonAssessmentPayload(**enrichment.carbon.to_dict()),
        enriched_at=enrichment.enriched_at.isoformat(),
    )


@router.post("/register", response_model=DeviceRegistrationResponse)
async def register_devices(
    request: Request,
    images: Annotated[list[UploadFile], File(description="Device capture images.")],
    service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
    validator: Annotated[ImageValidator, Depends(get_validator)],
    settings: Annotated[Settings, Depends(get_settings)],
    capture_id: Annotated[str | None, Form(description="Optional capture/session ID.")] = None,
) -> DeviceRegistrationResponse:
    """Register physical electronic device candidates detected in capture images.

    Runs computer-vision inference via the existing pipeline, separates distinct
    physical objects into individual DeviceCandidate domain records, classifies
    confidence according to policy, and persists records in DETECTED state.

    Args:
        request: Active HTTP request.
        images: One to MAX_IMAGES uploaded files.
        service: Injected DeviceRegistrationService.
        validator: Injected ImageValidator.
        settings: Application settings.
        capture_id: Optional client/session capture correlation identifier.

    Returns:
        A :class:`DeviceRegistrationResponse` containing all registered candidates.
    """
    t_start = time.perf_counter()
    req_id = request.headers.get("X-Request-ID")

    uploads = [
        RawUpload(
            filename=upload.filename,
            content_type=upload.content_type,
            data=await upload.read(),
        )
        for upload in images
    ]

    t_pre_start = time.perf_counter()
    loaded = validator.validate_batch(uploads)
    t_pre_end = time.perf_counter()
    preprocessing_ms = round((t_pre_end - t_pre_start) * 1000, 2)

    created_records, timing_dict = service.register_from_images(
        images=loaded,
        capture_id=capture_id,
    )
    t_total_end = time.perf_counter()
    total_ms = round((t_total_end - t_start) * 1000, 2)

    timing = TimingPayload(
        preprocessing_ms=preprocessing_ms,
        inference_ms=timing_dict.get("inference_ms", 0.0),
        postprocessing_ms=timing_dict.get("postprocessing_ms", 0.0),
        total_ms=total_ms,
    )

    actual_capture_id = created_records[0].capture_id if created_records else (capture_id or "")

    logger.bind(
        request_id=req_id,
        capture_id=actual_capture_id,
        devices_created=len(created_records),
        total_ms=total_ms,
    ).info("Device registration completed")

    return DeviceRegistrationResponse(
        success=True,
        capture_id=actual_capture_id,
        total_detected=len(created_records),
        devices=[_to_payload(rec) for rec in created_records],
        inference_mode=settings.inference_mode,
        timing=timing,
        request_id=req_id,
    )


@router.get("/{device_id}", response_model=DeviceRecordPayload)
def get_device(
    device_id: str,
    service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
) -> DeviceRecordPayload:
    """Retrieve a device record by unique device ID.

    Args:
        device_id: Public device identifier.
        service: Injected DeviceRegistrationService.

    Returns:
        The :class:`DeviceRecordPayload`.
    """
    record = service.get_device(device_id)
    return _to_payload(record)


@router.post("/{device_id}/confirm", response_model=DeviceStateUpdateResponse)
def confirm_device(
    request: Request,
    device_id: str,
    service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
) -> DeviceStateUpdateResponse:
    """Confirm a detected device candidate (transitions DETECTED -> CONFIRMED).

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        service: Injected DeviceRegistrationService.

    Returns:
        A :class:`DeviceStateUpdateResponse`.
    """
    req_id = request.headers.get("X-Request-ID")
    updated = service.confirm_device(device_id)
    return DeviceStateUpdateResponse(
        success=True,
        device=_to_payload(updated),
        previous_state="DETECTED",
        current_state="CONFIRMED",
        request_id=req_id,
    )


@router.post("/{device_id}/finalize", response_model=DeviceStateUpdateResponse)
def finalize_device(
    request: Request,
    device_id: str,
    service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
) -> DeviceStateUpdateResponse:
    """Finalize a confirmed device registration (transitions CONFIRMED -> REGISTERED).

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        service: Injected DeviceRegistrationService.

    Returns:
        A :class:`DeviceStateUpdateResponse`.
    """
    req_id = request.headers.get("X-Request-ID")
    updated = service.finalize_registration(device_id)
    return DeviceStateUpdateResponse(
        success=True,
        device=_to_payload(updated),
        previous_state="CONFIRMED",
        current_state="REGISTERED",
        request_id=req_id,
    )


@router.post("/{device_id}/enrich", response_model=DeviceEnrichmentResponse)
def enrich_device(
    request: Request,
    device_id: str,
    service: Annotated[DeviceIntelligenceService, Depends(get_device_intelligence_service)],
    body: Annotated[DeviceEnrichmentRequest | None, Body()] = None,
) -> DeviceEnrichmentResponse:
    """Enrich a registered device with brand, condition, material, and carbon intelligence.

    Runs the downstream intelligence pipeline, updates the stored device record,
    and returns both the updated record and full enrichment facets with provenance.

    Args:
        request: Active HTTP request.
        device_id: Target device identifier.
        service: Injected DeviceIntelligenceService.
        body: Optional enrichment parameters (OCR text, condition override).

    Returns:
        A :class:`DeviceEnrichmentResponse`.
    """
    req_id = request.headers.get("X-Request-ID")
    req_body = body or DeviceEnrichmentRequest()

    record, enrichment = service.enrich_device(
        device_id,
        ocr_text=req_body.ocr_text,
        ocr_confidence=req_body.ocr_confidence,
        manual_condition=req_body.manual_condition,
    )

    return DeviceEnrichmentResponse(
        success=True,
        device=_to_payload(record),
        intelligence=_to_intelligence_payload(enrichment),
        request_id=req_id,
    )


@router.get("/{device_id}/intelligence", response_model=DeviceEnrichmentResponse)
def get_device_intelligence(
    request: Request,
    device_id: str,
    service: Annotated[DeviceIntelligenceService, Depends(get_device_intelligence_service)],
) -> DeviceEnrichmentResponse:
    """Retrieve the latest intelligence enrichment facets for a device.

    Args:
        request: Active HTTP request.
        device_id: Target device identifier.
        service: Injected DeviceIntelligenceService.

    Returns:
        A :class:`DeviceEnrichmentResponse`.
    """
    req_id = request.headers.get("X-Request-ID")
    record, enrichment = service.get_device_intelligence(device_id)

    return DeviceEnrichmentResponse(
        success=True,
        device=_to_payload(record),
        intelligence=_to_intelligence_payload(enrichment),
        request_id=req_id,
    )


@router.get("", response_model=DeviceListResponse)
def list_devices(
    service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
    capture_id: Annotated[str | None, Query(description="Filter by capture session ID.")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DeviceListResponse:
    """List stored devices, optionally filtered by capture session ID.

    Args:
        service: Injected DeviceRegistrationService.
        capture_id: Optional capture session filter.
        limit: Max records to return.
        offset: Record offset.

    Returns:
        A :class:`DeviceListResponse`.
    """
    if capture_id:
        records = service.find_by_capture(capture_id)
        total = len(records)
        paged = records[offset : offset + limit]
    else:
        paged = service.list_devices(limit=limit, offset=offset)
        total = len(paged)

    return DeviceListResponse(
        total=total,
        devices=[_to_payload(r) for r in paged],
        limit=limit,
        offset=offset,
    )
