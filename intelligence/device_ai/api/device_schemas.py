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
