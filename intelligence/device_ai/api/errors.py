"""Exception handlers producing the standard error envelope.

Domain errors (:class:`DeviceAIError`) carry their own stable ``code`` and
``http_status``; they are translated here into the JSON error envelope
defined in :mod:`api.schemas`. Framework validation errors and unexpected
exceptions are also normalised so clients always receive a consistent
shape.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..exceptions import DeviceAIError
from .schemas import ErrorBody, ErrorResponse

# Header carrying the correlation id set by the request-context middleware.
_REQUEST_ID_HEADER = "X-Request-ID"


def _request_id(request: Request) -> str | None:
    """Extract the correlation id for a request, if present."""
    return request.headers.get(_REQUEST_ID_HEADER)


def _envelope(
    *,
    code: str,
    message: str,
    status_code: int,
    request_id: str | None,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    """Build a JSON response using the standard error envelope."""
    payload = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details or {}),
        request_id=request_id,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the application.

    Args:
        app: The FastAPI application to attach handlers to.
    """

    @app.exception_handler(DeviceAIError)
    async def _handle_domain_error(
        request: Request, exc: DeviceAIError
    ) -> JSONResponse:
        logger.bind(code=exc.code).warning(f"Domain error: {exc.message}")
        return _envelope(
            code=exc.code,
            message=exc.message,
            status_code=exc.http_status,
            request_id=_request_id(request),
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("Request validation failed")
        return _envelope(
            code="REQUEST_VALIDATION_ERROR",
            message="Request payload failed validation.",
            status_code=422,
            request_id=_request_id(request),
            details={"errors": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _envelope(
            code="HTTP_ERROR",
            message=str(exc.detail),
            status_code=exc.status_code,
            request_id=_request_id(request),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback server-side but never leak internals to the
        # client (security: no stack traces in responses).
        logger.opt(exception=exc).error("Unhandled exception")
        return _envelope(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            status_code=500,
            request_id=_request_id(request),
        )
