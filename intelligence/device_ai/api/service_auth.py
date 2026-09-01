"""Service-to-service authentication middleware (P8.7).

This service has no application-level authentication of its own — the
backend's JWT/RBAC layer never sits in front of it, and in this project's
docker-compose stack its port is reachable both via the internal Compose
network and a host port mapping (developer/demo convenience). Without this
middleware, anyone who can reach the port can drive the entire device
lifecycle — including creating local/external trust anchors — with no
credential at all.

Opt-in and backward-compatible: when ``Settings.service_api_key`` is unset
(the default), every request is allowed, identical to pre-P8.7 behavior —
local dev, ``scripts/demo/run_demo.py``, and the full test suite need no
new configuration. When it is set, every route except the public
health/meta allowlist below requires a matching ``X-Service-Api-Key``
header.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..configs.settings import Settings

SERVICE_API_KEY_HEADER = "X-Service-Api-Key"

# Read-only, non-sensitive endpoints that must stay reachable without a key:
# container healthchecks (`/health`), orchestrator/observability polling
# (`/version`, `/metrics`), the root banner, API docs, and the blockchain
# health probe — the one endpoint the backend's own read-only proxy calls
# (`backend/src/modules/blockchain/blockchain.service.ts`), already public
# on the backend side for the same reason (no sensitive data, no writes).
PUBLIC_PATHS = frozenset(
    {
        "/",
        "/health",
        "/version",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/system/blockchain/health",
    }
)


class ServiceApiKeyMiddleware:
    """ASGI middleware enforcing an optional shared-secret API key.

    Implemented at the raw ASGI level (matching ``RequestContextMiddleware``)
    so it composes cleanly ahead of the router with minimal overhead.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self._app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._settings.service_api_key:
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if request.url.path in PUBLIC_PATHS:
            await self._app(scope, receive, send)
            return

        provided = request.headers.get(SERVICE_API_KEY_HEADER)
        if provided != self._settings.service_api_key:
            response = JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": f"Missing or invalid {SERVICE_API_KEY_HEADER} header.",
                    },
                },
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
