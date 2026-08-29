"""SQLAlchemy session management and transactional scopes for Device AI (P5.4)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Callable

from loguru import logger
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a configured sessionmaker for the given engine.

    Args:
        engine: The SQLAlchemy Engine instance.

    Returns:
        A configured :class:`sessionmaker`.
    """
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def session_scope(
    session_factory: Callable[[], Session] | sessionmaker[Session],
) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations.

    Ensures explicit commit on success and automatic rollback on exception.

    Args:
        session_factory: Session maker callable.

    Yields:
        An active :class:`Session`.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("Database transaction rolled back due to error: {}", exc)
        raise
    finally:
        session.close()
