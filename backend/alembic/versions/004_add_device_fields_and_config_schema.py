"""Add device display fields and config_schema to device model.

Revision ID: 004
Revises: 003
Create Date: 2025-01-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add device_name, device_entity_id, enable_ota to devices table.
    Add config_schema to device_models table.
    """
    # Add fields extracted from config JSON for display purposes
    op.add_column(
        "devices",
        sa.Column("device_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("device_entity_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("enable_ota", sa.Boolean(), nullable=True),
    )

    # Add config_schema to device_models for JSON schema validation
    op.add_column(
        "device_models",
        sa.Column("config_schema", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove device display fields and config_schema."""
    op.drop_column("device_models", "config_schema")
    op.drop_column("devices", "enable_ota")
    op.drop_column("devices", "device_entity_id")
    op.drop_column("devices", "device_name")
