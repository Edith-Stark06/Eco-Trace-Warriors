"""Application factory for the Device Intelligence Engine.

Assembles the FastAPI application: configuration, logging, middleware,
exception handlers and routes. Kept separate from the ``app.py`` entrypoint
so tests can build a fresh app with overridden settings.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from . import __version__
from .api.blockchain_routes import router as blockchain_router
from .api.dataset_routes import router as dataset_router
from .api.dependencies import get_pipeline, get_registry
from .api.device_routes import router as device_router
from .api.errors import register_exception_handlers
from .api.fingerprint_routes import router as fingerprint_router
from .api.middleware import RequestContextMiddleware
from .api.ocr_routes import router as ocr_router
from .api.routes import router
from .configs.logging import configure_logging
from .configs.settings import Settings, get_settings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown: warm singletons and log lifecycle events."""
    settings: Settings = app.state.settings
    logger.info(f"Starting {settings.app_name} v{__version__}")

    # Warm the expensive singletons so the first request is fast and any
    # construction error surfaces at startup rather than mid-request.
    get_pipeline()
    registry = get_registry()
    if not registry.is_available():
        logger.warning(
            f"Model directory '{registry.model_dir}' not found; "
            "running with mock models only."
        )

    yield

    logger.info("Shutting down Device Intelligence Engine")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a FastAPI application instance.

    Args:
        settings: Optional settings override (primarily for tests). When
            omitted, the process settings singleton is used.

    Returns:
        A fully configured :class:`FastAPI` application.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="AI microservice for e-waste device intelligence.",
        lifespan=_lifespan,
    )
    app.state.settings = settings

    # Order matters: the context middleware wraps everything so its
    # request_id is available to handlers and logs.
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(router)
    app.include_router(dataset_router)
    app.include_router(fingerprint_router)
    app.include_router(ocr_router)
    app.include_router(device_router)
    app.include_router(blockchain_router)

    return app
