"""Pydantic schemas for the Fabric Gateway blockchain health API (P6.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BlockchainHealthPayload(BaseModel):
    """Read-only Fabric Gateway connectivity evaluation."""

    model_config = ConfigDict(protected_namespaces=())

    status: str = Field(
        description=(
            "One of: disabled, configuration_error, unavailable, connected, healthy."
        )
    )
    fabric_enabled: bool = Field(description="Value of the FABRIC_ENABLED setting.")
    channel: str = Field(description="Configured Fabric channel name.")
    chaincode: str = Field(description="Configured chaincode name (the P6.1 contract).")
    msp_id: str = Field(description="Configured MSP ID of the client identity.")
    peer_endpoint: str = Field(description="Configured Fabric Gateway peer endpoint.")
    message: str = Field(description="Human-readable explanation of the status.")
    checked_at: str = Field(
        description="ISO-8601 UTC timestamp this check was performed."
    )
    latency_ms: float | None = Field(
        default=None,
        description="Connection probe latency in milliseconds, when measured.",
    )


class BlockchainHealthResponse(BaseModel):
    """Response schema for ``GET /system/blockchain/health``."""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=True, description="Query execution status.")
    health: BlockchainHealthPayload = Field(
        description="Fabric Gateway health evaluation."
    )
    request_id: str | None = Field(default=None, description="Correlation request ID.")
