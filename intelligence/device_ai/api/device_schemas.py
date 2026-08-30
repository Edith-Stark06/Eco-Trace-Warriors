"""Pydantic schemas for the Device Registration & Intelligence Enrichment API (P5.2 & P5.3)."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from .schemas import TimingPayload


class DeviceRecordPayload(BaseModel):
    """Normalized device record payload."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Unique public device identifier (DEV-YYYY-XXXXXXXX-NN).")
    capture_id: str = Field(description="Correlation capture/session identifier.")
    class_id: int = Field(description="Canonical class ID (0..7).")
    device_type: str = Field(description="Canonical class name (e.g. laptop).")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence score.")
    confidence_state: str = Field(description="Confidence classification (HIGH_CONFIDENCE, REVIEW_REQUIRED, LOW_CONFIDENCE).")
    bounding_box: tuple[int, int, int, int] = Field(description="(x1, y1, x2, y2) pixel coordinates.")
    model_version: str = Field(description="Model/service version tag.")
    inference_mode: str = Field(description="Inference strategy (single_model | ensemble).")
    registration_state: str = Field(description="Lifecycle state (DETECTED, CONFIRMED, REGISTERED).")
    condition: str | None = Field(default=None, description="Assessed condition state.")
    materials: dict[str, float] | None = Field(default=None, description="Recoverable materials breakdown.")
    carbon_score: float | None = Field(default=None, description="Avoided burden carbon score.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Session and diagnostic metadata.")
    created_at: str = Field(description="ISO-8601 creation timestamp.")
    updated_at: str = Field(description="ISO-8601 update timestamp.")


