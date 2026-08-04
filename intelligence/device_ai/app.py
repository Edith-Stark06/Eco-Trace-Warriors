"""Service entrypoint for the Device Intelligence Engine.

Exposes the module-level ``app`` object used by ASGI servers, e.g.::

    uvicorn device_ai.app:app --host 0.0.0.0 --port 8100

Running this file directly starts Uvicorn using the configured host/port.
"""

from __future__ import annotations

from .application import create_app
from .configs.settings import get_settings

# Module-level ASGI application discovered by Uvicorn/Gunicorn.
app = create_app()


def main() -> None:
    """Run the service with Uvicorn using configured host/port."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "device_ai.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
