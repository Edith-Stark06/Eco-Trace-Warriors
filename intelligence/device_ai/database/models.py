"""SQLAlchemy 2.x declarative entity models for EcoTrace Device AI (P5.4).

Defines schema for:
- :class:`DeviceModel` (devices)
- :class:`DeviceEnrichmentModel` (device_enrichments)
- :class:`MaterialItemModel` (material_items)
- :class:`DeviceEventModel` (device_events)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DeviceModel(Base):
    """Relational table for persistent Device domain records."""

    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_state: Mapped[str] = mapped_column(String(32), nullable=False)
    bounding_box: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    inference_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    registration_state: Mapped[str] = mapped_column(String(32), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    materials: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    carbon_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    enrichments: Mapped[list[DeviceEnrichmentModel]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="desc(DeviceEnrichmentModel.enriched_at)",
    )

    events: Mapped[list[DeviceEventModel]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DeviceEventModel.timestamp",
    )

    trust_anchor: Mapped[TrustAnchorModel | None] = relationship(
        back_populates="device",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    external_trust_anchor: Mapped[ExternalTrustAnchorModel | None] = relationship(
        back_populates="device",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DeviceEnrichmentModel(Base):
    """Relational table for persistent DeviceEnrichment aggregate snapshots."""

    __tablename__ = "device_enrichments"

    enrichment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Brand facet
    brand_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brand_status: Mapped[str] = mapped_column(String(32), nullable=False)
    brand_source: Mapped[str] = mapped_column(String(32), nullable=False)
    brand_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    brand_raw_text: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Condition facet
    condition_value: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_status: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_source: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Materials facet summary
    materials_total_mass_g: Mapped[float] = mapped_column(Float, nullable=False)
    materials_source: Mapped[str] = mapped_column(String(64), nullable=False)
    materials_version: Mapped[str] = mapped_column(String(32), nullable=False)
    materials_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Carbon facet summary
    carbon_score: Mapped[float] = mapped_column(Float, nullable=False)
    carbon_methodology: Mapped[str] = mapped_column(String(64), nullable=False)
    carbon_version: Mapped[str] = mapped_column(String(32), nullable=False)
    carbon_source: Mapped[str] = mapped_column(String(64), nullable=False)
    carbon_category_breakdown: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    carbon_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    enriched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    device: Mapped[DeviceModel] = relationship(back_populates="enrichments")
    material_items: Mapped[list[MaterialItemModel]] = relationship(
        back_populates="enrichment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MaterialItemModel(Base):
    """Relational child table for individual material specifications."""

    __tablename__ = "material_items"

    material_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enrichment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("device_enrichments.enrichment_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    material_name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    mass_g: Mapped[float] = mapped_column(Float, nullable=False)
    recoverable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hazardous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    basis: Mapped[str] = mapped_column(String(64), nullable=False, default="device_profile")

    enrichment: Mapped[DeviceEnrichmentModel] = relationship(back_populates="material_items")


class DeviceEventModel(Base):
    """Relational table for lifecycle, registration and intelligence audit events."""

    __tablename__ = "device_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    capture_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)

    device: Mapped[DeviceModel] = relationship(back_populates="events")


# Composite indexes for high-frequency audit queries
Index("ix_device_events_device_time", DeviceEventModel.device_id, DeviceEventModel.timestamp)
Index("ix_device_events_type_time", DeviceEventModel.event_type, DeviceEventModel.timestamp)


class TrustAnchorModel(Base):
    """Relational table for persistent Trust Anchor records (P5.9)."""

    __tablename__ = "trust_anchors"

    anchor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    passport_fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False, default="sha256")
    anchored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ANCHORED")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device: Mapped[DeviceModel] = relationship(back_populates="trust_anchor")


class ExternalTrustAnchorModel(Base):
    """Relational table for persistent External Trust Anchor mirror records (P5.11)."""

    __tablename__ = "external_trust_anchors"

    external_anchor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    passport_fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False, default="sha256")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="memory")
    network: Mapped[str] = mapped_column(String(64), nullable=False, default="ecotrace-channel")
    transaction_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    anchored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ANCHORED")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    device: Mapped[DeviceModel] = relationship(back_populates="external_trust_anchor")
