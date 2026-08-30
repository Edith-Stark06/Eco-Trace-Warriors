"""Domain exception hierarchy for the Device Intelligence Engine.

These exceptions are raised by the preprocessing and inference layers and
translated into the standard HTTP error envelope by the API layer. Keeping
them free of any FastAPI/HTTP imports preserves clean layering: the domain
does not depend on the transport.

Each exception carries a stable ``code`` (machine-readable) and a
``http_status`` hint the API layer uses when building responses.
"""

from __future__ import annotations

from http import HTTPStatus


class DeviceAIError(Exception):
    """Base class for all Device Intelligence Engine domain errors.

    Attributes:
        message: Human-readable description of the error.
        code: Stable machine-readable error code (SCREAMING_SNAKE_CASE).
        http_status: Suggested HTTP status code for the API layer.
        details: Optional structured context for diagnostics.
    """

    code: str = "DEVICE_AI_ERROR"
    http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(DeviceAIError):
    """Raised when a request or its payload fails validation."""

    code = "VALIDATION_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class NoImagesProvidedError(ValidationError):
    """Raised when a prediction request contains no images."""

    code = "NO_IMAGES_PROVIDED"
    http_status = HTTPStatus.BAD_REQUEST


class TooManyImagesError(ValidationError):
    """Raised when a request exceeds the configured image count limit."""

    code = "TOO_MANY_IMAGES"
    http_status = HTTPStatus.BAD_REQUEST


class FileTooLargeError(ValidationError):
    """Raised when an uploaded image exceeds the configured size limit."""

    code = "FILE_TOO_LARGE"
    http_status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE


class UnsupportedMediaTypeError(ValidationError):
    """Raised when an uploaded image has an unsupported MIME type/extension."""

    code = "UNSUPPORTED_MEDIA_TYPE"
    http_status = HTTPStatus.UNSUPPORTED_MEDIA_TYPE


class CorruptedImageError(ValidationError):
    """Raised when an uploaded image cannot be decoded."""

    code = "CORRUPTED_IMAGE"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class ImageDimensionError(ValidationError):
    """Raised when image resolution is outside the accepted bounds."""

    code = "INVALID_IMAGE_DIMENSIONS"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class InferenceError(DeviceAIError):
    """Raised when the inference pipeline fails to produce a prediction."""

    code = "INFERENCE_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class ModelNotLoadedError(InferenceError):
    """Raised when a required model artifact is unavailable."""

    code = "MODEL_NOT_LOADED"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Dataset pipeline errors (milestone M1.2)
# ---------------------------------------------------------------------------


class DatasetError(DeviceAIError):
    """Base class for dataset-pipeline domain errors."""

    code = "DATASET_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class DatasetNotFoundError(DatasetError):
    """Raised when a referenced dataset directory or split does not exist."""

    code = "DATASET_NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND


class EmptyDatasetError(DatasetError):
    """Raised when an operation needs images but the dataset has none."""

    code = "EMPTY_DATASET"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class AnnotationValidationError(DatasetError):
    """Raised when annotation files fail structural or semantic validation."""

    code = "ANNOTATION_VALIDATION_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class UnsupportedExportFormatError(DatasetError):
    """Raised when an unknown/unsupported export format is requested."""

    code = "UNSUPPORTED_EXPORT_FORMAT"
    http_status = HTTPStatus.BAD_REQUEST


class InvalidSplitError(DatasetError):
    """Raised when split ratios are invalid (negative or not summing to 1)."""

    code = "INVALID_SPLIT"
    http_status = HTTPStatus.BAD_REQUEST


# ---------------------------------------------------------------------------
# Training & MLOps platform errors (milestone M1.3)
# ---------------------------------------------------------------------------


class TrainingError(DeviceAIError):
    """Base class for training-platform domain errors."""

    code = "TRAINING_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class ConfigError(TrainingError):
    """Raised when a training configuration is missing, malformed, or invalid."""

    code = "CONFIG_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class TrainerNotFoundError(TrainingError):
    """Raised when a requested trainer name is not registered."""

    code = "TRAINER_NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND


