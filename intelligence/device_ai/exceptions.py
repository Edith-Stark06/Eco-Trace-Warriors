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
# Decision knowledge engine errors (milestone M2.1)
# ---------------------------------------------------------------------------


class DecisionError(DeviceAIError):
    """Base class for decision knowledge engine domain errors.

    Like the fusion, recoverability, component, material and environmental
    engines it consumes, the decision knowledge engine is internal-only (no
    endpoints), so these errors are surfaced to the orchestrating code as typed
    exceptions rather than through the HTTP error envelope.
    """

    code = "DECISION_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class DecisionKnowledgeError(DecisionError):
    """Raised when the external decision-knowledge catalogue cannot be loaded.

    The engine reads its per-dimension signal weights, confidence weights and
    normalization constants from an external YAML/JSON file; this error is
    raised when that file is missing, unparseable, or structurally invalid (not
    a mapping, missing required keys, an unknown signal or dimension name, a
    negative weight, an all-zero dimension, a non-positive saturation constant,
    or a missing dimension).
    """

    code = "DECISION_KNOWLEDGE_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Circular decision engine errors (milestone M2.2)
# ---------------------------------------------------------------------------


class CircularDecisionError(DeviceAIError):
    """Base class for circular decision engine domain errors.

    Like the decision-knowledge, fusion, recoverability, component, material
    and environmental engines it consumes, the circular decision engine is
    internal-only (no endpoints), so these errors are surfaced to the
    orchestrating code as typed exceptions rather than through the HTTP error
    envelope.
    """

    code = "CIRCULAR_DECISION_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class CircularRuleError(CircularDecisionError):
    """Raised when the external circular-decision rule catalogue cannot be loaded.

    The engine reads its policy rules from an external YAML/JSON file; this
    error is raised when that file is missing, unparseable, or structurally
    invalid (not a mapping, missing required keys, a duplicate rule id, a
    duplicate precedence, an unknown signal/operator/action/priority name, an
    out-of-range threshold, a rule with no conditions, or a missing default
    fallback).
    """

    code = "CIRCULAR_RULE_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Device passport core errors (milestone M2.3)
# ---------------------------------------------------------------------------


class PassportError(DeviceAIError):
    """Base class for device-passport core domain errors.

    Like the decision-knowledge, circular, fusion, recoverability, component,
    material and environmental engines it composes, the device-passport core is
    internal-only (no endpoints), so these errors are surfaced to the
    orchestrating code as typed exceptions rather than through the HTTP error
    envelope.
    """

    code = "PASSPORT_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class PassportSchemaError(PassportError):
    """Raised when the external device-passport schema cannot be loaded.

    The builder reads the assembled passport's structural contract from an
    external YAML/JSON file; this error is raised when that file is missing,
    unparseable, or structurally invalid (not a mapping, missing a non-empty
    version, a missing/empty required-section list, a non-string section name,
    or a duplicate section).
    """

    code = "PASSPORT_SCHEMA_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class PassportValidationError(PassportError):
    """Raised when an assembled passport violates the external schema contract.

    The strict validator raises this when a built :class:`DevicePassport` (or its
    serialized form) is missing a required section, carries an out-of-range
    confidence, or otherwise fails the shipped schema — so a malformed passport
    never leaves the builder silently.
    """

    code = "PASSPORT_VALIDATION_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Device passport validation & integrity errors (milestone M2.4)
# ---------------------------------------------------------------------------


class PassportIntegrityError(DeviceAIError):
    """Base class for device-passport validation & integrity domain errors.

    Like the device-passport core it consumes, the validation & integrity engine
    is internal-only (no endpoints), so these errors are surfaced to the
    orchestrating code as typed exceptions rather than through the HTTP error
    envelope. They signal an *engine* fault (a malformed rule file, an
    unsupported hash algorithm) — never a passport that merely fails validation,
    which is reported as ordered errors on the produced
    :class:`~device_ai.integrity.models.PassportIntegrityReport` instead.
    """

    code = "PASSPORT_INTEGRITY_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class PassportIntegrityRuleError(PassportIntegrityError):
    """Raised when the external passport validation-rules file cannot be loaded.

    The integrity engine reads the sections, required fields and normalized
    ``[0, 1]`` confidence fields it re-validates a passport against from an
    external YAML/JSON file; this error is raised when that file is missing,
    unparseable, or structurally invalid (not a mapping, missing a non-empty
    version, a missing/empty section list, an unknown section kind, an object
    section with no fields, a duplicate field, or a confidence field absent from
    the section's own fields).
    """

    code = "PASSPORT_INTEGRITY_RULE_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Trust & provenance engine errors (milestone M2.5)
