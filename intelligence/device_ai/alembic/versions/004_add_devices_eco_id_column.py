"""Add indexed eco_id column to devices (P9.x EcoID passport lookup).

EcoID was previously only readable via a scan of the `metadata` JSON blob,
so looking a device up by its public EcoID (as opposed to its device_id)
had no indexed path. This adds a dedicated, indexed `eco_id` column kept in
sync with `metadata['eco_id']` on every write, and backfills it for any
devices already persisted before this migration.

Revision ID: 004_add_devices_eco_id_column
Revises: 003_add_p511_external_trust_anchors
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_add_devices_eco_id_column"
down_revision: Union[str, None] = "003_add_p511_external_trust_anchors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("eco_id", sa.String(length=64), nullable=True))
    op.create_index("ix_devices_eco_id", "devices", ["eco_id"])

    # Backfill from the existing metadata JSON blob so devices registered
    # before this migration remain resolvable by EcoID. JSON extraction
    # syntax is dialect-specific (production runs postgresql; the test suite
    # exercises this same migration against sqlite — see
    # tests/test_p511_external_trust.py's alembic upgrade/downgrade test).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE devices SET eco_id = metadata->>'eco_id' "
            "WHERE eco_id IS NULL AND metadata->>'eco_id' IS NOT NULL"
        )
    elif bind.dialect.name == "sqlite":
        op.execute(
            "UPDATE devices SET eco_id = json_extract(metadata, '$.eco_id') "
            "WHERE eco_id IS NULL AND json_extract(metadata, '$.eco_id') IS NOT NULL"
        )


def downgrade() -> None:
    op.drop_index("ix_devices_eco_id", table_name="devices")
    op.drop_column("devices", "eco_id")
