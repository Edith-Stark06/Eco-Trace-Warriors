"""PostgreSQL / SQLAlchemy implementation of DeviceRepository (P5.4).

Provides full transactional persistence for DeviceRecord entities,
DeviceEnrichment aggregate snapshots, material breakdown items, and audit events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..database.models import (
    DeviceEnrichmentModel,
    DeviceEventModel,
    DeviceModel,
    MaterialItemModel,
)
from ..database.session import session_scope
from .enrichment_models import (
    BrandAssessment,
    CarbonAssessment,
    ConditionAssessment,
    DeviceEnrichment,
    MaterialAssessment,
    MaterialItem,
)
from .models import (
    ConfidenceState,
    DeviceEvent,
    DeviceEventType,
    DeviceRecord,
    RegistrationState,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _model_to_domain(model: DeviceModel) -> DeviceRecord:
    """Convert an ORM DeviceModel to a domain DeviceRecord."""
    return DeviceRecord(
        device_id=model.device_id,
        capture_id=model.capture_id,
        class_id=model.class_id,
        device_type=model.device_type,
        confidence=float(model.confidence),
        confidence_state=ConfidenceState(model.confidence_state),
        bounding_box=tuple(model.bounding_box)[:4],  # type: ignore[arg-type]
        model_version=model.model_version,
        inference_mode=model.inference_mode,
        registration_state=RegistrationState(model.registration_state),
        condition=model.condition,
        materials=dict(model.materials) if model.materials is not None else None,
        carbon_score=float(model.carbon_score) if model.carbon_score is not None else None,
        metadata=dict(model.metadata_) if model.metadata_ is not None else {},
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _event_model_to_domain(model: DeviceEventModel) -> DeviceEvent:
    """Convert an ORM DeviceEventModel to a domain DeviceEvent."""
    return DeviceEvent(
        event_id=model.event_id,
        device_id=model.device_id,
        event_type=DeviceEventType(model.event_type),
        timestamp=model.timestamp,
        capture_id=model.capture_id,
        metadata=dict(model.metadata_) if model.metadata_ is not None else {},
    )


class PostgresDeviceRepository:
    """PostgreSQL-backed repository implementing the DeviceRepository protocol."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | sessionmaker[Session],
    ) -> None:
        self._session_factory = session_factory

    def save(self, device: DeviceRecord) -> None:
        """Persist or update a DeviceRecord within an atomic transaction."""
        with session_scope(self._session_factory) as session:
            model = session.get(DeviceModel, device.device_id)
            if model is None:
                model = DeviceModel(
                    device_id=device.device_id,
                    capture_id=device.capture_id,
                    class_id=device.class_id,
                    device_type=device.device_type,
                    confidence=device.confidence,
                    confidence_state=device.confidence_state.value,
                    bounding_box=list(device.bounding_box),
                    model_version=device.model_version,
                    inference_mode=device.inference_mode,
                    registration_state=device.registration_state.value,
                    condition=device.condition,
                    materials=device.materials,
                    carbon_score=device.carbon_score,
                    metadata_=device.metadata,
                    created_at=device.created_at,
                    updated_at=device.updated_at,
                )
                session.add(model)
            else:
                model.capture_id = device.capture_id
                model.class_id = device.class_id
                model.device_type = device.device_type
                model.confidence = device.confidence
                model.confidence_state = device.confidence_state.value
                model.bounding_box = list(device.bounding_box)
                model.model_version = device.model_version
                model.inference_mode = device.inference_mode
                model.registration_state = device.registration_state.value
                model.condition = device.condition
                model.materials = device.materials
                model.carbon_score = device.carbon_score
                model.metadata_ = device.metadata
                model.updated_at = device.updated_at

    def get(self, device_id: str) -> DeviceRecord | None:
        """Retrieve a DeviceRecord by ID."""
        with session_scope(self._session_factory) as session:
            model = session.get(DeviceModel, device_id)
            if model is None:
                return None
            return _model_to_domain(model)

    def exists(self, device_id: str) -> bool:
        """Check if a DeviceRecord exists."""
        with session_scope(self._session_factory) as session:
            stmt = select(func.count()).select_from(DeviceModel).where(DeviceModel.device_id == device_id)
            count = session.scalar(stmt)
            return bool(count and count > 0)

    def find_by_capture_id(self, capture_id: str) -> list[DeviceRecord]:
        """Return all devices originating from capture_id."""
        with session_scope(self._session_factory) as session:
            stmt = (
                select(DeviceModel)
                .where(DeviceModel.capture_id == capture_id)
                .order_by(DeviceModel.created_at)
            )
            models = session.scalars(stmt).all()
            return [_model_to_domain(m) for m in models]

    def list_all(self, limit: int = 100, offset: int = 0) -> list[DeviceRecord]:
        """List paginated device records."""
        with session_scope(self._session_factory) as session:
            stmt = (
                select(DeviceModel)
                .order_by(DeviceModel.created_at)
                .offset(offset)
                .limit(limit)
            )
            models = session.scalars(stmt).all()
            return [_model_to_domain(m) for m in models]

    def delete(self, device_id: str) -> bool:
        """Delete a DeviceRecord by ID."""
        with session_scope(self._session_factory) as session:
            model = session.get(DeviceModel, device_id)
            if model is not None:
                session.delete(model)
                return True
            return False

    def count(self) -> int:
        """Total number of stored devices."""
        with session_scope(self._session_factory) as session:
            stmt = select(func.count()).select_from(DeviceModel)
            return int(session.scalar(stmt) or 0)

    def save_enrichment(self, enrichment: DeviceEnrichment) -> None:
        """Persist structured DeviceEnrichment and its material items."""
        with session_scope(self._session_factory) as session:
            enrichment_id = f"enr-{uuid.uuid4().hex[:12]}"
            enr_model = DeviceEnrichmentModel(
                enrichment_id=enrichment_id,
                device_id=enrichment.device_id,
                brand_value=enrichment.brand.value,
                brand_status=enrichment.brand.status,
                brand_source=enrichment.brand.source,
                brand_confidence=enrichment.brand.confidence,
                brand_raw_text=enrichment.brand.raw_text,
                condition_value=enrichment.condition.value,
                condition_status=enrichment.condition.status,
                condition_source=enrichment.condition.source,
                condition_notes=enrichment.condition.notes,
                materials_total_mass_g=enrichment.materials.total_mass_g,
                materials_source=enrichment.materials.source,
                materials_version=enrichment.materials.version,
                materials_notes=enrichment.materials.notes,
                carbon_score=enrichment.carbon.carbon_score,
                carbon_methodology=enrichment.carbon.methodology,
                carbon_version=enrichment.carbon.version,
                carbon_source=enrichment.carbon.source,
                carbon_category_breakdown=enrichment.carbon.contributing_factors,
                carbon_notes=enrichment.carbon.notes,
                enriched_at=enrichment.enriched_at,
            )
            session.add(enr_model)

            for item in enrichment.materials.materials:
                item_model = MaterialItemModel(
                    material_item_id=f"mat-{uuid.uuid4().hex[:12]}",
                    enrichment_id=enrichment_id,
                    material_name=item.material,
                    category=item.category,
                    mass_g=item.mass_g,
                    recoverable=item.recoverable,
                    hazardous=item.hazardous,
                    basis=item.basis,
                )
                session.add(item_model)

    def append_event(self, event: DeviceEvent) -> None:
        """Append an immutable DeviceEvent to PostgreSQL."""
        with session_scope(self._session_factory) as session:
            model = DeviceEventModel(
                event_id=event.event_id,
                device_id=event.device_id,
                capture_id=event.capture_id,
                event_type=event.event_type.value if isinstance(event.event_type, DeviceEventType) else str(event.event_type),
                timestamp=event.timestamp,
                metadata_=event.metadata,
            )
            session.add(model)

    def list_events(self, device_id: str) -> list[DeviceEvent]:
        """Return all audit events for device_id sorted chronologically (oldest -> newest)."""
        with session_scope(self._session_factory) as session:
            stmt = (
                select(DeviceEventModel)
                .where(DeviceEventModel.device_id == device_id)
                .order_by(DeviceEventModel.timestamp)
            )
            events = session.scalars(stmt).all()
            return [_event_model_to_domain(e) for e in events]

    def get_latest_event(self, device_id: str) -> DeviceEvent | None:
        """Return the most recent audit event for device_id, or None."""
        with session_scope(self._session_factory) as session:
            stmt = (
                select(DeviceEventModel)
                .where(DeviceEventModel.device_id == device_id)
                .order_by(DeviceEventModel.timestamp.desc())
                .limit(1)
            )
            event = session.scalars(stmt).first()
            if event is None:
                return None
            return _event_model_to_domain(event)

    def count_events(self, device_id: str | None = None) -> int:
        """Count events for a specific device or total."""
        with session_scope(self._session_factory) as session:
            stmt = select(func.count()).select_from(DeviceEventModel)
            if device_id is not None:
                stmt = stmt.where(DeviceEventModel.device_id == device_id)
            return int(session.scalar(stmt) or 0)

    def save_with_event(self, device: DeviceRecord, event: DeviceEvent) -> None:
        """Atomically persist/update a DeviceRecord and append a DeviceEvent in a single transaction."""
        with session_scope(self._session_factory) as session:
            # 1. Save / Update device record
            model = session.get(DeviceModel, device.device_id)
            if model is None:
                model = DeviceModel(
                    device_id=device.device_id,
                    capture_id=device.capture_id,
                    class_id=device.class_id,
                    device_type=device.device_type,
                    confidence=device.confidence,
                    confidence_state=device.confidence_state.value,
                    bounding_box=list(device.bounding_box),
                    model_version=device.model_version,
                    inference_mode=device.inference_mode,
                    registration_state=device.registration_state.value,
                    condition=device.condition,
                    materials=device.materials,
                    carbon_score=device.carbon_score,
                    metadata_=device.metadata,
                    created_at=device.created_at,
                    updated_at=device.updated_at,
                )
                session.add(model)
            else:
                model.capture_id = device.capture_id
                model.class_id = device.class_id
                model.device_type = device.device_type
                model.confidence = device.confidence
                model.confidence_state = device.confidence_state.value
                model.bounding_box = list(device.bounding_box)
                model.model_version = device.model_version
                model.inference_mode = device.inference_mode
                model.registration_state = device.registration_state.value
                model.condition = device.condition
                model.materials = device.materials
                model.carbon_score = device.carbon_score
                model.metadata_ = device.metadata
                model.updated_at = device.updated_at

            # 2. Append event within the same transaction
            event_model = DeviceEventModel(
                event_id=event.event_id,
                device_id=event.device_id,
                capture_id=event.capture_id,
                event_type=event.event_type.value if isinstance(event.event_type, DeviceEventType) else str(event.event_type),
                timestamp=event.timestamp,
                metadata_=event.metadata,
            )
            session.add(event_model)

    def record_event(
        self,
        event_type: str,
        device_id: str,
        capture_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an audit event."""
        evt_type = DeviceEventType(event_type) if event_type in DeviceEventType.__members__ else DeviceEventType.DEVICE_DETECTED
        self.append_event(
            DeviceEvent(
                event_id=f"evt-{uuid.uuid4().hex[:12]}",
                device_id=device_id,
                event_type=evt_type,
                timestamp=_utc_now(),
                capture_id=capture_id,
                metadata=metadata or {},
            )
        )

    def get_events(self, device_id: str) -> list[dict[str, Any]]:
        """Return all audit events for a device as dictionaries."""
        return [e.to_dict() for e in self.list_events(device_id)]
