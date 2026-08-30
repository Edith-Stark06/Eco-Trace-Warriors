"""Add P5.9 trust_anchors table.

Revision ID: 002_add_p59_trust_anchors
Revises: 001_initial_p54_device_schema
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_add_p59_trust_anchors"
down_revision: Union[str, None] = "001_initial_p54_device_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trust_anchors",
        sa.Column("anchor_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "device_id",
            sa.String(length=64),
            sa.ForeignKey("devices.device_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("passport_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=32), nullable=False, server_default="sha256"),
        sa.Column("anchored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ANCHORED"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trust_anchors_device_id", "trust_anchors", ["device_id"], unique=True)
    op.create_index("ix_trust_anchors_passport_fingerprint", "trust_anchors", ["passport_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_trust_anchors_passport_fingerprint", table_name="trust_anchors")
    op.drop_index("ix_trust_anchors_device_id", table_name="trust_anchors")
    op.drop_table("trust_anchors")
