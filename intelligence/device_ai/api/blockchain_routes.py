"""Blockchain (Fabric Gateway) system API (P6.2).

Exposes:
- ``GET /system/blockchain/health``: read-only Fabric Gateway connectivity check.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ..configs.settings import Settings, get_settings
from ..devices.fabric_gateway_client import FabricGatewayClient, FabricHealthStatus
from .blockchain_schemas import BlockchainHealthPayload, BlockchainHealthResponse
from .dependencies import get_fabric_gateway_client

router = APIRouter(prefix="/system/blockchain", tags=["blockchain"])


@router.get("/health", response_model=BlockchainHealthResponse)
def get_blockchain_health(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    gateway_client: Annotated[
        FabricGatewayClient | None, Depends(get_fabric_gateway_client)
    ],
) -> BlockchainHealthResponse:
    """Evaluate Fabric Gateway connectivity (P6.2).

    Strictly read-only: performs a connection-level reachability probe only
    (TLS handshake / gRPC channel-ready check against the configured peer).
    Never submits a chaincode transaction, never writes to the database,
    never emits an audit event.

    Args:
        request: Active HTTP request.
        settings: Injected application settings.
        gateway_client: Injected Fabric Gateway client (``None`` when
            ``FABRIC_ENABLED=false``).

    Returns:
        A :class:`BlockchainHealthResponse` describing Fabric connectivity.
    """
    req_id = request.headers.get("X-Request-ID")

    if gateway_client is None:
        result = FabricHealthStatus(
            status="disabled",
            channel=settings.fabric_channel_name,
            chaincode=settings.fabric_chaincode_name,
            msp_id=settings.fabric_msp_id,
            peer_endpoint=settings.fabric_gateway_peer_endpoint,
            message="Fabric Gateway integration is disabled (FABRIC_ENABLED=false).",
        )
    else:
        result = gateway_client.health_check()

    return BlockchainHealthResponse(
        success=True,
        health=BlockchainHealthPayload(
            status=result.status,
            fabric_enabled=settings.fabric_enabled,
            channel=result.channel,
            chaincode=result.chaincode,
            msp_id=result.msp_id,
            peer_endpoint=result.peer_endpoint,
            message=result.message,
            checked_at=result.checked_at,
            latency_ms=result.latency_ms,
        ),
        request_id=req_id,
    )
