"""API route definitions.

Four endpoints make up the milestone M1.1 surface:

* ``GET  /``        — service metadata / liveness.
* ``GET  /health``  — readiness including per-component status.
* ``GET  /version`` — version information.
* ``POST /predict`` — multipart image upload → mock prediction.

Routes are thin: they validate/convert input, delegate to the injected
pipeline, and serialise the result. No business logic lives here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from loguru import logger

from .. import __version__
from ..configs.settings import Settings, get_settings
from ..inference.pipeline import PredictionPipeline, PredictionResult
from ..preprocessing.validator import ImageValidator, RawUpload
from .dependencies import get_pipeline, get_registry, get_validator
from .schemas import (
    ComponentHealth,
    ConditionPayload,
    HealthResponse,
    OCRPayload,
    PredictionResponse,
    RootResponse,
    VersionResponse,
)

router = APIRouter()

# API contract tag surfaced by /version; bump when the wire shape changes.
_API_CONTRACT = "v1"


@router.get("/", response_model=RootResponse, tags=["meta"])
def read_root(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RootResponse:
    """Return basic service metadata (liveness).

    Args:
        settings: Injected application settings.

    Returns:
        A :class:`RootResponse` with service name and version.
    """
    return RootResponse(
        service=settings.app_name,
        version=__version__,
        docs="/docs",
    )


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health(
    pipeline: Annotated[PredictionPipeline, Depends(get_pipeline)],
    registry=Depends(get_registry),  # noqa: ANN001 - ModelRegistry
) -> HealthResponse:
    """Return service readiness including per-component status.

    Args:
        pipeline: Injected prediction pipeline.
        registry: Injected model registry.

    Returns:
        A :class:`HealthResponse`. Status is ``"healthy"`` when every
        component reports ready, otherwise ``"degraded"``.
    """
    component_status = pipeline.health()
    components = [
        ComponentHealth(name=name, ready=ready)
        for name, ready in component_status.items()
    ]
    overall = "healthy" if all(component_status.values()) else "degraded"
    return HealthResponse(
        status=overall,
        version=__version__,
        components=components,
        model_dir_available=registry.is_available(),
    )


@router.get("/version", response_model=VersionResponse, tags=["meta"])
def version(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VersionResponse:
    """Return version information for the service and model contract.

    Args:
        settings: Injected application settings.

    Returns:
        A :class:`VersionResponse`.
    """
    return VersionResponse(
        service=settings.app_name,
        version=__version__,
        model_version=settings.model_version,
        api=_API_CONTRACT,
    )


@router.post("/predict", response_model=PredictionResponse, tags=["inference"])
async def predict(
    images: Annotated[list[UploadFile], File(description="Device images.")],
    pipeline: Annotated[PredictionPipeline, Depends(get_pipeline)],
    validator: Annotated[ImageValidator, Depends(get_validator)],
) -> PredictionResponse:
    """Run the mock prediction pipeline over uploaded device images.

    Args:
        images: One to ``MAX_IMAGES`` multipart image files.
        pipeline: Injected prediction pipeline.
        validator: Injected image validator.

    Returns:
        A :class:`PredictionResponse` with the aggregated prediction.

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
    logger.bind(image_count=len(loaded)).info("Images validated")

    result = pipeline.predict(loaded)
    logger.bind(eco_id=result.eco_id).info("Prediction complete")

    return _to_response(result)


def _to_response(result: PredictionResult) -> PredictionResponse:
    """Convert a pipeline :class:`PredictionResult` into the API schema."""
    return PredictionResponse(
        eco_id=result.eco_id,
        device_type=result.detection.device_type,
        brand=result.detection.brand,
        confidence=result.detection.confidence,
        condition=ConditionPayload(
            label=result.condition.label,
            score=result.condition.score,
        ),
        ocr=OCRPayload(
            serial_number=result.ocr.serial_number,
            model=result.ocr.model,
        ),
        materials=result.materials.composition,
        carbon_score=result.carbon_score,
        embedding_id=result.embedding.embedding_id,
        model_version=result.model_version,
    )
