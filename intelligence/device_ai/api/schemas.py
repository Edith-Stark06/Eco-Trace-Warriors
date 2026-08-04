"""Pydantic v2 schemas for API requests and responses.

These models define the public contract of the service. They are the only
place raw pipeline value objects are converted into serialisable payloads,
keeping the transport boundary explicit and validated.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RootResponse(BaseModel):
    """Response body for ``GET /``."""

    service: str = Field(description="Service display name.")
    status: Literal["ok"] = Field(default="ok", description="Liveness flag.")
    version: str = Field(description="Service/API version.")
    docs: str = Field(description="Path to interactive API documentation.")


class ComponentHealth(BaseModel):
    """Readiness of a single model component."""

    name: str = Field(description="Component name.")
    ready: bool = Field(description="Whether the component is ready to serve.")


class HealthResponse(BaseModel):
    """Response body for ``GET /health``."""

    status: Literal["healthy", "degraded"] = Field(
        description="Overall service health."
    )
    version: str = Field(description="Service/API version.")
    components: list[ComponentHealth] = Field(description="Per-component readiness.")
    model_dir_available: bool = Field(
        description="Whether the configured model directory exists."
    )


class VersionResponse(BaseModel):
    """Response body for ``GET /version``."""

    service: str = Field(description="Service display name.")
    version: str = Field(description="Service/API version.")
    model_version: str = Field(description="Model contract version.")
    api: str = Field(description="API contract version tag.")


class ConditionPayload(BaseModel):
    """Condition assessment section of a prediction."""

    label: str = Field(description="Condition class label.")
    score: float = Field(ge=0.0, le=1.0, description="Confidence score.")


class OCRPayload(BaseModel):
    """OCR extraction section of a prediction."""

    serial_number: str = Field(default="", description="Extracted serial.")
    model: str = Field(default="", description="Extracted model identifier.")


class PredictionResponse(BaseModel):
    """Response body for ``POST /predict``.

    Mirrors the milestone reference payload exactly so the backend can rely
    on a stable shape across the mock → real-model transition.
    """

    # ``model_version``/``model_*`` fields would collide with Pydantic's
    # protected ``model_`` namespace; disable the protection explicitly.
    model_config = ConfigDict(protected_namespaces=())

    eco_id: str = Field(description="Public EcoID (ET-YYYY-XXXXXXXX).")
    device_type: str = Field(description="Predicted device type.")
    brand: str = Field(description="Predicted brand/manufacturer.")
    confidence: float = Field(ge=0.0, le=1.0, description="Device-type confidence.")
    condition: ConditionPayload = Field(description="Condition assessment.")
    ocr: OCRPayload = Field(description="Extracted text fields.")
    materials: dict[str, float] = Field(
        description="Recoverable material composition (fractions)."
    )
    carbon_score: float = Field(
        ge=0.0, le=100.0, description="Derived carbon-recovery score."
    )
    embedding_id: str = Field(description="Reference to the visual embedding.")
    model_version: str = Field(description="Model/service version tag.")


class ErrorBody(BaseModel):
    """Inner body of the standard error envelope."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable error description.")
    details: dict[str, object] = Field(
        default_factory=dict, description="Optional structured context."
    )


class ErrorResponse(BaseModel):
    """Standard error envelope returned for all handled failures."""

    success: Literal[False] = Field(
        default=False, description="Always false for errors."
    )
    error: ErrorBody = Field(description="Error detail.")
    request_id: str | None = Field(
        default=None, description="Correlating request identifier."
    )