class DeviceRegistrationResponse(BaseModel):
    """Response body for ``POST /devices/register``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Registration operation status.")
    capture_id: str = Field(description="Capture session correlation ID.")
    total_detected: int = Field(description="Number of distinct physical devices detected and created.")
    devices: list[DeviceRecordPayload] = Field(description="List of registered device candidate records.")
    inference_mode: str = Field(description="Inference mode used for registration.")
    timing: TimingPayload = Field(description="Per-stage latency breakdown in milliseconds.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class DeviceStateUpdateResponse(BaseModel):
    """Response body for state transition endpoints (confirm, finalize)."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="State transition status.")
    device: DeviceRecordPayload = Field(description="Updated device record.")
    previous_state: str = Field(description="Lifecycle state before transition.")
    current_state: str = Field(description="Lifecycle state after transition.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class DeviceListResponse(BaseModel):
    """Response body for ``GET /devices``."""

    model_config = ConfigDict(protected_namespaces=())

    total: int = Field(description="Total count of stored devices.")
    devices: list[DeviceRecordPayload] = Field(description="List of retrieved device records.")
    limit: int = Field(description="Page size limit.")
    offset: int = Field(description="Page offset.")


# ---------------------------------------------------------------------------
# P5.3 Enrichment Schemas
# ---------------------------------------------------------------------------


class BrandAssessmentPayload(BaseModel):
    """Brand intelligence assessment payload."""

    model_config = ConfigDict(protected_namespaces=())

    value: str | None = Field(description="Recognized brand name or null if unknown.")
    status: str = Field(description="Brand recognition status ('CONFIRMED' | 'UNKNOWN').")
    source: str = Field(description="Provenance source ('ocr' | 'none').")
    confidence: float | None = Field(default=None, description="OCR recognition confidence.")
    raw_text: str | None = Field(default=None, description="Original matching text span.")


class ConditionAssessmentPayload(BaseModel):
    """Condition intelligence assessment payload."""

    model_config = ConfigDict(protected_namespaces=())

    value: str = Field(description="Condition state (EXCELLENT, GOOD, FAIR, POOR, UNKNOWN).")
    status: str = Field(description="Assessment status ('AVAILABLE' | 'UNAVAILABLE').")
    source: str = Field(description="Provenance source ('pending_assessment', etc.).")
    confidence: float | None = Field(default=None, description="Assessment confidence if available.")
    notes: str = Field(description="Explanatory methodology notes.")


class MaterialItemPayload(BaseModel):
    """Estimated material item payload."""

    model_config = ConfigDict(protected_namespaces=())

    material: str = Field(description="Material component name.")
    category: str = Field(description="Material category (metals, plastics, glass, etc.).")
    mass_g: float = Field(description="Nominal mass in grams.")
    recoverable: bool = Field(description="Whether material is recoverable.")
    hazardous: bool = Field(description="Whether material requires hazardous handling.")
    basis: str = Field(description="Methodological basis ('device_profile').")


class MaterialAssessmentPayload(BaseModel):
    """Material composition intelligence payload."""

    model_config = ConfigDict(protected_namespaces=())

    materials: list[MaterialItemPayload] = Field(description="List of material components.")
    total_mass_g: float = Field(description="Total nominal mass in grams.")
    source: str = Field(description="Provenance source ('device_profile').")
    version: str = Field(description="Catalogue version tag.")
    notes: str = Field(description="Explanatory methodology notes.")


class CarbonAssessmentPayload(BaseModel):
    """Avoided carbon scoring intelligence payload."""

    model_config = ConfigDict(protected_namespaces=())

    carbon_score: float = Field(description="Estimated avoided CO2e in kg.")
    methodology: str = Field(description="Calculation methodology ('avoided_burden_co2e').")
    version: str = Field(description="Model version tag.")
    source: str = Field(description="Provenance source ('estimated_project_model').")
    contributing_factors: dict[str, float] = Field(description="Avoided CO2e breakdown by material category.")
    notes: str = Field(description="Explanatory methodology notes.")


class DeviceIntelligencePayload(BaseModel):
    """Aggregated intelligence enrichment payload."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Target device ID.")
    brand: BrandAssessmentPayload = Field(description="Brand intelligence facet.")
    condition: ConditionAssessmentPayload = Field(description="Condition intelligence facet.")
    materials: MaterialAssessmentPayload = Field(description="Material composition facet.")
    carbon: CarbonAssessmentPayload = Field(description="Carbon avoided burden facet.")
    enriched_at: str = Field(description="ISO-8601 timestamp of enrichment.")


class DeviceEnrichmentRequest(BaseModel):
    """Optional request body for ``POST /devices/{device_id}/enrich``."""

    model_config = ConfigDict(protected_namespaces=())

    ocr_text: str | None = Field(default=None, description="Optional raw OCR text string for brand discovery.")
    ocr_confidence: float | None = Field(default=None, description="Optional OCR confidence score.")
    manual_condition: str | None = Field(default=None, description="Optional manual condition inspection override.")


class DeviceEnrichmentResponse(BaseModel):
    """Response body for ``POST /devices/{device_id}/enrich`` and ``GET /devices/{device_id}/intelligence``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Enrichment operation status.")
    device: DeviceRecordPayload = Field(description="Updated device record.")
    intelligence: DeviceIntelligencePayload = Field(description="Enrichment facets.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class DeviceEventPayload(BaseModel):
    """Schema for an individual audit event."""

    model_config = ConfigDict(protected_namespaces=())

    event_id: str = Field(description="Unique event ID.")
    device_id: str = Field(description="Target device ID.")
    event_type: str = Field(description="Lifecycle event type (e.g. 'DEVICE_DETECTED').")
    timestamp: str = Field(description="ISO-8601 event timestamp.")
    capture_id: str | None = Field(default=None, description="Image capture correlation ID.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Event context metadata.")


class DeviceHistoryResponse(BaseModel):
    """Response schema for device audit history queries (GET /devices/{id}/events)."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Query status.")
    device_id: str = Field(description="Target device identifier.")
    current_state: str = Field(description="Current lifecycle registration state.")
    events: list[DeviceEventPayload] = Field(description="Ordered list of audit events (oldest -> newest).")
    total_events: int = Field(description="Total count of audit events recorded.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class DeviceIdentityPayload(BaseModel):
    """Device identity facet schema."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Public device identifier.")
    eco_id: str | None = Field(default=None, description="EcoTrace identity / correlation ID.")
    device_type: str = Field(description="Canonical device type.")
    class_id: int = Field(description="Canonical class taxonomy ID.")
    capture_id: str = Field(description="Capture session correlation ID.")
    registration_timestamp: str = Field(description="ISO-8601 registration timestamp.")
    created_at: str = Field(description="ISO-8601 record creation timestamp.")
    updated_at: str = Field(description="ISO-8601 record update timestamp.")


class DetectionFacetPayload(BaseModel):
    """Detection facet schema."""

    model_config = ConfigDict(protected_namespaces=())

    confidence: float = Field(description="Detection confidence score.")
    confidence_state: str = Field(description="Confidence classification state.")
    bounding_box: list[int] = Field(description="Pixel bounding box [x1, y1, x2, y2].")
    inference_mode: str = Field(description="Inference strategy (single_model | ensemble).")
    model_version: str = Field(description="Detector model version tag.")


class BrandFacetPayload(BaseModel):
    """Brand intelligence facet schema."""

    model_config = ConfigDict(protected_namespaces=())

    brand: str | None = Field(default=None, description="Canonical brand name.")
    status: str = Field(description="Brand recognition status.")
    source: str = Field(description="Brand provenance source.")
    confidence: float | None = Field(default=None, description="Confidence score.")
    raw_text: str | None = Field(default=None, description="Matched OCR raw text.")


class ConditionFacetPayload(BaseModel):
    """Condition intelligence facet schema."""

    model_config = ConfigDict(protected_namespaces=())

    condition: str | None = Field(default=None, description="Assessed condition state.")
    status: str = Field(description="Condition assessment status.")
    source: str = Field(description="Condition assessment provenance source.")
    notes: str | None = Field(default=None, description="Assessment notes.")


class MaterialFacetPayload(BaseModel):
    """Material composition facet schema."""

    model_config = ConfigDict(protected_namespaces=())

    materials: list[MaterialItemPayload] = Field(default_factory=list, description="Material items breakdown.")
    total_mass_g: float | None = Field(default=None, description="Total nominal mass in grams.")
    source: str = Field(description="Material profile source.")
    version: str | None = Field(default=None, description="Material profile version.")
    notes: str | None = Field(default=None, description="Methodology notes.")


class CarbonFacetPayload(BaseModel):
    """Avoided carbon burden facet schema."""

    model_config = ConfigDict(protected_namespaces=())

    carbon_score: float | None = Field(default=None, description="Estimated avoided CO2e in kg.")
    contributing_factors: dict[str, float] = Field(default_factory=dict, description="CO2e savings breakdown by material category.")
    methodology: str | None = Field(default=None, description="Calculation methodology.")
    source: str = Field(description="Carbon calculation source.")
    version: str | None = Field(default=None, description="Carbon model version.")
    notes: str | None = Field(default=None, description="Methodology notes.")


class LifecycleFacetPayload(BaseModel):
    """Lifecycle registration status facet schema."""

    model_config = ConfigDict(protected_namespaces=())

    current_state: str = Field(description="Current registration state (DETECTED, CONFIRMED, REGISTERED).")
    is_confirmed: bool = Field(description="Whether device is confirmed.")
    is_registered: bool = Field(description="Whether device is finalized and registered.")
    is_enriched: bool = Field(description="Whether intelligence enrichment has been performed.")


class AuditFacetPayload(BaseModel):
    """Audit history facet schema."""

    model_config = ConfigDict(protected_namespaces=())

    total_events: int = Field(description="Total count of audit events.")
    events: list[DeviceEventPayload] = Field(description="Chronological audit events.")


class DevicePassportPayload(BaseModel):
    """Aggregated Device Passport data payload."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Public device identifier.")
    eco_id: str | None = Field(default=None, description="EcoTrace identity / correlation ID.")
    identity: DeviceIdentityPayload = Field(description="Device identity facet.")
    detection: DetectionFacetPayload = Field(description="Detection facet.")
    brand: BrandFacetPayload = Field(description="Brand intelligence facet.")
    condition: ConditionFacetPayload = Field(description="Condition assessment facet.")
    material: MaterialFacetPayload = Field(description="Material composition facet.")
    carbon: CarbonFacetPayload = Field(description="Carbon scoring facet.")
    lifecycle: LifecycleFacetPayload = Field(description="Lifecycle status facet.")
    audit: AuditFacetPayload = Field(description="Chronological audit facet.")
    generated_at: str = Field(description="ISO-8601 timestamp of passport generation.")


class DevicePassportResponse(BaseModel):
    """Response schema for ``GET /devices/{device_id}/passport``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Query status.")
    passport: DevicePassportPayload = Field(description="Aggregated device passport.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class VerificationCheckDetailPayload(BaseModel):
    """Detailed result for a single verification check."""

    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(description="Name of the verification check (e.g. 'identity', 'detection').")
    status: str = Field(description="Check status: PASS, WARNING, FAIL, NOT_APPLICABLE.")
    message: str = Field(description="Human-readable result summary.")
    details: dict[str, Any] = Field(default_factory=dict, description="Structured check diagnostics.")


class PassportVerificationPayload(BaseModel):
    """Payload representing a complete passport verification evaluation."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Public device identifier.")
    verification_status: str = Field(description="Overall verification status: VERIFIED, WARNING, INVALID.")
    passport_fingerprint: str = Field(description="Deterministic SHA-256 fingerprint of the canonical passport.")
    checks: dict[str, str] = Field(description="Summary map of check names to their status string.")
    check_details: list[VerificationCheckDetailPayload] = Field(default_factory=list, description="Granular check details.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings.")
    errors: list[str] = Field(default_factory=list, description="Verification failure errors.")
    verified_at: str = Field(description="ISO-8601 UTC timestamp of verification execution.")


class DevicePassportVerificationResponse(BaseModel):
    """Response schema for ``GET /devices/{device_id}/passport/verify``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Query execution status.")
    verification: PassportVerificationPayload = Field(description="Verification evaluation payload.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class AnchorPassportRequest(BaseModel):
    """Optional request payload for ``POST /devices/{device_id}/passport/anchor``."""

    model_config = ConfigDict(protected_namespaces=())

    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional custom metadata attached to the trust anchor.")


class TrustAnchorPayload(BaseModel):
    """Payload representing an anchored passport fingerprint."""

    model_config = ConfigDict(protected_namespaces=())

    anchor_id: str = Field(description="Unique trust anchor ID.")
    device_id: str = Field(description="Public device identifier.")
    passport_fingerprint: str = Field(description="Cryptographic SHA-256 fingerprint of the canonical passport.")
    algorithm: str = Field(default="sha256", description="Hashing algorithm used for fingerprinting.")
    anchored_at: str = Field(description="ISO-8601 UTC timestamp of anchoring.")
    status: str = Field(default="ANCHORED", description="Anchor lifecycle status: ANCHORED.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Contextual anchor metadata.")


class TrustAnchorResponse(BaseModel):
    """Response schema for ``POST /devices/{device_id}/passport/anchor`` and ``GET /devices/{device_id}/passport/anchor``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Operation status.")
    anchor: TrustAnchorPayload = Field(description="Trust anchor payload.")
    is_new: bool = Field(default=True, description="True if anchor was newly created; False if retrieved / idempotent.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class TrustAnchorVerificationPayload(BaseModel):
    """Payload representing comparison between current passport and anchored trust record."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Public device identifier.")
    status: str = Field(description="Anchor verification status: VERIFIED, MISMATCH, NOT_FOUND.")
    stored_fingerprint: str | None = Field(default=None, description="Stored anchor fingerprint.")
    current_fingerprint: str | None = Field(default=None, description="Recomputed passport fingerprint.")
    algorithm: str = Field(default="sha256", description="Hashing algorithm.")
    verified_at: str = Field(description="ISO-8601 UTC timestamp of verification.")
    message: str = Field(description="Verification outcome message.")
    details: dict[str, Any] = Field(default_factory=dict, description="Diagnostic details.")


class TrustAnchorVerificationResponse(BaseModel):
    """Response schema for ``GET /devices/{device_id}/passport/anchor/verify``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Query execution status.")
    verification: TrustAnchorVerificationPayload = Field(description="Anchor verification evaluation.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class TrustStatusPayload(BaseModel):
    """Payload representing comprehensive canonical device trust evaluation (P5.10)."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Public device identifier.")
    status: str = Field(description="Trust evaluation status: UNANCHORED, ANCHORED, VERIFIED, MISMATCH, STALE.")
    passport_fingerprint: str | None = Field(default=None, description="Current passport SHA-256 fingerprint.")
    anchored_fingerprint: str | None = Field(default=None, description="Stored anchor SHA-256 fingerprint.")
    anchor_id: str | None = Field(default=None, description="Trust anchor record ID.")
    algorithm: str = Field(default="sha256", description="Hash algorithm.")
    anchored_at: str | None = Field(default=None, description="Timestamp when anchor was stored.")
    evaluated_at: str = Field(description="Timestamp when trust status was evaluated.")
    verification_status: str | None = Field(default=None, description="Passport verification status (VERIFIED, WARNING, INVALID).")
    reason: str = Field(description="Explanation of trust status outcome.")
    is_fresh: bool = Field(default=True, description="Whether the anchor is within freshness limit.")
    max_age_days: int | None = Field(default=None, description="Configured max age in days for freshness.")
    age_days: float | None = Field(default=None, description="Current age in days of the anchor.")
    checks: dict[str, str] = Field(default_factory=dict, description="Component-level passport check outcomes.")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional context metadata.")


class DeviceTrustStatusResponse(BaseModel):
    """Response schema for ``GET /devices/{device_id}/trust`` (P5.10)."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Query execution status.")
    trust: TrustStatusPayload = Field(description="Device trust evaluation details.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


# ---------------------------------------------------------------------------
# External / Blockchain Trust Ledger Schemas (P5.11)
# ---------------------------------------------------------------------------


class ExternalTrustAnchorPayload(BaseModel):
    """Payload representing an external / blockchain trust anchor."""

    model_config = ConfigDict(protected_namespaces=())

    external_anchor_id: str = Field(description="Unique external anchor identifier.")
    device_id: str = Field(description="Public device identifier.")
    passport_fingerprint: str = Field(description="Anchored SHA-256 passport fingerprint.")
    algorithm: str = Field(default="sha256", description="Cryptographic hashing algorithm.")
    provider: str = Field(description="External ledger provider (e.g. memory, hyperledger_fabric).")
    network: str = Field(description="Blockchain network or channel identifier.")
    transaction_id: str = Field(description="External transaction reference ID.")
    anchored_at: str = Field(description="ISO-8601 UTC timestamp of anchoring.")
    status: str = Field(default="ANCHORED", description="Anchor record status.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Contextual anchor metadata.")


class ExternalTrustAnchorResponse(BaseModel):
    """Response schema for ``POST /devices/{device_id}/passport/external-anchor`` and ``GET /devices/{device_id}/passport/external-anchor``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Operation status.")
    anchor: ExternalTrustAnchorPayload = Field(description="External trust anchor payload.")
    is_new: bool = Field(default=True, description="True if anchor was newly created; False if retrieved / idempotent.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class ExternalTrustVerificationPayload(BaseModel):
    """Payload representing comparison between current passport and external blockchain anchor."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Public device identifier.")
    status: str = Field(description="External verification status: NOT_ANCHORED, VERIFIED, MISMATCH, UNAVAILABLE, ERROR.")
    stored_fingerprint: str | None = Field(default=None, description="Stored anchor fingerprint on external ledger.")
    current_fingerprint: str | None = Field(default=None, description="Current computed passport fingerprint.")
    algorithm: str = Field(default="sha256", description="Hashing algorithm.")
    provider: str = Field(description="External ledger provider.")
    network: str = Field(description="Blockchain network identifier.")
    transaction_id: str | None = Field(default=None, description="Transaction ID on external ledger.")
    anchored_at: str | None = Field(default=None, description="Anchoring timestamp on external ledger.")
    verified_at: str = Field(description="Timestamp when external verification was evaluated.")
    message: str = Field(description="Explanation of external verification outcome.")
    details: dict[str, Any] = Field(default_factory=dict, description="Diagnostic and provider metadata.")


class ExternalTrustVerificationResponse(BaseModel):
    """Response schema for ``GET /devices/{device_id}/passport/external-anchor/verify``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Query execution status.")
    verification: ExternalTrustVerificationPayload = Field(description="External verification evaluation.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")


class FullTrustComparisonPayload(BaseModel):
    """Payload representing synthesized local and external blockchain trust evaluation (P5.11)."""

    model_config = ConfigDict(protected_namespaces=())

    device_id: str = Field(description="Public device identifier.")
    local_status: str = Field(description="Local operational trust status.")
    external_status: str = Field(description="External ledger trust status.")
    overall_status: str = Field(description="Synthesized aggregate trust status.")
    passport_fingerprint: str | None = Field(default=None, description="Current passport SHA-256 fingerprint.")
    local_anchored_fingerprint: str | None = Field(default=None, description="Fingerprint stored in local PostgreSQL anchor.")
    external_anchored_fingerprint: str | None = Field(default=None, description="Fingerprint stored on external ledger.")
    local_anchor_id: str | None = Field(default=None, description="Local trust anchor ID.")
    external_anchor_id: str | None = Field(default=None, description="External trust anchor ID.")
    transaction_id: str | None = Field(default=None, description="Blockchain transaction ID.")
    provider: str = Field(description="External ledger provider.")
    network: str = Field(description="Blockchain network / channel identifier.")
    evaluated_at: str = Field(description="Evaluation timestamp (UTC).")
    reason: str = Field(description="Summary explanation of synthesized trust status.")
    local_trust_details: dict[str, Any] = Field(default_factory=dict, description="Local trust evaluation details.")
    external_trust_details: dict[str, Any] = Field(default_factory=dict, description="External trust evaluation details.")


class FullDeviceTrustStatusResponse(BaseModel):
    """Response schema for ``GET /devices/{device_id}/trust/full``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Query execution status.")
    trust: FullTrustComparisonPayload = Field(description="Full synthesized device trust status.")
    request_id: str | None = Field(default=None, description="Correlation request ID.")
