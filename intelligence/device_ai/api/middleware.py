"""FastAPI middleware.

Provides the request-scoped observability required by the milestone: every
request is assigned a ``request_id`` and logged with its latency, image
count and response status. The ``request_id`` is bound into the Loguru
context so all logs emitted while handling the request carry it, and is
echoed back to the client via the ``X-Request-ID`` header.
"""

from __future__ import annotations

import time

from loguru import logger
from starlette.requests import Request
from starlette.types import ASGIApp

from ..utils.hashing import new_request_id

# Header used to surface the correlation id to clients and accept an
# upstream-provided id (e.g. from the backend) when present.
_REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware:
    """ASGI middleware that adds request-id and latency logging.

    Implemented at the raw ASGI level (rather than ``BaseHTTPMiddleware``) so
    it composes cleanly and adds minimal overhead.

    Args:
        app: The wrapped ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        """Handle one ASGI event, adding request-id and latency logging."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        request_id = request.headers.get(_REQUEST_ID_HEADER) or new_request_id()
        # Inject the (possibly generated) id into the request scope headers so
        # downstream handlers — including exception handlers building the error
        # envelope — read the same value echoed back to the client.
        header_key = _REQUEST_ID_HEADER.lower().encode()
        scope_headers = [(k, v) for k, v in scope.get("headers", []) if k != header_key]
        scope_headers.append((header_key, request_id.encode()))
        scope["headers"] = scope_headers

        start = time.perf_counter()

        # Capture the response status as it is emitted so we can log it.
        status_holder: dict[str, int] = {"status": 0}

        async def send_wrapper(message) -> None:  # noqa: ANN001
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((_REQUEST_ID_HEADER.encode(), request_id.encode()))
            await send(message)

        with logger.contextualize(request_id=request_id):
            logger.bind(method=request.method, path=request.url.path).info(
                "Request received"
            )
            try:
                await self._app(scope, receive, send_wrapper)
            finally:
                latency_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.bind(
                    latency_ms=latency_ms,
                    response_status=status_holder["status"],
                    method=request.method,
                    path=request.url.path,
                ).info("Request completed")
