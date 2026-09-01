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

import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from loguru import logger

from .. import __version__
from ..configs.settings import Settings, get_settings
from ..database.database import get_engine, ping_engine
from ..inference.class_map import CANONICAL_CLASSES, CLASS_NAME_TO_ID
from ..inference.pipeline import PredictionPipeline, PredictionResult
from ..preprocessing.validator import ImageValidator, RawUpload
from ..utils.metrics import get_metrics_registry
from .dependencies import (
    enforce_predict_rate_limit,
    get_pipeline,
    get_registry,
    get_validator,
)
from .schemas import (
    ComponentHealth,
    ConditionPayload,
    DetectionPayload,
    DetectorInfo,
    HealthResponse,
    MetricsResponse,
    ModelInfoResponse,
    OCRPayload,
    PredictionResponse,
    RootResponse,
    TimingPayload,
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
    settings: Annotated[Settings, Depends(get_settings)],
    pipeline: Annotated[PredictionPipeline, Depends(get_pipeline)],
    registry=Depends(get_registry),  # noqa: ANN001 - ModelRegistry
) -> HealthResponse:
    """Return service readiness including per-component status and inference mode.

    Args:
        settings: Injected application settings.
        pipeline: Injected prediction pipeline.
        registry: Injected model registry.

    Returns:
        A :class:`HealthResponse`. Status is ``"healthy"`` when every
        component reports ready, otherwise ``"degraded"``.
    """
    try:
        component_status = pipeline.health()
        components = [
            ComponentHealth(name=name, ready=ready)
            for name, ready in component_status.items()
        ]
        overall = "healthy" if all(component_status.values()) else "degraded"
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Error checking component health: {exc}")
        components = []
        overall = "degraded"

    try:
        model_dir_available = registry.is_available()
    except Exception:  # noqa: BLE001
        model_dir_available = False

    # Database is only a real dependency when a component is actually
    # configured to use Postgres (P7.3) — mirrors the production-safety
    # validator added in P7.2 (configs/settings.py), which applies the same
    # "postgres backend implies DATABASE_URL matters" rule.
    uses_postgres = settings.device_backend == "postgres" or (
        settings.trust_anchor_backend == "postgres"
    )
    if uses_postgres:
        try:
            db_url = (
                settings.database_url
                or "postgresql+psycopg://ecotrace:ecotrace123@localhost:5432/ecotrace"
            )
            engine = get_engine(
                db_url,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=settings.db_pool_timeout,
                echo=settings.db_echo,
            )
            db_ready = ping_engine(engine)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Error checking database health: {exc}")
            db_ready = False
        components.append(ComponentHealth(name="database", ready=db_ready))
        if not db_ready:
            overall = "degraded"

    return HealthResponse(
        status=overall,
        version=__version__,
        components=components,
        model_dir_available=model_dir_available,
        inference_mode=settings.inference_mode,
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


@router.get("/metrics", response_model=MetricsResponse, tags=["meta"])
def metrics() -> MetricsResponse:
    """Return in-process request and Fabric-transaction counters (P7.3).

    Public, read-only, no request body, no authentication — the JSON
    summary contains only aggregate counts/timings per route (method +
    matched route template, never raw URLs, query strings, or bodies), so
    it carries no more sensitive information than ``/health``.

    Returns:
        A :class:`MetricsResponse` wrapping the registry snapshot.
    """
    return MetricsResponse(metrics=get_metrics_registry().snapshot())


@router.get("/model", response_model=ModelInfoResponse, tags=["meta"])
def get_model_info(
    settings: Annotated[Settings, Depends(get_settings)],
    pipeline: Annotated[PredictionPipeline, Depends(get_pipeline)],
) -> ModelInfoResponse:
    """Return active model metadata, inference mode, and canonical class mapping.

    Args:
        settings: Injected application settings.
        pipeline: Injected prediction pipeline.

    Returns:
        A :class:`ModelInfoResponse`.
    """
    detector = pipeline.detector
    detector_info = DetectorInfo(
        name=detector.name,
        version=detector.version,
        ready=detector.is_ready,
    )
    return ModelInfoResponse(
        inference_mode=settings.inference_mode,
        detector=detector_info,
        class_map=CANONICAL_CLASSES,
        model_version=settings.model_version,
    )


@router.post(
    "/predict",
    response_model=PredictionResponse,
    tags=["inference"],
    dependencies=[Depends(enforce_predict_rate_limit)],
)
async def predict(
    request: Request,
    images: Annotated[list[UploadFile], File(description="Device images.")],
    pipeline: Annotated[PredictionPipeline, Depends(get_pipeline)],
    validator: Annotated[ImageValidator, Depends(get_validator)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PredictionResponse:
    """Run the device intelligence prediction pipeline over uploaded images.

    Validates inputs, measures latency per processing stage, logs structured
    metrics, and returns an enriched prediction payload.

    Args:
        request: The active FastAPI HTTP request (for header / request-id access).
        images: One to ``MAX_IMAGES`` multipart image files.
        pipeline: Injected prediction pipeline.
        validator: Injected image validator.
        settings: Injected application settings.

    Returns:
        A :class:`PredictionResponse` with prediction and latency metadata.

    Raises:
        DeviceAIError: Any validation/inference failure, translated to the
            standard error envelope by the registered exception handlers.
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

    result, timing_dict = pipeline.predict_with_timing(loaded)
    t_total_end = time.perf_counter()
    total_ms = round((t_total_end - t_start) * 1000, 2)

    timing = TimingPayload(
        preprocessing_ms=preprocessing_ms,
        inference_ms=timing_dict.get("inference_ms", 0.0),
        postprocessing_ms=timing_dict.get("postprocessing_ms", 0.0),
        total_ms=total_ms,
    )

    detections_payload = [
        DetectionPayload(
            class_id=CLASS_NAME_TO_ID.get(d.label.lower(), -1),
            class_name=d.label,
            confidence=d.confidence,
            bounding_box=d.bounding_box,
        )
        for d in result.detection.detections
    ]

    logger.bind(
        request_id=req_id,
        image_count=len(loaded),
        inference_mode=settings.inference_mode,
        device_type=result.detection.device_type,
        confidence=result.detection.confidence,
        num_detections=len(detections_payload),
        preprocessing_ms=preprocessing_ms,
        inference_ms=timing.inference_ms,
        postprocessing_ms=timing.postprocessing_ms,
        total_ms=total_ms,
        eco_id=result.eco_id,
    ).info("Prediction complete")

    return _to_response(
        result,
        request_id=req_id,
        inference_mode=settings.inference_mode,
        detections=detections_payload,
        timing=timing,
    )


def _to_response(
    result: PredictionResult,
    request_id: str | None = None,
    inference_mode: str = "single_model",
    detections: list[DetectionPayload] | None = None,
    timing: TimingPayload | None = None,
) -> PredictionResponse:
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
        request_id=request_id,
        inference_mode=inference_mode,
        detections=detections if detections is not None else [],
        timing=timing,
    )
