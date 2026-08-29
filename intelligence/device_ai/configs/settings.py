"""Application settings for the Device Intelligence Engine.

Configuration is parsed **once** at startup from environment variables
(optionally a local ``.env`` file) using ``pydantic-settings`` and then
injected where needed. No module should read ``os.environ`` directly
(``docs/engineering/08_AI.md`` → Coding Standards).

Environment variables
---------------------
``HOST``            Interface the server binds to.
``PORT``            TCP port the server listens on.
``MODEL_DIR``       Root directory holding versioned model artifacts.
``UPLOAD_DIR``      Directory for transient upload persistence (optional use).
``DATASET_DIR``     Root directory holding the managed dataset sub-folders.
``ARTIFACT_DIR``    Root directory holding training artifacts (M1.3).
``MLRUNS_DIR``      Root directory holding experiment-tracking runs (M1.3).
``EXPERIMENT_TRACKER`` Run-tracking backend (``json``/``mlflow``/``none``).
``DETECTOR_WEIGHTS`` Detector artifact locator (file/dir, relative to MODEL_DIR).
``DETECTOR_IMAGE_SIZE`` Inference image size (px) for the YOLO detector.
``DETECTOR_CONFIDENCE_THRESHOLD`` Minimum kept-detection confidence.
``CLIP_MODEL_NAME``  OpenCLIP architecture name (e.g. ``ViT-B-32``).
``CLIP_PRETRAINED``  OpenCLIP pretrained-weights tag.
``CLIP_WEIGHTS``     CLIP artifact locator (file/dir, relative to MODEL_DIR).
``FINGERPRINT_METRIC`` Default similarity metric (cosine/euclidean/manhattan).
``FINGERPRINT_MATCH_THRESHOLD`` Similarity (0..1) judged a fingerprint match.
``FINGERPRINT_STORE_DIR`` Directory for the JSON fingerprint backend.
``FINGERPRINT_BACKEND`` Fingerprint persistence backend (``memory``/``json``).
``OCR_BACKEND``     OCR recognition backend (``easyocr``/``mock``).
``OCR_LANGUAGES``   Language codes for the EasyOCR reader (e.g. ``["en"]``).
``OCR_WEIGHTS``     OCR model-storage locator (dir, relative to MODEL_DIR).
``OCR_USE_GPU``     Whether to request GPU inference from EasyOCR.
``OCR_MIN_CONFIDENCE`` Minimum kept OCR recognition confidence (0..1).
``BARCODE_ENABLED`` Whether QR/barcode decoding is enabled.
``RECOVERABILITY_REFURBISH_MIN_REUSABILITY`` Reusability floor for refurbishment.
``RECOVERABILITY_REPAIR_MIN_REPAIRABILITY`` Repairability floor for repair.
``RECOVERABILITY_RECYCLE_MIN_RECYCLABILITY`` Recyclability floor for recycling.
``RECOVERABILITY_LOW_CONFIDENCE_THRESHOLD`` Confidence below which review is forced.
``COMPONENT_PROFILES_PATH`` Component-profile library locator (YAML/JSON, relative to the package).
``COMPONENT_MIN_PRESENCE_CONFIDENCE`` Presence confidence below which a component is dropped.
``MATERIAL_PROFILES_PATH`` Material-profile library locator (YAML/JSON, relative to the package).
``MATERIAL_MIN_CONFIDENCE`` Confidence below which a recovered material is dropped.
``ENVIRONMENTAL_FACTORS_PATH`` Conversion-factor catalogue locator (relative to pkg).
``ENVIRONMENTAL_MIN_CONFIDENCE`` Confidence below which a material is ignored.
``MAX_IMAGES``      Maximum number of images accepted per request.
``MAX_FILE_SIZE``   Maximum size, in bytes, of a single uploaded image.
``LOG_LEVEL``       Log verbosity (``DEBUG``/``INFO``/``WARNING``/...).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Media types accepted by the prediction endpoint. Declared here (single
# source of truth) and reused by the validator and the API documentation.
ALLOWED_IMAGE_MIME_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)

# File extensions permitted for uploads, mirroring the MIME allow-list.
ALLOWED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})

# Names of the versioned sub-directories that make up a managed dataset. The
# dataset pipeline (milestone M1.2) resolves each of these relative to
# ``DATASET_DIR`` so no module hardcodes a path.
DATASET_SUBDIRS: tuple[str, ...] = (
    "raw",
    "processed",
    "cleaned",
    "augmented",
    "annotations",
    "labels",
    "metadata",
    "quality",
    "splits",
    "exports",
)

# Names of the sub-directories that make up the training artifact store. The
# training platform (milestone M1.3) resolves each of these relative to
# ``ARTIFACT_DIR`` so no module hardcodes a path.
ARTIFACT_SUBDIRS: tuple[str, ...] = (
    "checkpoints",
    "exports",
    "reports",
)

LogLevel = Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]

# Experiment-tracking backends supported by the training platform (M1.3).
ExperimentTracker = Literal["json", "mlflow", "none"]

# Similarity metrics supported by the fingerprinting engine (M1.5). Kept as a
# string literal (single source of truth) so settings, schemas and the metric
# registry all agree on the accepted values.
SimilarityMetricName = Literal["cosine", "euclidean", "manhattan"]

# Persistence backends for fingerprint records (M1.5).
FingerprintBackend = Literal["memory", "json"]

# OCR recognition backends supported by the OCR Intelligence Engine (M1.6).
# 'easyocr' uses the EasyOCR adapter when the optional dependency and weights
# are present, degrading to not-ready otherwise; 'mock' forces the deterministic
# mock backend (useful in the base environment and tests).
OCRBackendName = Literal["easyocr", "mock"]

# Inference mode for the P5.0 production inference engine. 'single_model'
# uses the P4.4.2 YOLO11n reference; 'ensemble' fuses P4.11 + P4.12 via
# Weighted Box Fusion (P4.13 configuration).
InferenceMode = Literal["single_model", "ensemble"]

# Persistence backends for device registration records (P5.2 & P5.4).
DeviceBackend = Literal["memory", "json", "postgres"]


class Settings(BaseSettings):
    """Strongly-typed application configuration.

    Attributes are populated from environment variables. Field names map to
    upper-cased environment keys (case-insensitive) thanks to the model
    configuration below.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Service identity ------------------------------------------------
    app_name: str = Field(
        default="EcoTrace Device Intelligence Engine",
        description="Human-readable service name.",
    )
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment.",
    )

    # --- Networking ------------------------------------------------------
    host: str = Field(default="0.0.0.0", description="Bind interface.")
    port: int = Field(default=8100, ge=1, le=65535, description="Bind port.")

    # --- Filesystem locations -------------------------------------------
    model_dir: Path = Field(
        default=Path("models"),
        description="Root directory containing versioned model artifacts.",
    )
    upload_dir: Path = Field(
        default=Path("uploads"),
        description="Directory used for optional transient upload persistence.",
    )

    # --- Upload constraints ---------------------------------------------
    max_images: int = Field(
        default=6, ge=1, le=32, description="Maximum images per request."
    )
    min_images: int = Field(default=1, ge=1, description="Minimum images per request.")
    max_file_size: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        description="Maximum size of a single image in bytes.",
    )
    min_image_dimension: int = Field(
        default=32,
        ge=1,
        description="Minimum width/height (px) for a valid image.",
    )
    max_image_dimension: int = Field(
        default=12_000,
        ge=1,
        description="Maximum width/height (px) for a valid image.",
    )

    # --- Observability ---------------------------------------------------
    log_level: LogLevel = Field(default="INFO", description="Log verbosity.")
    json_logs: bool = Field(
        default=False,
        description="Emit machine-readable JSON logs instead of console logs.",
    )

    # --- Model contract --------------------------------------------------
    model_version: str = Field(
        default="1.0.0",
        description="Version tag reported with every prediction.",
    )

    # --- Dataset pipeline (milestone M1.2) -------------------------------
    dataset_dir: Path = Field(
        default=Path("datasets"),
        description="Root directory holding the managed dataset sub-folders.",
    )
    duplicate_hamming_threshold: int = Field(
        default=5,
        ge=0,
        le=64,
        description=(
            "Maximum Hamming distance between perceptual hashes for two "
            "images to be considered near-duplicates."
        ),
    )
    blur_threshold: float = Field(
        default=100.0,
        ge=0.0,
        description=(
            "Variance-of-Laplacian below which an image is flagged as blurry."
        ),
    )
    brightness_dark_threshold: float = Field(
        default=40.0,
        ge=0.0,
        le=255.0,
        description="Mean luminance below which an image is flagged as too dark.",
    )
    brightness_bright_threshold: float = Field(
        default=220.0,
        ge=0.0,
        le=255.0,
        description="Mean luminance above which an image is flagged as too bright.",
    )
    split_ratios: tuple[float, float, float] = Field(
        default=(0.7, 0.2, 0.1),
        description="Default train/validation/test split proportions.",
    )
    split_seed: int = Field(
        default=42,
        ge=0,
        description="Seed for deterministic, reproducible dataset splitting.",
    )

    # --- Training & MLOps platform (milestone M1.3) ----------------------
    artifact_dir: Path = Field(
        default=Path("artifacts"),
        description=(
            "Root directory holding training artifacts (checkpoints, exports, "
            "reports, model registry)."
        ),
    )
    mlruns_dir: Path = Field(
        default=Path("mlruns"),
        description="Root directory holding experiment-tracking run records.",
    )
    experiment_tracker: ExperimentTracker = Field(
        default="json",
        description=(
            "Backend used to record training runs. 'json' writes run records "
            "under MLRUNS_DIR; 'mlflow' delegates to MLflow when installed "
            "(falling back to JSON otherwise); 'none' disables tracking."
        ),
    )
    training_seed: int = Field(
        default=42,
        ge=0,
        description="Seed for deterministic, reproducible training runs.",
    )

    # --- Device detector (milestone M1.4) --------------------------------
    detector_weights: str = Field(
        default="yolov8n.pt",
        description=(
            "Detector artifact locator, resolved relative to MODEL_DIR when "
            "not absolute. May name a file (``model.pt``/``model.onnx``) or a "
            "directory containing one. When the artifact is absent or the "
            "Ultralytics backend is unavailable, the service falls back to the "
            "deterministic mock detector."
        ),
    )
    detector_image_size: int = Field(
        default=640,
        ge=32,
        le=4096,
        description="Inference image size (pixels) forwarded to the YOLO detector.",
    )
    detector_confidence_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for a YOLO detection to be kept.",
    )

    # --- Device fingerprinting (milestone M1.5) --------------------------
    clip_model_name: str = Field(
        default="ViT-B-32",
        description=(
            "OpenCLIP architecture name passed to open_clip.create_model. "
            "Only used when the open-clip-torch backend is installed."
        ),
    )
    clip_pretrained: str = Field(
        default="laion2b_s34b_b79k",
        description=(
            "OpenCLIP pretrained-weights tag. When CLIP_WEIGHTS resolves to a "
            "local artifact, that file is loaded instead of downloading this tag."
        ),
    )
    clip_weights: str = Field(
        default="clip",
        description=(
            "CLIP artifact locator, resolved relative to MODEL_DIR when not "
            "absolute. May name a checkpoint file or a directory containing "
            "one. When absent or the open-clip-torch backend is unavailable, "
            "the service falls back to the deterministic mock encoder."
        ),
    )
    fingerprint_metric: SimilarityMetricName = Field(
        default="cosine",
        description=(
            "Default similarity metric for fingerprint comparison: 'cosine', "
            "'euclidean' or 'manhattan'."
        ),
    )
    fingerprint_match_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description=(
            "Similarity (0..1) at or above which two fingerprints are judged a "
            "match by the verification engine."
        ),
    )
    fingerprint_store_dir: Path = Field(
        default=Path("fingerprints"),
        description=(
            "Directory used by the JSON fingerprint repository backend to "
            "persist one record per EcoID."
        ),
    )
    fingerprint_backend: FingerprintBackend = Field(
        default="memory",
        description=(
            "Persistence backend for fingerprints: 'memory' (process-local, "
            "non-durable) or 'json' (one JSON file per EcoID under "
            "FINGERPRINT_STORE_DIR)."
        ),
    )

    # --- OCR intelligence (milestone M1.6) -------------------------------
    ocr_backend: OCRBackendName = Field(
        default="easyocr",
        description=(
            "OCR recognition backend: 'easyocr' uses the EasyOCR adapter when "
            "the optional dependency and weights are available (auto-degrading "
            "to the deterministic mock when not), 'mock' always uses the mock."
        ),
    )
    ocr_languages: tuple[str, ...] = Field(
        default=("en",),
        description="Language codes passed to the EasyOCR reader (e.g. 'en').",
    )
    ocr_weights: str = Field(
        default="ocr",
        description=(
            "OCR model-storage locator, resolved relative to MODEL_DIR when not "
            "absolute. Names the directory EasyOCR loads its artifacts from. "
            "When absent or the easyocr backend is unavailable, the service "
            "falls back to the deterministic mock OCR backend."
        ),
    )
    ocr_use_gpu: bool = Field(
        default=False,
        description="Whether to request GPU inference from the EasyOCR reader.",
    )
    ocr_min_confidence: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description=(
            "Recognition confidence below which EasyOCR rows are discarded "
            "before parsing."
        ),
    )
    barcode_enabled: bool = Field(
        default=True,
        description=(
            "Whether the OCR engine decodes QR/barcodes alongside text "
            "recognition. When disabled, no barcode reader is attached."
        ),
    )

    # --- Recoverability intelligence (milestone M1.8) ----------------------
    recoverability_refurbish_min_reusability: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description=(
            "Reusability at or above which a non-hazard, confident device is "
            "recommended for refurbishment."
        ),
    )
    recoverability_repair_min_repairability: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description=(
            "Repairability at or above which a non-hazard, confident device is "
            "recommended for repair."
        ),
    )
    recoverability_recycle_min_recyclability: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
        description=(
            "Recyclability at or above which a non-hazard, confident device is "
            "recommended for recycling."
        ),
    )
    recoverability_low_confidence_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description=(
            "Fused confidence below which the recoverability engine forces a "
            "manual review instead of a disposition."
        ),
    )

    # --- Component intelligence (milestone M1.9) ---------------------------
    component_profiles_path: str = Field(
        default="components/data/components.yaml",
        description=(
            "Component-profile library locator. Resolved relative to the "
            "device_ai package root when not absolute. Names the external "
            "YAML (or JSON) file that holds the versioned, per-device-type "
            "component knowledge the engine infers from."
        ),
    )
    component_min_presence_confidence: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description=(
            "Presence confidence at or below which an inferred component is "
            "dropped from the report as too unlikely to be worth listing."
        ),
    )

    # --- Material intelligence (milestone M1.10) ---------------------------
    material_profiles_path: str = Field(
        default="materials/data/materials.yaml",
        description=(
            "Material-profile library locator. Resolved relative to the "
            "device_ai package root when not absolute. Names the external "
            "YAML (or JSON) file that holds the versioned, per-device-type "
            "material knowledge the engine infers recoverable materials from."
        ),
    )
    material_min_confidence: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence at or below which a recovered material is dropped from "
            "the report as too unlikely to be worth listing."
        ),
    )

    # --- Environmental intelligence (milestone M1.11) ----------------------
    environmental_factors_path: str = Field(
        default="environmental/data/factors.yaml",
        description=(
            "Environmental conversion-factor catalogue locator. Resolved "
            "relative to the device_ai package root when not absolute. Names the "
            "external YAML (or JSON) file that holds the versioned, "
            "per-material-category carbon/energy/water factors the engine "
            "converts recovered mass into an avoided burden with."
        ),
    )
    environmental_min_confidence: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence at or below which a recovered material is ignored when "
            "aggregating the environmental savings, as too unlikely to count "
            "toward the avoided burden."
        ),
    )

    # --- P5.0 inference engine (final ML integration) ---------------------
    inference_mode: InferenceMode = Field(
        default="single_model",
        description=(
            "Detector strategy: 'single_model' uses the P4.4.2 YOLO11n "
            "reference checkpoint; 'ensemble' fuses P4.11 YOLO11n + P4.12 "
            "YOLO11s via Weighted Box Fusion (P4.13 E4 configuration)."
        ),
    )
    ensemble_model_a_weights: str = Field(
        default=(
            "dataset_acquisition/training/"
            "p4_11_multisource_targeted_aug_v1/runs/"
            "p411_yolo11n_targeted_aug/weights/best.pt"
        ),
        description=(
            "P4.11 YOLO11n checkpoint for ensemble Model A. Resolved "
            "relative to the repository root when not absolute."
        ),
    )
    ensemble_model_b_weights: str = Field(
        default=(
            "dataset_acquisition/training/"
            "p4_12_model_scale_v1/runs/"
            "p412_yolo11s/weights/best.pt"
        ),
        description=(
            "P4.12 YOLO11s checkpoint for ensemble Model B. Resolved "
            "relative to the repository root when not absolute."
        ),
    )
    ensemble_weights_a: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="WBF fusion weight for Model A (P4.11).",
    )
    ensemble_weights_b: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="WBF fusion weight for Model B (P4.12).",
    )
    ensemble_use_tta: bool = Field(
        default=True,
        description="Enable Test-Time Augmentation for ensemble models.",
    )
    ensemble_iou_threshold: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="IoU threshold for WBF clustering.",
    )
    ensemble_image_size: int = Field(
        default=512,
        ge=32,
        le=4096,
        description="Inference image size (pixels) for ensemble models.",
    )
    ensemble_confidence_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Minimum fused confidence for ensemble detections.",
    )

    # --- Device registration & workflow (P5.2) ----------------------------
    device_backend: DeviceBackend = Field(
        default="memory",
        description="Persistence backend for device records: 'memory' or 'json'.",
    )
    device_store_dir: Path = Field(
        default=Path("devices"),
        description="Directory for JSON device record persistence.",
    )
    confidence_high_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence threshold at or above which a detection is HIGH_CONFIDENCE.",
    )
    confidence_review_threshold: float = Field(
        default=0.40,
        ge=0.0,
        le=1.0,
        description="Confidence threshold at or above which a detection is REVIEW_REQUIRED (below is LOW_CONFIDENCE).",
    )

    # --- Device intelligence enrichment (P5.3) ---------------------------
    material_profile_version: str = Field(
        default="v1.0.0",
        description="Version tag for the deterministic material profile catalogue.",
    )
    carbon_model_version: str = Field(
        default="v1.0.0",
        description="Version tag for the avoided-burden carbon scoring model.",
    )
    carbon_calculation_methodology: str = Field(
        default="avoided_burden_co2e",
        description="Methodological basis for carbon scoring calculation.",
    )

    # --- PostgreSQL Persistence (P5.4) ------------------------------------
    database_url: str | None = Field(
        default=None,
        description="Database connection URL (e.g. postgresql+psycopg://user:pass@host:5432/db).",
    )
    db_pool_size: int = Field(
        default=5,
        ge=1,
        le=50,
        description="SQLAlchemy connection pool size.",
    )
    db_max_overflow: int = Field(
        default=10,
        ge=0,
        le=100,
        description="SQLAlchemy max overflow connections.",
    )
    db_pool_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="SQLAlchemy pool acquisition timeout in seconds.",
    )
    db_echo: bool = Field(
        default=False,
        description="Enable SQLAlchemy query logging.",
    )

    @field_validator("min_images")
    @classmethod
    def _min_not_greater_than_max(cls, value: int, info: ValidationInfo) -> int:
        """Ensure ``min_images`` never exceeds ``max_images``."""
        max_images = info.data.get("max_images")
        if max_images is not None and value > max_images:
            raise ValueError("min_images cannot be greater than max_images")
        return value

    @field_validator("split_ratios")
    @classmethod
    def _ratios_sum_to_one(
        cls, value: tuple[float, float, float]
    ) -> tuple[float, float, float]:
        """Ensure the split ratios are positive and sum to approximately 1.0."""
        if any(part < 0.0 for part in value):
            raise ValueError("split_ratios must be non-negative")
        if abs(sum(value) - 1.0) > 1e-6:
            raise ValueError("split_ratios must sum to 1.0")
        return value

    @property
    def max_file_size_mb(self) -> float:
        """Return the maximum file size expressed in megabytes."""
        return self.max_file_size / (1024 * 1024)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton.

    The result is cached so configuration is parsed exactly once. Tests may
    clear the cache via ``get_settings.cache_clear()`` to inject overrides.

    Returns:
        The application settings instance.
    """
    return Settings()
