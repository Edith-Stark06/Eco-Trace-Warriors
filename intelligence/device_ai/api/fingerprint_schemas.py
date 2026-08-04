"""Pydantic v2 schemas for the fingerprinting endpoints (milestone M1.5).

These models define the public contract of the ``/fingerprint`` surface. They
convert the fingerprint value objects into serialisable payloads and validate
request bodies at the transport boundary, keeping the domain layer free of
HTTP concerns.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..configs.settings import SimilarityMetricName

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    """Request body for ``POST /fingerprint/compare``."""

    left_eco_id: str = Field(description="EcoID of the first stored fingerprint.")
    right_eco_id: str = Field(description="EcoID of the second stored fingerprint.")
    metric: SimilarityMetricName | None = Field(
        default=None,
        description=(
            "Optional similarity metric override; defaults to the service's "
            "configured metric."
        ),
    )


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class FingerprintResponse(BaseModel):
    """Response body for ``POST /fingerprint/generate`` and ``GET /{eco_id}``.

    Carries the hash-backed fingerprint, the normalized semantic embedding and
    provenance metadata.
    """

    eco_id: str = Field(description="Public EcoID (ET-YYYY-XXXXXXXX).")
    fingerprint: str = Field(
        description="Hash-backed fingerprint (SHA-256 hex of the embedding)."
    )
    embedding: list[float] = Field(
        description="The L2-normalized semantic embedding vector."
    )
    dimension: int = Field(description="Length of the embedding vector.")
    encoder_name: str = Field(description="Name of the encoder that produced it.")
    encoder_version: str = Field(description="Version of that encoder.")
    metric: str = Field(description="Default similarity metric for this fingerprint.")
    created_at: str = Field(description="ISO-8601 UTC creation timestamp.")
    source_hashes: list[str] = Field(
        default_factory=list,
        description="SHA-256 content hashes of the source images (provenance).",
    )
    device_type: str = Field(
        default="", description="Optional device type (reused from detection)."
    )
    brand: str = Field(
        default="", description="Optional brand (reused from detection)."
    )
    identity: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional OCR-derived identity fields (manufacturer/model/serial/"
            "IMEI/MAC), present only when OCR features were supplied (M1.6)."
        ),
    )


class CompareResponse(BaseModel):
    """Response body for ``POST /fingerprint/compare``."""

    left_eco_id: str = Field(description="EcoID of the first fingerprint.")
    right_eco_id: str = Field(description="EcoID of the second fingerprint.")
    metric: str = Field(description="Similarity metric used for the comparison.")
    similarity: float = Field(
        ge=0.0, le=1.0, description="Normalized similarity (1.0 = identical)."
    )
    distance: float = Field(
        ge=0.0, description="Raw geometric distance (lower = more similar)."
    )
    threshold: float = Field(
        ge=0.0, le=1.0, description="Similarity threshold the decision used."
    )
    decision: str = Field(description="Verification decision: 'match' or 'no_match'.")
    is_match: bool = Field(description="Whether the fingerprints were judged a match.")
