"""PostgreSQL / SQLAlchemy implementation of TrustAnchorRepository (P5.9).

Provides full transactional persistence for TrustAnchor domain entities within the
PostgreSQL relational data store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..database.models import TrustAnchorModel
from ..database.session import session_scope
from ..exceptions import AnchorConflictError
from .trust_anchor import TrustAnchor, TrustAnchorStatus


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _anchor_model_to_domain(model: TrustAnchorModel) -> TrustAnchor:
    """Convert an ORM TrustAnchorModel to a domain TrustAnchor."""
    anchored_at_str = (
        model.anchored_at.isoformat()
        if isinstance(model.anchored_at, datetime)
        else str(model.anchored_at)
    )
    return TrustAnchor(
        anchor_id=model.anchor_id,
        device_id=model.device_id,
        passport_fingerprint=model.passport_fingerprint,
        algorithm=model.algorithm,
        anchored_at=anchored_at_str,
        status=TrustAnchorStatus(model.status),
        metadata=dict(model.metadata_) if model.metadata_ is not None else {},
    )


class PostgresTrustAnchorRepository:
    """PostgreSQL-backed repository implementing the TrustAnchorRepository protocol (P5.9)."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | sessionmaker[Session],
    ) -> None:
        self._session_factory = session_factory

    def save(self, anchor: TrustAnchor, overwrite: bool = False) -> TrustAnchor:
        """Persist a TrustAnchor within an atomic transaction.

        Rules:
        - If device not anchored: insert and return domain anchor.
        - If device already anchored with IDENTICAL fingerprint: return existing (idempotent).
        - If device already anchored with DIFFERENT fingerprint:
            - If overwrite is False: raise AnchorConflictError (no overwrite).
            - If overwrite is True: update existing row with new anchor data.
        """
        now = _utc_now()
        anchored_at_dt = (
            datetime.fromisoformat(anchor.anchored_at)
            if isinstance(anchor.anchored_at, str)
            else anchor.anchored_at
        )

        with session_scope(self._session_factory) as session:
            stmt = select(TrustAnchorModel).where(TrustAnchorModel.device_id == anchor.device_id)
            existing = session.execute(stmt).scalar_one_or_none()

            if existing is not None:
                if not overwrite:
                    if existing.passport_fingerprint == anchor.passport_fingerprint:
                        logger.bind(device_id=anchor.device_id).info(
                            "Idempotent anchor request in PostgreSQL store."
                        )
                        return _anchor_model_to_domain(existing)

                    raise AnchorConflictError(
                        f"Anchor conflict: device '{anchor.device_id}' is already anchored with fingerprint "
                        f"'{existing.passport_fingerprint}'; cannot overwrite with '{anchor.passport_fingerprint}'.",
                        details={
                            "device_id": anchor.device_id,
                            "existing_fingerprint": existing.passport_fingerprint,
                            "new_fingerprint": anchor.passport_fingerprint,
                        },
                    )

                # Explicit overwrite / re-anchor
                existing.anchor_id = anchor.anchor_id
                existing.passport_fingerprint = anchor.passport_fingerprint
                existing.algorithm = anchor.algorithm
                existing.anchored_at = anchored_at_dt
                existing.status = (
                    anchor.status.value
                    if isinstance(anchor.status, (TrustAnchorStatus, str))
                    else str(anchor.status)
                )
                existing.metadata_ = dict(anchor.metadata)
                existing.updated_at = now
                session.flush()
                logger.bind(device_id=anchor.device_id, anchor_id=anchor.anchor_id).info(
                    "Trust anchor updated (re-anchored) in PostgreSQL repository."
                )
                return _anchor_model_to_domain(existing)

            model = TrustAnchorModel(
                anchor_id=anchor.anchor_id,
                device_id=anchor.device_id,
                passport_fingerprint=anchor.passport_fingerprint,
                algorithm=anchor.algorithm,
                anchored_at=anchored_at_dt,
                status=(
                    anchor.status.value
                    if isinstance(anchor.status, (TrustAnchorStatus, str))
                    else str(anchor.status)
                ),
                metadata_=dict(anchor.metadata),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            logger.bind(device_id=anchor.device_id, anchor_id=anchor.anchor_id).info(
                "Trust anchor stored in PostgreSQL repository."
            )
            return _anchor_model_to_domain(model)

    def get_by_device_id(self, device_id: str) -> TrustAnchor | None:
        """Retrieve stored TrustAnchor for a device ID, or None if not found."""
        with session_scope(self._session_factory) as session:
            stmt = select(TrustAnchorModel).where(TrustAnchorModel.device_id == device_id)
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return None
            return _anchor_model_to_domain(model)

    def exists(self, device_id: str) -> bool:
        """Check if a device is anchored in the repository."""
        with session_scope(self._session_factory) as session:
            stmt = select(func.count(TrustAnchorModel.anchor_id)).where(
                TrustAnchorModel.device_id == device_id
            )
            count = session.execute(stmt).scalar_one()
            return count > 0

    def count(self) -> int:
        """Return total count of anchored records."""
        with session_scope(self._session_factory) as session:
            stmt = select(func.count(TrustAnchorModel.anchor_id))
            return session.execute(stmt).scalar_one()

    def clear(self) -> None:
        """Clear all stored trust anchors (test utility)."""
        with session_scope(self._session_factory) as session:
            session.query(TrustAnchorModel).delete()