# ---------------------------------------------------------------------------


class PassportTrustError(DeviceAIError):
    """Base class for trust & provenance engine domain errors.

    Like the device-passport core and the validation & integrity engine it
    consumes, the trust engine is internal-only (no endpoints), so these errors
    are surfaced to the orchestrating code as typed exceptions rather than
    through the HTTP error envelope. They signal an *engine* fault (a malformed
    trust catalogue) — never inputs that merely score as low-trust, which are
    reported as a low :class:`~device_ai.trust.models.TrustLevel` and ordered
    warnings on the produced
    :class:`~device_ai.trust.models.PassportTrustReport` instead.
    """

    code = "PASSPORT_TRUST_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class PassportTrustRuleError(PassportTrustError):
    """Raised when the external trust catalogue cannot be loaded.

    The trust engine reads its per-axis blend weights and its ordered
    trust-level thresholds from an external YAML/JSON file; this error is raised
    when that file is missing, unparseable, or structurally invalid (not a
    mapping, missing a non-empty version, missing/empty weights or levels, an
    unknown axis name, a negative or all-zero weight, a non-numeric or
    out-of-range threshold, a duplicate or unknown level name, or levels that do
    not cover the score range).
    """

    code = "PASSPORT_TRUST_RULE_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Blockchain ledger core errors (milestone M3.1)
# ---------------------------------------------------------------------------


class LedgerError(DeviceAIError):
    """Base class for blockchain ledger core domain errors.

    Like the device-passport core, the validation & integrity engine and the
    trust engine it consumes, the ledger core is internal-only (no endpoints),
    so these errors are surfaced to the orchestrating code as typed exceptions
    rather than through the HTTP error envelope. They signal an *engine* fault
    (a malformed config file, an unsupported hash algorithm) — never a chain
    that merely fails verification, which is reported as ``is_valid=False`` on
    the produced :class:`~device_ai.ledger.models.Blockchain` instead.
    """

    code = "LEDGER_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class LedgerConfigError(LedgerError):
    """Raised when the external blockchain-ledger config file cannot be loaded.

    The ledger core reads its hash algorithm, blockchain version and genesis
    sentinel from an external YAML/JSON file; this error is raised when that
    file is missing, unparseable, or structurally invalid (not a mapping, a
    non-string field, an empty hash algorithm, an empty version, or a genesis
    sentinel that is not a hex string).
    """

    code = "LEDGER_CONFIG_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Device lifecycle ledger engine errors (milestone M3.3)
# ---------------------------------------------------------------------------


class LifecycleError(DeviceAIError):
    """Base class for device-lifecycle ledger engine domain errors.

    Like the blockchain ledger core it composes with, the device-lifecycle
    engine is internal-only (no endpoints), so these errors are surfaced to the
    orchestrating code as typed exceptions rather than through the HTTP error
    envelope. They signal an *engine* fault — an empty event sequence with no
    genesis event to anchor on, or an attempt to anchor a lifecycle that failed
    validation — never a lifecycle that merely violates a transition rule, which
    is reported as ``is_valid=False`` on the produced
    :class:`~device_ai.lifecycle.models.LifecycleRecord` instead.
    """

    code = "LIFECYCLE_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class LifecycleRuleError(LifecycleError):
    """Raised when the external lifecycle transition-rules file cannot be loaded.

    The lifecycle engine reads its state machine — the legal event-type
    transitions, the initial (genesis) events and the terminal events — from an
    external YAML/JSON file; this error is raised when that file is missing,
    unparseable, or structurally invalid (not a mapping, a missing/empty
    version, a transitions block that does not declare every lifecycle event
    type exactly once, an unknown event-type name, a duplicate transition
    target, an empty initial-events list, a terminal event that still declares
    outgoing transitions, or a non-terminal event with no outgoing transition).
    """

    code = "LIFECYCLE_RULE_ERROR"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY
