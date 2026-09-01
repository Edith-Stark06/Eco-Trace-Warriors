"""SQLAlchemy engine lifecycle and connection factory for Device AI (P5.4).

Manages engine lifecycle, connection pooling, and connection health.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import QueuePool, StaticPool

_ENGINE_CACHE: dict[str, Engine] = {}


def get_engine(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: int = 30,
    echo: bool = False,
) -> Engine:
    """Return a cached or newly created SQLAlchemy Engine.

    Args:
        database_url: Database connection string (e.g. postgresql+psycopg://...).
        pool_size: Connection pool size.
        max_overflow: Max overflow connections beyond pool_size.
        pool_timeout: Pool acquisition timeout in seconds.
        echo: Whether to log SQL statements.

    Returns:
        The configured :class:`Engine`.
    """
    if database_url in _ENGINE_CACHE:
        return _ENGINE_CACHE[database_url]

    # Redact credentials for logging
    sanitized_url = database_url
    if "@" in database_url:
        prefix, host_part = database_url.split("@", 1)
        scheme = prefix.split("://")[0] if "://" in prefix else "db"
        sanitized_url = f"{scheme}://***:***@{host_part}"

    logger.info("Initializing database engine: {}", sanitized_url)

    engine_kwargs: dict[str, Any] = {
        "echo": echo,
        "future": True,
    }

    if database_url.startswith("sqlite"):
        # SQLite configuration for local/in-memory testing
        if ":memory:" in database_url or "mode=memory" in database_url:
            engine_kwargs["poolclass"] = StaticPool
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # PostgreSQL production configuration
        engine_kwargs["poolclass"] = QueuePool
        engine_kwargs["pool_size"] = pool_size
        engine_kwargs["max_overflow"] = max_overflow
        engine_kwargs["pool_timeout"] = pool_timeout
        engine_kwargs["pool_pre_ping"] = True

    engine = create_engine(database_url, **engine_kwargs)
    _ENGINE_CACHE[database_url] = engine
    return engine


def ping_engine(engine: Engine) -> bool:
    """Run a trivial round-trip query to verify the database is reachable.

    Used by the ``/health`` readiness check (P7.3). Never raises — any
    connectivity failure is caught and reported as ``False`` so a database
    outage degrades the health endpoint rather than crashing it.

    Args:
        engine: The engine to probe.

    Returns:
        ``True`` if a connection could be opened and ``SELECT 1`` executed.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database health probe failed: {}", exc)
        return False


def dispose_engines() -> None:
    """Dispose of all cached database engines."""
    for url, engine in list(_ENGINE_CACHE.items()):
        try:
            engine.dispose()
        except Exception as exc:
            logger.warning("Error disposing database engine: {}", exc)
    _ENGINE_CACHE.clear()