class ExportError(TrainingError):
    """Raised when a model export operation fails."""

    code = "EXPORT_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class ModelRegistryError(TrainingError):
    """Raised when a model-registry lookup or mutation fails."""

    code = "MODEL_REGISTRY_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class ModelNotFoundError(ModelRegistryError):
    """Raised when a referenced model name/version is not in the registry."""

    code = "MODEL_NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND


# ---------------------------------------------------------------------------
# Fingerprinting engine errors (milestone M1.5)
# ---------------------------------------------------------------------------


class FingerprintError(DeviceAIError):
    """Base class for device-fingerprinting domain errors."""

    code = "FINGERPRINT_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class FingerprintNotFoundError(FingerprintError):
    """Raised when no fingerprint exists for a referenced EcoID."""

    code = "FINGERPRINT_NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND


class FingerprintMismatchError(FingerprintError):
    """Raised when two fingerprints cannot be compared.

    Comparison requires matching embedding dimensionality (and, by default,
    the same encoder) so a similarity score is meaningful.
    """

    code = "FINGERPRINT_MISMATCH"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class UnknownSimilarityMetricError(FingerprintError):
    """Raised when an unsupported similarity metric name is requested."""

    code = "UNKNOWN_SIMILARITY_METRIC"
    http_status = HTTPStatus.BAD_REQUEST


class EncoderNotReadyError(FingerprintError):
    """Raised when the embedding encoder has no backend loaded to serve."""

    code = "ENCODER_NOT_READY"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# OCR intelligence engine errors (milestone M1.6)
# ---------------------------------------------------------------------------


class OCRError(DeviceAIError):
    """Base class for OCR Intelligence Engine domain errors."""

    code = "OCR_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class OCRBackendNotReadyError(OCRError):
    """Raised when the OCR recognition backend has no reader loaded to serve."""

    code = "OCR_BACKEND_NOT_READY"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE


class OCRParseError(OCRError):
    """Raised when raw spans/barcodes submitted to the parser are malformed."""

    code = "OCR_PARSE_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Fusion engine errors (milestone M1.7)
# ---------------------------------------------------------------------------


class FusionError(DeviceAIError):
    """Base class for multi-modal fusion engine domain errors.

    The fusion engine is internal-only (no endpoints), so these errors are
    surfaced to the orchestrating code as typed exceptions rather than through
    the HTTP error envelope.
    """

    code = "FUSION_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# Recoverability intelligence engine errors (milestone M1.8)
# ---------------------------------------------------------------------------


class RecoverabilityError(DeviceAIError):
    """Base class for recoverability intelligence engine domain errors.

    Like the fusion engine it consumes, the recoverability engine is
    internal-only (no endpoints), so these errors are surfaced to the
    orchestrating code as typed exceptions rather than through the HTTP error
    envelope.
    """

    code = "RECOVERABILITY_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# Component intelligence engine errors (milestone M1.9)
# ---------------------------------------------------------------------------


class ComponentError(DeviceAIError):
    """Base class for component intelligence engine domain errors.

    Like the fusion and recoverability engines it consumes, the component
    engine is internal-only (no endpoints), so these errors are surfaced to the
    orchestrating code as typed exceptions rather than through the HTTP error
    envelope.
    """

    code = "COMPONENT_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class ComponentProfileError(ComponentError):
    """Raised when the external component-profile library cannot be loaded.

    The engine reads its component knowledge from an external YAML/JSON file;
    this error is raised when that file is missing, unparseable, or structurally
    invalid (not a mapping, missing required keys, out-of-range likelihoods).
    """

    code = "COMPONENT_PROFILE_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Material intelligence engine errors (milestone M1.10)
# ---------------------------------------------------------------------------


class MaterialError(DeviceAIError):
    """Base class for material intelligence engine domain errors.

    Like the fusion, recoverability and component engines it consumes, the
    material engine is internal-only (no endpoints), so these errors are
    surfaced to the orchestrating code as typed exceptions rather than through
    the HTTP error envelope.
    """

    code = "MATERIAL_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class MaterialProfileError(MaterialError):
    """Raised when the external material-profile library cannot be loaded.

    The engine reads its material knowledge from an external YAML/JSON file;
    this error is raised when that file is missing, unparseable, or structurally
    invalid (not a mapping, missing required keys, negative masses, unknown
    material category, or an unknown source-component category).
    """

    code = "MATERIAL_PROFILE_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Environmental intelligence engine errors (milestone M1.11)
