"""Initial P5.4 device schema: devices, enrichments, material_items, device_events.

Revision ID: 001_initial_p54_device_schema
Revises: None
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial_p54_device_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create devices table
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("capture_id", sa.String(length=64), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("device_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_state", sa.String(length=32), nullable=False),
        sa.Column("bounding_box", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("inference_mode", sa.String(length=32), nullable=False),
        sa.Column("registration_state", sa.String(length=32), nullable=False),
        sa.Column("condition", sa.String(length=32), nullable=True),
        sa.Column("materials", sa.JSON(), nullable=True),
        sa.Column("carbon_score", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_devices_capture_id", "devices", ["capture_id"])

    # 2. Create device_enrichments table
    op.create_table(
        "device_enrichments",
        sa.Column("enrichment_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("device_id", sa.String(length=64), sa.ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_value", sa.String(length=64), nullable=True),
        sa.Column("brand_status", sa.String(length=32), nullable=False),
        sa.Column("brand_source", sa.String(length=32), nullable=False),
        sa.Column("brand_confidence", sa.Float(), nullable=True),
        sa.Column("brand_raw_text", sa.String(length=255), nullable=True),
        sa.Column("condition_value", sa.String(length=32), nullable=False),
        sa.Column("condition_status", sa.String(length=32), nullable=False),
        sa.Column("condition_source", sa.String(length=64), nullable=False),
        sa.Column("condition_notes", sa.Text(), nullable=True),
        sa.Column("materials_total_mass_g", sa.Float(), nullable=False),
        sa.Column("materials_source", sa.String(length=64), nullable=False),
        sa.Column("materials_version", sa.String(length=32), nullable=False),
        sa.Column("materials_notes", sa.Text(), nullable=True),
        sa.Column("carbon_score", sa.Float(), nullable=False),
        sa.Column("carbon_methodology", sa.String(length=64), nullable=False),
        sa.Column("carbon_version", sa.String(length=32), nullable=False),
        sa.Column("carbon_source", sa.String(length=64), nullable=False),
        sa.Column("carbon_category_breakdown", sa.JSON(), nullable=False),
        sa.Column("carbon_notes", sa.Text(), nullable=True),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_enrichments_device_id", "device_enrichments", ["device_id"])

    # 3. Create material_items table
    op.create_table(
        "material_items",
        sa.Column("material_item_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("enrichment_id", sa.String(length=64), sa.ForeignKey("device_enrichments.enrichment_id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("mass_g", sa.Float(), nullable=False),
        sa.Column("recoverable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("hazardous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("basis", sa.String(length=64), nullable=False, server_default="device_profile"),
    )
    op.create_index("ix_material_items_enrichment_id", "material_items", ["enrichment_id"])

    # 4. Create device_events table
    op.create_table(
        "device_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("device_id", sa.String(length=64), sa.ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False),
        sa.Column("capture_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_device_events_device_id", "device_events", ["device_id"])
    op.create_index("ix_device_events_capture_id", "device_events", ["capture_id"])
    op.create_index("ix_device_events_event_type", "device_events", ["event_type"])
    op.create_index("ix_device_events_timestamp", "device_events", ["timestamp"])
    op.create_index("ix_device_events_device_time", "device_events", ["device_id", "timestamp"])
    op.create_index("ix_device_events_type_time", "device_events", ["event_type", "timestamp"])


def downgrade() -> None:
    op.drop_table("device_events")
    op.drop_table("material_items")
    op.drop_table("device_enrichments")
    op.drop_table("devices")
