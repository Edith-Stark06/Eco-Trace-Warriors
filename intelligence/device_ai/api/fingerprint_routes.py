"""Fingerprinting API routes (milestone M1.5).

Three endpoints make up the ``/fingerprint`` surface:

* ``POST /fingerprint/generate`` — multipart image upload → generate & persist
  a hash-backed fingerprint.
* ``POST /fingerprint/compare``  — verify two stored fingerprints by EcoID.
* ``GET  /fingerprint/{eco_id}`` — fetch a stored fingerprint.

Routes are thin: they validate/convert input, delegate to the injected
:class:`~device_ai.fingerprint.service.FingerprintService`, and serialise the
result. No business logic lives here, and the existing prediction endpoints are
left untouched (this router is mounted under a separate prefix).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from loguru import logger

from ..fingerprint.models import DeviceFingerprint
from ..fingerprint.service import FingerprintService
from ..fingerprint.verification import VerificationResult
from ..preprocessing.validator import ImageValidator, RawUpload
from .dependencies import get_fingerprint_service, get_validator
from .fingerprint_schemas import (
    CompareRequest,
    CompareResponse,
    FingerprintResponse,
)

router = APIRouter(prefix="/fingerprint", tags=["fingerprint"])


@router.post("/generate", response_model=FingerprintResponse)
async def generate_fingerprint(
    images: Annotated[list[UploadFile], File(description="Device images.")],
    service: Annotated[FingerprintService, Depends(get_fingerprint_service)],
    validator: Annotated[ImageValidator, Depends(get_validator)],
    device_type: Annotated[str, Form()] = "",
    brand: Annotated[str, Form()] = "",
) -> FingerprintResponse:
    """Generate and persist a fingerprint for uploaded device images.

    Args:
        images: One to ``MAX_IMAGES`` multipart image files.
        service: Injected fingerprint service.
        validator: Injected image validator.
        device_type: Optional device type recorded for provenance.
        brand: Optional brand recorded for provenance.

    Returns:
        A :class:`FingerprintResponse` for the generated fingerprint.

    Raises:
        DeviceAIError: Any validation/inference failure, translated to the
            standard error envelope by the registered exception handlers.
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
    fingerprint = service.generate(loaded, device_type=device_type, brand=brand)
    logger.bind(eco_id=fingerprint.eco_id).info("Fingerprint generated")
    return _to_fingerprint_response(fingerprint)


@router.post("/compare", response_model=CompareResponse)
def compare_fingerprints(
    payload: CompareRequest,
    service: Annotated[FingerprintService, Depends(get_fingerprint_service)],
) -> CompareResponse:
    """Verify two stored fingerprints against each other.

    Args:
        payload: The compare request (two EcoIDs + optional metric override).
        service: Injected fingerprint service.

    Returns:
        A :class:`CompareResponse` with the similarity and match decision.

    Raises:
        FingerprintNotFoundError: If either EcoID is unknown.
        FingerprintMismatchError: If the fingerprints cannot be compared.
    """
    result = service.compare(
        payload.left_eco_id,
        payload.right_eco_id,
        metric=payload.metric,
    )
    logger.bind(decision=result.decision.value).info("Fingerprint comparison complete")
    return _to_compare_response(result)


@router.get("/{eco_id}", response_model=FingerprintResponse)
def get_fingerprint(
    eco_id: str,
    service: Annotated[FingerprintService, Depends(get_fingerprint_service)],
) -> FingerprintResponse:
    """Return the stored fingerprint for ``eco_id``.

    Args:
        eco_id: The EcoID to look up.
        service: Injected fingerprint service.

    Returns:
        A :class:`FingerprintResponse` for the stored fingerprint.

    Raises:
        FingerprintNotFoundError: If no fingerprint is stored for ``eco_id``.
    """
    fingerprint = service.get(eco_id)
    return _to_fingerprint_response(fingerprint)


def _to_fingerprint_response(fingerprint: DeviceFingerprint) -> FingerprintResponse:
    """Convert a :class:`DeviceFingerprint` into the API schema."""
    return FingerprintResponse(
        eco_id=fingerprint.eco_id,
        fingerprint=fingerprint.fingerprint,
        embedding=list(fingerprint.embedding),
        dimension=fingerprint.dimension,
        encoder_name=fingerprint.encoder_name,
        encoder_version=fingerprint.encoder_version,
        metric=fingerprint.metric,
        created_at=fingerprint.created_at.isoformat(),
        source_hashes=list(fingerprint.source_hashes),
        device_type=fingerprint.device_type,
        brand=fingerprint.brand,
        identity=dict(fingerprint.identity),
    )


def _to_compare_response(result: VerificationResult) -> CompareResponse:
    """Convert a :class:`VerificationResult` into the API schema."""
    return CompareResponse(
        left_eco_id=result.left_eco_id,
        right_eco_id=result.right_eco_id,
        metric=result.metric.value,
        similarity=result.similarity,
        distance=result.distance,
        threshold=result.threshold,
        decision=result.decision.value,
        is_match=result.is_match,
    )