# ---------------------------------------------------------------------------


class EnvironmentalError(DeviceAIError):
    """Base class for environmental intelligence engine domain errors.

    Like the fusion, recoverability, component and material engines it consumes,
    the environmental engine is internal-only (no endpoints), so these errors
    are surfaced to the orchestrating code as typed exceptions rather than
    through the HTTP error envelope.
    """

    code = "ENVIRONMENTAL_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class EnvironmentalFactorError(EnvironmentalError):
    """Raised when the external conversion-factor library cannot be loaded.

    The engine reads its conversion factors from an external YAML/JSON file;
    this error is raised when that file is missing, unparseable, or structurally
    invalid (not a mapping, missing required keys, negative or non-numeric
    factors, an unknown material category, or a missing ``default`` fallback).
    """

    code = "ENVIRONMENTAL_FACTOR_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Device registration & lifecycle workflow errors (P5.2)
# ---------------------------------------------------------------------------


class DeviceRegistrationError(DeviceAIError):
    """Base class for device registration and workflow errors."""

    code = "DEVICE_REGISTRATION_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class DeviceNotFoundError(DeviceRegistrationError):
    """Raised when a requested device ID does not exist."""

    code = "DEVICE_NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND


class DuplicateDeviceError(DeviceRegistrationError):
    """Raised when attempting to create a device record with an existing ID."""

    code = "DUPLICATE_DEVICE"
    http_status = HTTPStatus.CONFLICT


class InvalidStateTransitionError(DeviceRegistrationError):
    """Raised when an invalid lifecycle state transition is requested."""

    code = "INVALID_STATE_TRANSITION"
    http_status = HTTPStatus.BAD_REQUEST


class NoDetectionsForRegistrationError(DeviceRegistrationError):
    """Raised when device registration is requested on an image with zero detections."""

    code = "NO_DETECTIONS_FOUND"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class InvalidDeviceClassError(DeviceRegistrationError):
    """Raised when an unrecognized or unsupported device class is encountered."""

    code = "INVALID_DEVICE_CLASS"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class DevicePersistenceError(DeviceRegistrationError):
    """Raised when device record persistence fails."""

    code = "DEVICE_PERSISTENCE_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# Trust Anchor & Blockchain abstraction errors (P5.8)
# ---------------------------------------------------------------------------


class TrustAnchorError(DeviceAIError):
    """Base class for trust anchor and verification errors."""

    code = "TRUST_ANCHOR_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class AnchorNotFoundError(TrustAnchorError):
    """Raised when no trust anchor exists for a requested device."""

    code = "ANCHOR_NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND


class AnchorConflictError(TrustAnchorError):
    """Raised when attempting to anchor a conflicting fingerprint onto an already anchored device."""

    code = "ANCHOR_CONFLICT"
    http_status = HTTPStatus.CONFLICT


class PassportNotAnchorableError(TrustAnchorError):
    """Raised when a passport fails verification and cannot be anchored."""

    code = "PASSPORT_NOT_ANCHORABLE"
    http_status = HTTPStatus.BAD_REQUEST


# ---------------------------------------------------------------------------
# External / Blockchain Trust Ledger errors (P5.11)
# ---------------------------------------------------------------------------


class ExternalLedgerError(TrustAnchorError):
    """Base exception for external/blockchain ledger errors."""

    code = "EXTERNAL_LEDGER_ERROR"
    http_status = HTTPStatus.BAD_GATEWAY


class ExternalLedgerUnavailableError(ExternalLedgerError):
    """Raised when external ledger provider is unreachable or disabled."""

    code = "EXTERNAL_LEDGER_UNAVAILABLE"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE


class ExternalAnchorNotFoundError(ExternalLedgerError):
    """Raised when no external anchor exists on the ledger for the requested device."""

    code = "EXTERNAL_ANCHOR_NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND


class ExternalAnchorConflictError(ExternalLedgerError):
    """Raised when attempting to externally anchor a conflicting fingerprint onto an already anchored device."""

    code = "EXTERNAL_ANCHOR_CONFLICT"
    http_status = HTTPStatus.CONFLICT
