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

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, Response, UploadFile, status
from loguru import logger

from ..configs.settings import Settings, get_settings
from ..devices.enrichment_models import DeviceEnrichment
from ..devices.enrichment_service import DeviceIntelligenceService
from ..devices.models import DeviceEventType, DeviceRecord
from ..devices.passport import DevicePassport
from ..devices.passport_verification import PassportVerificationResult
from ..devices.service import DeviceRegistrationService
from ..devices.trust_anchor import (
    DevicePassportTrustService,
    TrustAnchor,
    TrustAnchorVerification,
)
from ..preprocessing.validator import ImageValidator, RawUpload
from .dependencies import (
    get_device_intelligence_service,
    get_device_service,
    get_trust_service,
    get_validator,
)
from .device_schemas import (
    AnchorPassportRequest,
    AuditFacetPayload,
    BrandAssessmentPayload,
    BrandFacetPayload,
    CarbonAssessmentPayload,
    CarbonFacetPayload,
    ConditionAssessmentPayload,
    ConditionFacetPayload,
    DetectionFacetPayload,
    DeviceEnrichmentRequest,
    DeviceEnrichmentResponse,
    DeviceEventPayload,
    DeviceHistoryResponse,
    DeviceIdentityPayload,
    DeviceIntelligencePayload,
    DeviceListResponse,
    DevicePassportPayload,
    DevicePassportResponse,
    DevicePassportVerificationResponse,
    DeviceRecordPayload,
    DeviceRegistrationResponse,
    DeviceStateUpdateResponse,
    DeviceTrustStatusResponse,
    ExternalTrustAnchorPayload,
    ExternalTrustAnchorResponse,
    ExternalTrustVerificationPayload,
    ExternalTrustVerificationResponse,
    FullDeviceTrustStatusResponse,
    FullTrustComparisonPayload,
    LifecycleFacetPayload,
    MaterialAssessmentPayload,
    MaterialFacetPayload,
    MaterialItemPayload,
    PassportVerificationPayload,
    TrustAnchorPayload,
    TrustAnchorResponse,
    TrustAnchorVerificationPayload,
    TrustAnchorVerificationResponse,
    TrustStatusPayload,
    VerificationCheckDetailPayload,
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


@router.get("/{device_id}/events", response_model=DeviceHistoryResponse)
@router.get("/{device_id}/history", response_model=DeviceHistoryResponse)
def get_device_history(
    request: Request,
    device_id: str,
    service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
) -> DeviceHistoryResponse:
    """Retrieve chronological audit event history for a device record.

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        service: Injected DeviceRegistrationService.

    Returns:
        A :class:`DeviceHistoryResponse` containing ordered audit events.
    """
    req_id = request.headers.get("X-Request-ID")
    record = service.get_device(device_id)
    events = service.get_device_events(device_id)

    event_payloads = [
        DeviceEventPayload(
            event_id=e.event_id,
            device_id=e.device_id,
            event_type=e.event_type.value if isinstance(e.event_type, DeviceEventType) else str(e.event_type),
            timestamp=e.timestamp.isoformat(),
            capture_id=e.capture_id,
            metadata=e.metadata,
        )
        for e in events
    ]

    return DeviceHistoryResponse(
        success=True,
        device_id=record.device_id,
        current_state=record.registration_state.value,
        events=event_payloads,
        total_events=len(event_payloads),
        request_id=req_id,
    )


def _to_passport_payload(passport: DevicePassport) -> DevicePassportPayload:
    """Convert a domain DevicePassport into an API payload."""
    return DevicePassportPayload(
        device_id=passport.device_id,
        eco_id=passport.eco_id,
        identity=DeviceIdentityPayload(
            device_id=passport.identity.device_id,
            eco_id=passport.identity.eco_id,
            device_type=passport.identity.device_type,
            class_id=passport.identity.class_id,
            capture_id=passport.identity.capture_id,
            registration_timestamp=passport.identity.registration_timestamp,
            created_at=passport.identity.created_at,
            updated_at=passport.identity.updated_at,
        ),
        detection=DetectionFacetPayload(
            confidence=passport.detection.confidence,
            confidence_state=passport.detection.confidence_state,
            bounding_box=passport.detection.bounding_box,
            inference_mode=passport.detection.inference_mode,
            model_version=passport.detection.model_version,
        ),
        brand=BrandFacetPayload(
            brand=passport.brand.brand,
            status=passport.brand.status,
            source=passport.brand.source,
            confidence=passport.brand.confidence,
            raw_text=passport.brand.raw_text,
        ),
        condition=ConditionFacetPayload(
            condition=passport.condition.condition,
            status=passport.condition.status,
            source=passport.condition.source,
            notes=passport.condition.notes,
        ),
        material=MaterialFacetPayload(
            materials=[
                MaterialItemPayload(
                    material=m.material,
                    category=m.category,
                    mass_g=m.mass_g,
                    recoverable=m.recoverable,
                    hazardous=m.hazardous,
                    basis=m.basis,
                )
                for m in passport.material.materials
            ],
            total_mass_g=passport.material.total_mass_g,
            source=passport.material.source,
            version=passport.material.version,
            notes=passport.material.notes,
        ),
        carbon=CarbonFacetPayload(
            carbon_score=passport.carbon.carbon_score,
            contributing_factors=passport.carbon.contributing_factors,
            methodology=passport.carbon.methodology,
            source=passport.carbon.source,
            version=passport.carbon.version,
            notes=passport.carbon.notes,
        ),
        lifecycle=LifecycleFacetPayload(
            current_state=passport.lifecycle.current_state,
            is_confirmed=passport.lifecycle.is_confirmed,
            is_registered=passport.lifecycle.is_registered,
            is_enriched=passport.lifecycle.is_enriched,
        ),
        audit=AuditFacetPayload(
            total_events=passport.audit.total_events,
            events=[
                DeviceEventPayload(
                    event_id=e["event_id"],
                    device_id=e["device_id"],
                    event_type=e["event_type"],
                    timestamp=e["timestamp"],
                    capture_id=e.get("capture_id"),
                    metadata=e.get("metadata", {}),
                )
                for e in passport.audit.events
            ],
        ),
        generated_at=passport.generated_at,
    )


@router.get("/{device_id}/passport", response_model=DevicePassportResponse)
def get_device_passport(
    request: Request,
    device_id: str,
    service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
) -> DevicePassportResponse:
    """Retrieve the aggregated, read-oriented Device Passport and Traceability record.

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        service: Injected DeviceRegistrationService.

    Returns:
        A :class:`DevicePassportResponse` containing the aggregated passport.
    """
    req_id = request.headers.get("X-Request-ID")
    passport = service.get_device_passport(device_id)

    return DevicePassportResponse(
        success=True,
        passport=_to_passport_payload(passport),
        request_id=req_id,
    )


def _to_verification_payload(result: PassportVerificationResult) -> PassportVerificationPayload:
    """Convert domain PassportVerificationResult into API payload."""
    return PassportVerificationPayload(
        device_id=result.device_id,
        verification_status=result.verification_status.value,
        passport_fingerprint=result.passport_fingerprint,
        checks=result.checks,
        check_details=[
            VerificationCheckDetailPayload(
                name=c.name,
                status=c.status.value,
                message=c.message,
                details=c.details,
            )
            for c in result.check_details
        ],
        warnings=result.warnings,
        errors=result.errors,
        verified_at=result.verified_at,
    )


@router.get("/{device_id}/passport/verify", response_model=DevicePassportVerificationResponse)
def verify_device_passport(
    request: Request,
    device_id: str,
    service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
) -> DevicePassportVerificationResponse:
    """Execute deterministic integrity, lifecycle, and provenance verification of a Device Passport.

    Strictly read-only: does not modify device state, write to the database, or emit audit events.

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        service: Injected DeviceRegistrationService.

    Returns:
        A :class:`DevicePassportVerificationResponse` containing the verification evaluation.
    """
    req_id = request.headers.get("X-Request-ID")
    verification_result = service.verify_device_passport(device_id)

    return DevicePassportVerificationResponse(
        success=True,
        verification=_to_verification_payload(verification_result),
        request_id=req_id,
    )


# ---------------------------------------------------------------------------
# Trust Anchor Layer Endpoints (P5.8)
# ---------------------------------------------------------------------------


@router.post("/{device_id}/passport/anchor", response_model=TrustAnchorResponse, status_code=status.HTTP_200_OK)
def anchor_device_passport(
    request: Request,
    response: Response,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
    body: AnchorPassportRequest | None = None,
) -> TrustAnchorResponse:
    """Verify and anchor the Device Passport in the Trust Anchor layer.

    Status codes:
    - 201 Created: When a new anchor is created.
    - 200 OK: When returning an existing idempotent anchor.

    Args:
        request: Active HTTP request.
        response: Active HTTP response (to set 201 status code on new anchor creation).
        device_id: Public device identifier.
        trust_service: Injected DevicePassportTrustService.
        body: Optional request body containing anchor metadata.

    Returns:
        A :class:`TrustAnchorResponse` containing the anchor payload.
    """
    req_id = request.headers.get("X-Request-ID")
    metadata = body.metadata if body else None
    anchor, is_new = trust_service.anchor_device_passport(device_id, metadata=metadata)

    if is_new:
        response.status_code = status.HTTP_201_CREATED

    return TrustAnchorResponse(
        success=True,
        anchor=TrustAnchorPayload(
            anchor_id=anchor.anchor_id,
            device_id=anchor.device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            algorithm=anchor.algorithm,
            anchored_at=anchor.anchored_at,
            status=anchor.status.value,
            metadata=anchor.metadata,
        ),
        is_new=is_new,
        request_id=req_id,
    )


@router.get("/{device_id}/passport/anchor", response_model=TrustAnchorResponse)
def get_device_anchor(
    request: Request,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
) -> TrustAnchorResponse:
    """Retrieve the stored Trust Anchor for a device.

    Strictly read-only.

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        trust_service: Injected DevicePassportTrustService.

    Returns:
        A :class:`TrustAnchorResponse` containing the anchor payload.
    """
    req_id = request.headers.get("X-Request-ID")
    anchor = trust_service.get_device_anchor(device_id)

    return TrustAnchorResponse(
        success=True,
        anchor=TrustAnchorPayload(
            anchor_id=anchor.anchor_id,
            device_id=anchor.device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            algorithm=anchor.algorithm,
            anchored_at=anchor.anchored_at,
            status=anchor.status.value,
            metadata=anchor.metadata,
        ),
        is_new=False,
        request_id=req_id,
    )


@router.get("/{device_id}/passport/anchor/verify", response_model=TrustAnchorVerificationResponse)
def verify_device_anchor(
    request: Request,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
) -> TrustAnchorVerificationResponse:
    """Verify current passport fingerprint against the anchored trust record.

    Strictly read-only: does not modify device, passport, or anchor.

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        trust_service: Injected DevicePassportTrustService.

    Returns:
        A :class:`TrustAnchorVerificationResponse` containing the verification outcome.
    """
    req_id = request.headers.get("X-Request-ID")
    verification = trust_service.verify_device_anchor(device_id)

    return TrustAnchorVerificationResponse(
        success=True,
        verification=TrustAnchorVerificationPayload(
            device_id=verification.device_id,
            status=verification.status.value,
            stored_fingerprint=verification.stored_fingerprint,
            current_fingerprint=verification.current_fingerprint,
            algorithm=verification.algorithm,
            verified_at=verification.verified_at,
            message=verification.message,
            details=verification.details,
        ),
        request_id=req_id,
    )


@router.get("/{device_id}/trust", response_model=DeviceTrustStatusResponse)
def get_device_trust_status(
    request: Request,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
) -> DeviceTrustStatusResponse:
    """Evaluate canonical trust status for a device (P5.10).

    Strictly read-only query that checks whether the current Device Passport
    corresponds to the anchored record, evaluates integrity, and verifies freshness.
    Guarantees zero database writes, zero device mutations, and zero audit event emissions.

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        trust_service: Injected DevicePassportTrustService.

    Returns:
        A :class:`DeviceTrustStatusResponse` containing comprehensive trust details.
    """
    req_id = request.headers.get("X-Request-ID")
    result = trust_service.get_device_trust_status(device_id)

    return DeviceTrustStatusResponse(
        success=True,
        trust=TrustStatusPayload(
            device_id=result.device_id,
            status=result.status.value,
            passport_fingerprint=result.passport_fingerprint,
            anchored_fingerprint=result.anchored_fingerprint,
            anchor_id=result.anchor_id,
            algorithm=result.algorithm,
            anchored_at=result.anchored_at,
            evaluated_at=result.evaluated_at,
            verification_status=result.verification_status,
            reason=result.reason,
            is_fresh=result.is_fresh,
            max_age_days=result.max_age_days,
            age_days=result.age_days,
            checks=result.checks,
            details=result.details,
        ),
        request_id=req_id,
    )


@router.post("/{device_id}/passport/reanchor", response_model=TrustAnchorResponse)
def reanchor_device_passport(
    request: Request,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
    body: AnchorPassportRequest | None = None,
) -> TrustAnchorResponse:
    """Explicitly re-anchor a verified device passport, replacing any outdated anchor (P5.10).

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        body: Optional anchor request payload with additional context metadata.
        trust_service: Injected DevicePassportTrustService.

    Returns:
        A :class:`TrustAnchorResponse` with the updated anchor and ``is_new=True``.
    """
    req_id = request.headers.get("X-Request-ID")
    metadata = body.metadata if body else {}

    anchor, is_changed = trust_service.reanchor_device_passport(
        device_id=device_id,
        metadata=metadata,
    )

    return TrustAnchorResponse(
        success=True,
        anchor=TrustAnchorPayload(
            anchor_id=anchor.anchor_id,
            device_id=anchor.device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            algorithm=anchor.algorithm,
            anchored_at=anchor.anchored_at,
            status=anchor.status.value,
            metadata=anchor.metadata,
        ),
        is_new=is_changed,
        request_id=req_id,
    )


# ---------------------------------------------------------------------------
# External / Blockchain Trust Endpoints (P5.11)
# ---------------------------------------------------------------------------


@router.post(
    "/{device_id}/passport/external-anchor",
    response_model=ExternalTrustAnchorResponse,
    status_code=status.HTTP_200_OK,
)
def anchor_device_passport_externally(
    request: Request,
    response: Response,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
    body: AnchorPassportRequest | None = None,
) -> ExternalTrustAnchorResponse:
    """Submit and record an external / blockchain trust anchor for a locally verified passport (P5.11).

    Status codes (P9.7, matching the sibling ``/passport/anchor`` route):
    - 201 Created: When a new external anchor is created.
    - 200 OK: When returning an existing idempotent anchor.

    Args:
        request: Active HTTP request.
        response: Active HTTP response (to set 201 status code on new anchor creation).
        device_id: Public device identifier.
        trust_service: Injected DevicePassportTrustService.
        body: Optional anchor request with metadata.

    Returns:
        An :class:`ExternalTrustAnchorResponse` with the external anchor details.
    """
    req_id = request.headers.get("X-Request-ID")
    metadata = body.metadata if body else {}

    anchor, is_new = trust_service.anchor_device_passport_externally(
        device_id=device_id,
        metadata=metadata,
    )

    if is_new:
        response.status_code = status.HTTP_201_CREATED

    return ExternalTrustAnchorResponse(
        success=True,
        anchor=ExternalTrustAnchorPayload(
            external_anchor_id=anchor.external_anchor_id,
            device_id=anchor.device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            algorithm=anchor.algorithm,
            provider=anchor.provider,
            network=anchor.network,
            transaction_id=anchor.transaction_id,
            anchored_at=anchor.anchored_at,
            status=anchor.status,
            metadata=anchor.metadata,
        ),
        is_new=is_new,
        request_id=req_id,
    )


@router.get("/{device_id}/passport/external-anchor", response_model=ExternalTrustAnchorResponse)
def get_device_external_anchor(
    request: Request,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
) -> ExternalTrustAnchorResponse:
    """Retrieve the stored External Trust Anchor for a device (P5.11).

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        trust_service: Injected DevicePassportTrustService.

    Returns:
        An :class:`ExternalTrustAnchorResponse`.
    """
    req_id = request.headers.get("X-Request-ID")
    anchor = trust_service.get_device_external_anchor(device_id)

    return ExternalTrustAnchorResponse(
        success=True,
        anchor=ExternalTrustAnchorPayload(
            external_anchor_id=anchor.external_anchor_id,
            device_id=anchor.device_id,
            passport_fingerprint=anchor.passport_fingerprint,
            algorithm=anchor.algorithm,
            provider=anchor.provider,
            network=anchor.network,
            transaction_id=anchor.transaction_id,
            anchored_at=anchor.anchored_at,
            status=anchor.status,
            metadata=anchor.metadata,
        ),
        is_new=False,
        request_id=req_id,
    )


@router.get(
    "/{device_id}/passport/external-anchor/verify",
    response_model=ExternalTrustVerificationResponse,
)
def verify_device_passport_external(
    request: Request,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
) -> ExternalTrustVerificationResponse:
    """Verify the current passport against the external blockchain ledger (P5.11).

    Strictly read-only: does not modify device, passport, local anchor, or external anchor.
    Guarantees zero database writes, zero mutations, and zero audit event emissions.

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        trust_service: Injected DevicePassportTrustService.

    Returns:
        An :class:`ExternalTrustVerificationResponse`.
    """
    req_id = request.headers.get("X-Request-ID")
    result = trust_service.verify_device_passport_external(device_id)

    return ExternalTrustVerificationResponse(
        success=True,
        verification=ExternalTrustVerificationPayload(
            device_id=result.device_id,
            status=result.status.value,
            stored_fingerprint=result.stored_fingerprint,
            current_fingerprint=result.current_fingerprint,
            algorithm=result.algorithm,
            provider=result.provider,
            network=result.network,
            transaction_id=result.transaction_id,
            anchored_at=result.anchored_at,
            verified_at=result.verified_at,
            message=result.message,
            details=result.details,
        ),
        request_id=req_id,
    )


@router.get("/{device_id}/trust/full", response_model=FullDeviceTrustStatusResponse)
def get_full_device_trust_status(
    request: Request,
    device_id: str,
    trust_service: Annotated[DevicePassportTrustService, Depends(get_trust_service)],
) -> FullDeviceTrustStatusResponse:
    """Retrieve synthesized full device trust status across both Local Operational Trust and External Blockchain Trust (P5.11).

    Strictly read-only: performs zero mutations, zero writes, and emits zero events.

    Args:
        request: Active HTTP request.
        device_id: Public device identifier.
        trust_service: Injected DevicePassportTrustService.

    Returns:
        A :class:`FullDeviceTrustStatusResponse`.
    """
    req_id = request.headers.get("X-Request-ID")
    result = trust_service.get_full_device_trust_status(device_id)

    return FullDeviceTrustStatusResponse(
        success=True,
        trust=FullTrustComparisonPayload(
            device_id=result.device_id,
            local_status=result.local_status,
            external_status=result.external_status,
            overall_status=result.overall_status,
            passport_fingerprint=result.passport_fingerprint,
            local_anchored_fingerprint=result.local_anchored_fingerprint,
            external_anchored_fingerprint=result.external_anchored_fingerprint,
            local_anchor_id=result.local_anchor_id,
            external_anchor_id=result.external_anchor_id,
            transaction_id=result.transaction_id,
            provider=result.provider,
            network=result.network,
            evaluated_at=result.evaluated_at,
            reason=result.reason,
            local_trust_details=result.local_trust_details,
            external_trust_details=result.external_trust_details,
        ),
        request_id=req_id,
    )
