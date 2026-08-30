"""FastAPI dependency providers.

Centralises construction of the settings, validator, model registry and
prediction pipeline so routes receive ready-to-use collaborators via
``Depends`` (dependency injection). The heavy, stateless singletons
(pipeline, registry) are cached for the process lifetime; request-scoped
helpers (validator) are cheap to build per call.
"""

from __future__ import annotations

from datetime import UTC
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from loguru import logger

from ..configs.settings import Settings, get_settings
from ..dataset.service import DatasetService
from ..fingerprint.repository import (
    FingerprintRepository,
    InMemoryFingerprintRepository,
    JsonFileFingerprintRepository,
)
from ..fingerprint.service import FingerprintService
from ..fingerprint.verification import VerificationEngine
from ..devices.repository import (
    DeviceRepository,
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from ..devices.postgres_repository import PostgresDeviceRepository
from ..devices.postgres_trust_anchor_repository import PostgresTrustAnchorRepository
from ..devices.postgres_external_trust_repository import PostgresExternalTrustAnchorRepository
from ..devices.external_trust import (
    ExternalTrustLedger,
    FabricExternalTrustLedger,
    InMemoryExternalTrustLedger,
)
from ..devices.service import DeviceRegistrationService
from ..devices.enrichment_service import DeviceIntelligenceService
from ..devices.trust_anchor import (
    DevicePassportTrustService,
    InMemoryTrustAnchorRepository,
    TrustAnchorPolicy,
    TrustAnchorRepository,
)
from ..database.database import dispose_engines, get_engine
from ..database.session import get_session_factory
from ..inference.clip_encoder import CLIPEncoder
from ..inference.ecoid import EcoIDGenerator
from ..inference.pipeline import (
    PredictionPipeline,
    build_detection_pipeline,
    build_mock_pipeline,
)
from ..inference.predictor import EmbeddingEncoder, MockEmbeddingEncoder
from ..inference.registry import ModelRegistry
from ..inference.ensemble_detector import EnsembleDetector
from ..inference.yolo_detector import YOLODetector
from ..ocr.backends import EasyOCRBackend, MockOCRBackend, OCRBackend
from ..ocr.barcode import BarcodeReader, MockBarcodeReader, OpenCVBarcodeReader
from ..ocr.parser import OCRParser
from ..ocr.service import OCRService
from ..preprocessing.validator import ImageValidator


@lru_cache(maxsize=1)
def get_pipeline() -> PredictionPipeline:
    """Return the process-wide prediction pipeline singleton.

    Selects the detector implementation based on ``INFERENCE_MODE``:

    * ``single_model`` — :class:`YOLODetector` backed by the P4.4.2 reference.
    * ``ensemble`` — :class:`EnsembleDetector` fusing P4.11 + P4.12 via WBF.

    Either way the API response schema is identical, so switching modes is
    transparent to clients.

    Returns:
        The shared :class:`PredictionPipeline`.
    """
    settings = get_settings()

    if settings.inference_mode == "ensemble":
        detector = _build_ensemble_detector(settings)
    else:
        detector = _build_detector(settings)

    if detector is not None and detector.is_ready:
        mode_label = (
            "WBF ensemble (P4.11 + P4.12)"
            if settings.inference_mode == "ensemble"
            else "single YOLO detector"
        )
        logger.info("Serving predictions with the {}.", mode_label)
        return build_detection_pipeline(
            detector=detector,
            model_version=settings.model_version,
            year=_current_year(),
        )
    logger.info("Detector artifact unavailable; serving the mock pipeline.")
    return build_mock_pipeline(
        model_version=settings.model_version,
        year=_current_year(),
    )


def _build_detector(settings: Settings) -> YOLODetector | None:
    """Build a :class:`YOLODetector` from settings, or ``None`` on failure.

    The configured ``detector_weights`` locator is resolved relative to
    ``model_dir`` when not absolute. Construction never raises: any failure to
    locate/load the artifact leaves the detector not-ready and the caller falls
    back to the mock pipeline.

    Args:
        settings: The active application settings.

    Returns:
        A (possibly not-ready) :class:`YOLODetector`, or ``None`` if even
        construction failed.
    """
    weights = Path(settings.detector_weights)
    if not weights.is_absolute():
        weights = settings.model_dir / weights
    try:
        return YOLODetector(
            weights_path=weights,
            image_size=settings.detector_image_size,
            confidence_threshold=settings.detector_confidence_threshold,
        )
    except Exception as exc:  # noqa: BLE001 - degrade to mock on any error
        logger.warning("Could not construct YOLO detector: {}", exc)
        return None


def _build_ensemble_detector(settings: Settings) -> EnsembleDetector | None:
    """Build an :class:`EnsembleDetector` from settings, or ``None`` on failure.

    Model A (P4.11) and Model B (P4.12) weight paths are resolved relative to
    the **repository root** (one level above ``device_ai``) when not absolute.

    Args:
        settings: The active application settings.

    Returns:
        A (possibly not-ready) :class:`EnsembleDetector`, or ``None`` if
        construction failed.
    """
    # Resolve relative paths from the repository root.
    repo_root = Path(__file__).resolve().parents[3]

    model_a_path = Path(settings.ensemble_model_a_weights)
    if not model_a_path.is_absolute():
        model_a_path = repo_root / model_a_path

    model_b_path = Path(settings.ensemble_model_b_weights)
    if not model_b_path.is_absolute():
        model_b_path = repo_root / model_b_path

    try:
        return EnsembleDetector(
            model_a_path=model_a_path,
            model_b_path=model_b_path,
            weights=(settings.ensemble_weights_a, settings.ensemble_weights_b),
            use_tta=settings.ensemble_use_tta,
            iou_threshold=settings.ensemble_iou_threshold,
            image_size=settings.ensemble_image_size,
            confidence_threshold=settings.ensemble_confidence_threshold,
        )
    except Exception as exc:  # noqa: BLE001 - degrade to mock on any error
        logger.warning("Could not construct ensemble detector: {}", exc)
        return None


@lru_cache(maxsize=1)
def get_registry() -> ModelRegistry:
    """Return the process-wide model registry singleton.

    Returns:
        The shared :class:`ModelRegistry` bound to the configured model dir.
    """
    return ModelRegistry(get_settings().model_dir)


def get_validator(
    settings: Settings | None = None,
) -> ImageValidator:
    """Return an :class:`ImageValidator` bound to the active settings.

    Args:
        settings: Optional explicit settings (used by tests). Defaults to the
            process settings singleton.

    Returns:
        A configured :class:`ImageValidator`.
    """
    return ImageValidator(settings or get_settings())


def get_dataset_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DatasetService:
    """Return a :class:`DatasetService` bound to the active settings.

    Built per request (it is cheap and holds no heavy state) so that
    settings overrides — including the ``dataset_dir`` used by tests — are
    always observed.

    The ``settings`` collaborator is resolved through FastAPI's dependency
    graph (``Depends(get_settings)``) rather than declared as a plain
    ``Settings`` default. A bare Pydantic-model parameter would be mistaken
    by FastAPI for a second request-body field, forcing JSON bodies to embed
    under ``payload`` and breaking every POST route. Tests may still call
    this factory directly with an explicit ``settings`` positional argument.

    Args:
        settings: The active settings (injected; defaults to the process
            settings singleton via :func:`get_settings`).

    Returns:
        A configured :class:`DatasetService`.
    """
    return DatasetService(settings)


@lru_cache(maxsize=1)
def get_fingerprint_encoder() -> EmbeddingEncoder:
    """Return the process-wide embedding encoder singleton.

    A real :class:`~device_ai.inference.clip_encoder.CLIPEncoder` is wired in
    when its artifact resolves and the OpenCLIP backend is available; otherwise
    the service degrades to the deterministic
    :class:`~device_ai.inference.predictor.MockEmbeddingEncoder`. Either way the
    fingerprint contract is identical, so swapping models is transparent to
    clients (mirrors :func:`get_pipeline`).

    Returns:
        The shared :class:`EmbeddingEncoder`.
    """
    settings = get_settings()
    encoder = _build_clip_encoder(settings)
    if encoder is not None and encoder.is_ready:
        logger.info("Serving fingerprints with the real OpenCLIP encoder.")
        return encoder
    logger.info("OpenCLIP encoder unavailable; serving the mock encoder.")
    return MockEmbeddingEncoder()


def _build_clip_encoder(settings: Settings) -> CLIPEncoder | None:
    """Build a :class:`CLIPEncoder` from settings, or ``None`` on failure.

    The configured ``clip_weights`` locator is resolved relative to
    ``model_dir`` when not absolute. Construction never raises: any failure to
    locate/load the artifact leaves the encoder not-ready and the caller falls
    back to the mock encoder.

    Args:
        settings: The active application settings.

    Returns:
        A (possibly not-ready) :class:`CLIPEncoder`, or ``None`` if even
        construction failed.
    """
    weights = Path(settings.clip_weights)
    if not weights.is_absolute():
        weights = settings.model_dir / weights
    try:
        return CLIPEncoder(
            weights_path=weights,
            model_name=settings.clip_model_name,
            pretrained=settings.clip_pretrained,
        )
    except Exception as exc:  # noqa: BLE001 - degrade to mock on any error
        logger.warning("Could not construct OpenCLIP encoder: {}", exc)
        return None


@lru_cache(maxsize=1)
def get_fingerprint_repository() -> FingerprintRepository:
    """Return the process-wide fingerprint repository singleton.

    The backend is selected by ``fingerprint_backend``: ``"json"`` persists one
    record per EcoID under ``fingerprint_store_dir``; ``"memory"`` (default)
    keeps records process-locally. Cached so an in-memory store survives across
    requests within a process.

    Returns:
        The shared :class:`FingerprintRepository`.
    """
    settings = get_settings()
    if settings.fingerprint_backend == "json":
        return JsonFileFingerprintRepository(settings.fingerprint_store_dir)
    return InMemoryFingerprintRepository()


def get_fingerprint_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> FingerprintService:
    """Return a :class:`FingerprintService` wired from the active settings.

    Built per request (it is cheap and holds no heavy state beyond its injected
    singletons) so settings overrides — including the metric/threshold used by
    tests — are always observed. The encoder and repository come from cached
    singletons; the verifier and EcoID generator are constructed from settings.

    Like :func:`get_dataset_service`, ``settings`` is resolved through FastAPI's
    dependency graph rather than declared as a plain ``Settings`` default, so
    FastAPI does not mistake it for a request-body field.

    Args:
        settings: The active settings (injected; defaults to the process
            settings singleton via :func:`get_settings`).

    Returns:
        A configured :class:`FingerprintService`.
    """
    verifier = VerificationEngine(
        threshold=settings.fingerprint_match_threshold,
        metric=settings.fingerprint_metric,
    )
    return FingerprintService(
        encoder=get_fingerprint_encoder(),
        repository=get_fingerprint_repository(),
        ecoid_generator=EcoIDGenerator(year=_current_year()),
        verifier=verifier,
    )


@lru_cache(maxsize=1)
def get_ocr_backend() -> OCRBackend:
    """Return the process-wide OCR recognition backend singleton.

    A real :class:`~device_ai.ocr.backends.EasyOCRBackend` is wired in when the
    ``ocr_backend`` setting selects ``easyocr`` and the reader loads (its
    optional dependency and weights are present); otherwise the service degrades
    to the deterministic :class:`~device_ai.ocr.backends.MockOCRBackend`. Either
    way the OCR contract is identical, so swapping backends is transparent to
    clients (mirrors :func:`get_fingerprint_encoder`).

    Returns:
        The shared :class:`~device_ai.ocr.backends.OCRBackend`.
    """
    settings = get_settings()
    if settings.ocr_backend == "easyocr":
        backend = _build_easyocr_backend(settings)
        if backend is not None and backend.is_ready:
            logger.info("Serving OCR with the real EasyOCR backend.")
            return backend
        logger.info("EasyOCR backend unavailable; serving the mock OCR backend.")
    return MockOCRBackend()


def _build_easyocr_backend(settings: Settings) -> EasyOCRBackend | None:
    """Build an :class:`EasyOCRBackend` from settings, or ``None`` on failure.

    The configured ``ocr_weights`` locator is resolved relative to ``model_dir``
    when not absolute. Construction never raises: any failure to locate/load the
    reader leaves the backend not-ready and the caller falls back to the mock.

    Args:
        settings: The active application settings.

    Returns:
        A (possibly not-ready) :class:`EasyOCRBackend`, or ``None`` if even
        construction failed.
    """
    weights = Path(settings.ocr_weights)
    if not weights.is_absolute():
        weights = settings.model_dir / weights
    try:
        return EasyOCRBackend(
            languages=settings.ocr_languages,
            weights_path=weights,
            use_gpu=settings.ocr_use_gpu,
            min_confidence=settings.ocr_min_confidence,
        )
    except Exception as exc:  # noqa: BLE001 - degrade to mock on any error
        logger.warning("Could not construct EasyOCR backend: {}", exc)
        return None


@lru_cache(maxsize=1)
def get_barcode_reader() -> BarcodeReader:
    """Return the process-wide barcode/QR reader singleton.

    A real :class:`~device_ai.ocr.barcode.OpenCVBarcodeReader` is wired in when
    the OpenCV backend is available; otherwise the service degrades to the
    deterministic :class:`~device_ai.ocr.barcode.MockBarcodeReader`.

    Returns:
        The shared :class:`~device_ai.ocr.barcode.BarcodeReader`.
    """
    reader = OpenCVBarcodeReader()
    if reader.is_ready:
        logger.info("Serving barcode decoding with the real OpenCV reader.")
        return reader
    logger.info("OpenCV reader unavailable; serving the mock barcode reader.")
    return MockBarcodeReader()


def get_ocr_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> OCRService:
    """Return an :class:`OCRService` wired from the active settings.

    Built per request (it is cheap and holds no heavy state beyond its injected
    singletons) so settings overrides are always observed. The backend and
    barcode reader come from cached singletons; the barcode reader is attached
    only when ``barcode_enabled`` is set.

    Like :func:`get_fingerprint_service`, ``settings`` is resolved through
    FastAPI's dependency graph rather than declared as a plain ``Settings``
    default, so FastAPI does not mistake it for a request-body field.

    Args:
        settings: The active settings (injected; defaults to the process
            settings singleton via :func:`get_settings`).

    Returns:
        A configured :class:`OCRService`.
    """
    barcode_reader = get_barcode_reader() if settings.barcode_enabled else None
    return OCRService(
        backend=get_ocr_backend(),
        parser=OCRParser(),
        barcode_reader=barcode_reader,
    )


def build_device_repository(settings: Settings) -> DeviceRepository:
    """Construct a :class:`DeviceRepository` from the provided settings.

    Args:
        settings: Application settings.

    Returns:
        The configured :class:`DeviceRepository`.
    """
    if settings.device_backend == "postgres":
        db_url = settings.database_url or "postgresql+psycopg://ecotrace:ecotrace123@localhost:5432/ecotrace"
        engine = get_engine(
            db_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            echo=settings.db_echo,
        )
        session_factory = get_session_factory(engine)
        return PostgresDeviceRepository(session_factory)

    if settings.device_backend == "json":
        store_dir = settings.device_store_dir
        if not store_dir.is_absolute():
            store_dir = Path(__file__).resolve().parents[1] / store_dir
        return JsonFileDeviceRepository(store_dir)

    return InMemoryDeviceRepository()


@lru_cache(maxsize=1)
def get_device_repository() -> DeviceRepository:
    """Return the process-wide :class:`DeviceRepository` singleton.

    Selects the backend from ``device_backend``:
    - ``memory``: Process-local dict store (default, test friendly).
    - ``json``: Durable filesystem store under ``device_store_dir``.
    - ``postgres``: Production PostgreSQL relational store via SQLAlchemy.

    Returns:
        The configured :class:`DeviceRepository`.
    """
    return build_device_repository(get_settings())


def get_device_service(
    repository: Annotated[DeviceRepository, Depends(get_device_repository)],
    pipeline: Annotated[PredictionPipeline, Depends(get_pipeline)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeviceRegistrationService:
    """Return a :class:`DeviceRegistrationService` wired with dependencies.

    Args:
        repository: Injected device repository.
        pipeline: Injected prediction pipeline.
        settings: Injected active application settings.

    Returns:
        A configured :class:`DeviceRegistrationService`.
    """
    return DeviceRegistrationService(
        repository=repository,
        pipeline=pipeline,
        settings=settings,
    )


def get_device_intelligence_service(
    repository: Annotated[DeviceRepository, Depends(get_device_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeviceIntelligenceService:
    """Return a :class:`DeviceIntelligenceService` wired with repository and settings.

    Args:
        repository: Injected device repository.
        settings: Injected active application settings.

    Returns:
        A configured :class:`DeviceIntelligenceService`.
    """
    return DeviceIntelligenceService(
        repository=repository,
        settings=settings,
    )


def build_trust_anchor_repository(settings: Settings) -> TrustAnchorRepository:
    """Construct a :class:`TrustAnchorRepository` from the provided settings.

    Args:
        settings: Application settings.

    Returns:
        The configured :class:`TrustAnchorRepository`.
    """
    if settings.trust_anchor_backend == "postgres":
        db_url = settings.database_url or "postgresql+psycopg://ecotrace:ecotrace123@localhost:5432/ecotrace"
        engine = get_engine(
            db_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            echo=settings.db_echo,
        )
        session_factory = get_session_factory(engine)
        return PostgresTrustAnchorRepository(session_factory)

    return InMemoryTrustAnchorRepository()


@lru_cache(maxsize=1)
def get_trust_anchor_repository() -> TrustAnchorRepository:
    """Return the process-wide :class:`TrustAnchorRepository` singleton.

    Selects the backend from ``trust_anchor_backend``:
    - ``memory``: Process-local dict store (default, test friendly).
    - ``postgres``: Production PostgreSQL relational store via SQLAlchemy.

    Returns:
        The configured :class:`TrustAnchorRepository`.
    """
    return build_trust_anchor_repository(get_settings())


def build_external_trust_ledger(settings: Settings) -> ExternalTrustLedger:
    """Construct an :class:`ExternalTrustLedger` based on application settings.

    Args:
        settings: Active application configuration.

    Returns:
        An instantiated :class:`ExternalTrustLedger`.
    """
    backend = settings.external_trust_backend
    if backend == "fabric":
        logger.info(
            "Configuring FabricExternalTrustLedger (channel='{}', chaincode='{}').",
            settings.external_trust_channel,
            settings.external_trust_chaincode,
        )
        return FabricExternalTrustLedger(
            channel=settings.external_trust_channel,
            chaincode=settings.external_trust_chaincode,
            network=settings.external_trust_network,
            provider=settings.external_trust_provider,
        )

    logger.info("Configuring InMemoryExternalTrustLedger (network='{}').", settings.external_trust_network)
    return InMemoryExternalTrustLedger(
        network=settings.external_trust_network,
        provider=settings.external_trust_backend,
    )


@lru_cache(maxsize=1)
def get_external_trust_ledger() -> ExternalTrustLedger:
    """Return the process-wide :class:`ExternalTrustLedger` singleton."""
    return build_external_trust_ledger(get_settings())


@lru_cache(maxsize=1)
def get_external_trust_repository() -> PostgresExternalTrustAnchorRepository | None:
    """Return the process-wide :class:`PostgresExternalTrustAnchorRepository` singleton if postgres is configured."""
    settings = get_settings()
    if settings.device_backend == "postgres" or settings.trust_anchor_backend == "postgres":
        db_url = settings.database_url or "postgresql+psycopg://ecotrace:ecotrace123@localhost:5432/ecotrace"
        engine = get_engine(
            db_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            echo=settings.db_echo,
        )
        session_factory = get_session_factory(engine)
        return PostgresExternalTrustAnchorRepository(session_factory)
    return None


def get_trust_service(
    device_service: Annotated[DeviceRegistrationService, Depends(get_device_service)],
    anchor_repository: Annotated[TrustAnchorRepository, Depends(get_trust_anchor_repository)],
    external_ledger: Annotated[ExternalTrustLedger, Depends(get_external_trust_ledger)],
    external_repository: Annotated[PostgresExternalTrustAnchorRepository | None, Depends(get_external_trust_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DevicePassportTrustService:
    """Return a :class:`DevicePassportTrustService` wired with dependencies.

    Args:
        device_service: Injected device registration & lifecycle service.
        anchor_repository: Injected local trust anchor repository.
        external_ledger: Injected external blockchain trust ledger provider.
        external_repository: Injected PostgreSQL external anchor repository (if active).
        settings: Injected application settings.

    Returns:
        A configured :class:`DevicePassportTrustService`.
    """
    return DevicePassportTrustService(
        device_service=device_service,
        anchor_repository=anchor_repository,
        policy=TrustAnchorPolicy.STRICT,
        settings=settings,
        external_ledger=external_ledger,
        external_repository=external_repository,
    )


def _current_year() -> int:
    """Return the current four-digit year.

    Isolated in one helper so the (impure) clock read has a single, easily
    overridable call site.

    Returns:
        The current year as an integer.
    """
    from datetime import datetime

    return datetime.now(UTC).year


def reset_dependency_caches() -> None:
    """Clear cached singletons.

    Intended for tests that override settings and need the pipeline/registry/
    encoder/repository/OCR/device/trust singletons rebuilt against the new configuration.
    """
    get_pipeline.cache_clear()
    get_registry.cache_clear()
    get_fingerprint_encoder.cache_clear()
    get_fingerprint_repository.cache_clear()
    get_device_repository.cache_clear()
    get_trust_anchor_repository.cache_clear()
    get_external_trust_ledger.cache_clear()
    get_external_trust_repository.cache_clear()
    get_ocr_backend.cache_clear()
    get_barcode_reader.cache_clear()
    get_settings.cache_clear()
    dispose_engines()
