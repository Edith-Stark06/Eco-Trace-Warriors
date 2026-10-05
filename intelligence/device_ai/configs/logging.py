"""Structured logging configuration built on Loguru.

The service emits structured logs so that every request can be traced by
its ``request_id`` and correlated with latency, image count and response
status (milestone requirement). Logging is configured once at startup and
never scattered across modules.

Two sinks are supported:

* **Console** (default) — colourised, human-friendly for local development.
* **JSON** — one JSON object per line, suitable for log shippers in
  staging/production. Enable via ``JSON_LOGS=true``.

Standard-library logging (used by Uvicorn/FastAPI) is redirected into
Loguru through :class:`InterceptHandler` so all logs share one format.
"""

from __future__ import annotations

import logging
import sys
from types import FrameType
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger

from .settings import Settings

# Names of the stdlib loggers whose records we intercept and re-emit
# through Loguru, giving Uvicorn access/error logs a consistent format.
_INTERCEPTED_LOGGERS: tuple[str, ...] = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "fastapi",
)


class InterceptHandler(logging.Handler):
    """Route standard-library log records to Loguru.

    This lets third-party libraries that use :mod:`logging` participate in
    the same structured sink without bespoke configuration.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a single stdlib record to the Loguru logger."""
        # Map the stdlib level number to a Loguru level name when possible.
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk back the stack so the originating call site is reported,
        # not this handler.
        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _console_format(record) -> str:  # noqa: ANN001 - loguru record type
    """Return the console log format string.

    ``request_id`` is included when present in the record's ``extra`` bag so
    request-scoped logs are easy to follow.
    """
    base = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
        "| <level>{level: <8}</level> "
        "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
    )
    if record["extra"].get("request_id"):
        base += " | <yellow>req={extra[request_id]}</yellow>"
    return base + " - <level>{message}</level>\n"


def configure_logging(settings: Settings) -> None:
    """Configure Loguru sinks and intercept stdlib logging.

    Idempotent: existing Loguru sinks are removed first so repeated calls
    (e.g. in tests) do not duplicate output.

    Args:
        settings: Application settings controlling level and format.
    """
    logger.remove()

    if settings.json_logs:
        # ``serialize=True`` emits one JSON object per record, including the
        # ``extra`` bag (request_id, latency_ms, ...).
        logger.add(
            sys.stdout,
            level=settings.log_level,
            serialize=True,
            backtrace=False,
            diagnose=False,
            enqueue=True,
        )
    else:
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format=_console_format,
            backtrace=False,
            diagnose=False,
            enqueue=True,
        )

    # Redirect stdlib logging into Loguru with a single root handler.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in _INTERCEPTED_LOGGERS:
        logging_logger = logging.getLogger(name)
        logging_logger.handlers = [InterceptHandler()]
        logging_logger.propagate = False

    logger.debug(f"Logging configured (level={settings.log_level})")


def get_logger() -> Logger:
    """Return the shared Loguru logger.

    Returns:
        The process-wide Loguru logger instance.
    """
    return logger
