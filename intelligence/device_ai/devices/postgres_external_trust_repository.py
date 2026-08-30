"""PostgreSQL / SQLAlchemy implementation of External Trust Anchor repository (P5.11).

Provides full transactional persistence for ExternalTrustAnchor mirror records within the
PostgreSQL relational data store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..database.models import ExternalTrustAnchorModel
from ..database.session import session_scope
from ..exceptions import ExternalAnchorConflictError
from .external_trust import ExternalTrustAnchor


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _external_anchor_model_to_domain(model: ExternalTrustAnchorModel) -> ExternalTrustAnchor:
    """Convert an ORM ExternalTrustAnchorModel to a domain ExternalTrustAnchor."""
    anchored_at_str = (
        model.anchored_at.isoformat()
        if isinstance(model.anchored_at, datetime)
        else str(model.anchored_at)
    )
    return ExternalTrustAnchor(
        external_anchor_id=model.external_anchor_id,
        device_id=model.device_id,
        passport_fingerprint=model.passport_fingerprint,
        algorithm=model.algorithm,
        provider=model.provider,
        network=model.network,
        transaction_id=model.transaction_id,
        anchored_at=anchored_at_str,
        status=model.status,
        metadata=dict(model.metadata_) if model.metadata_ is not None else {},
    )


class PostgresExternalTrustAnchorRepository:
    """PostgreSQL-backed repository for ExternalTrustAnchor mirror records (P5.11)."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | sessionmaker[Session],
    ) -> None:
        self._session_factory = session_factory

    def save(self, anchor: ExternalTrustAnchor, overwrite: bool = False) -> ExternalTrustAnchor:
        """Persist an ExternalTrustAnchor within an atomic transaction.

        Rules:
        - If device not anchored: insert and return domain anchor.
        - If device already anchored with IDENTICAL fingerprint: return existing (idempotent).
        - If device already anchored with DIFFERENT fingerprint:
            - If overwrite is False: raise ExternalAnchorConflictError.
            - If overwrite is True: update existing row in-place.
        """
        now = _utc_now()
        anchored_at_dt = (
            datetime.fromisoformat(anchor.anchored_at)
            if isinstance(anchor.anchored_at, str)
            else anchor.anchored_at
        )

        with session_scope(self._session_factory) as session:
            stmt = select(ExternalTrustAnchorModel).where(
                ExternalTrustAnchorModel.device_id == anchor.device_id
            )
            existing = session.execute(stmt).scalar_one_or_none()

            if existing is not None:
                if not overwrite:
                    if existing.passport_fingerprint == anchor.passport_fingerprint:
                        logger.bind(device_id=anchor.device_id).info(
                            "Idempotent external anchor in PostgreSQL store."
                        )
                        return _external_anchor_model_to_domain(existing)

                    raise ExternalAnchorConflictError(
                        f"External anchor conflict: device '{anchor.device_id}' is already anchored externally with "
                        f"fingerprint '{existing.passport_fingerprint}'; cannot overwrite with '{anchor.passport_fingerprint}'.",
                        details={
                            "device_id": anchor.device_id,
                            "existing_fingerprint": existing.passport_fingerprint,
                            "new_fingerprint": anchor.passport_fingerprint,
                        },
                    )

                # Overwrite in-place
                existing.external_anchor_id = anchor.external_anchor_id
                existing.passport_fingerprint = anchor.passport_fingerprint
                existing.algorithm = anchor.algorithm
                existing.provider = anchor.provider
                existing.network = anchor.network
                existing.transaction_id = anchor.transaction_id
                existing.anchored_at = anchored_at_dt
                existing.status = anchor.status
                existing.metadata_ = dict(anchor.metadata)
                existing.updated_at = now
                session.flush()
                logger.bind(device_id=anchor.device_id, tx_id=anchor.transaction_id).info(
                    "Updated ExternalTrustAnchor row in PostgreSQL."
                )
                return _external_anchor_model_to_domain(existing)

            # Insert new row
            model = ExternalTrustAnchorModel(
                external_anchor_id=anchor.external_anchor_id,
                device_id=anchor.device_id,
                passport_fingerprint=anchor.passport_fingerprint,
                algorithm=anchor.algorithm,
                provider=anchor.provider,
                network=anchor.network,
                transaction_id=anchor.transaction_id,
                anchored_at=anchored_at_dt,
                status=anchor.status,
                metadata_=dict(anchor.metadata),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            logger.bind(device_id=anchor.device_id, tx_id=anchor.transaction_id).info(
                "Created ExternalTrustAnchor row in PostgreSQL."
            )
            return _external_anchor_model_to_domain(model)

    def get_by_device_id(self, device_id: str) -> ExternalTrustAnchor | None:
        """Retrieve external anchor by device_id."""
        with session_scope(self._session_factory) as session:
            stmt = select(ExternalTrustAnchorModel).where(
                ExternalTrustAnchorModel.device_id == device_id
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return None
            return _external_anchor_model_to_domain(model)

    def delete_by_device_id(self, device_id: str) -> bool:
        """Delete external anchor row for a device."""
        with session_scope(self._session_factory) as session:
            stmt = select(ExternalTrustAnchorModel).where(
                ExternalTrustAnchorModel.device_id == device_id
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return False
            session.delete(model)
            return True

    def count(self) -> int:
        """Return total count of external trust anchor records."""
        with session_scope(self._session_factory) as session:
            stmt = select(func.count(ExternalTrustAnchorModel.external_anchor_id))
            return int(session.execute(stmt).scalar() or 0)

    def exists(self, device_id: str) -> bool:
        """Check whether an external trust anchor exists for a device."""
        with session_scope(self._session_factory) as session:
            stmt = select(func.count(ExternalTrustAnchorModel.external_anchor_id)).where(
                ExternalTrustAnchorModel.device_id == device_id
            )
            return bool((session.execute(stmt).scalar() or 0) > 0)
