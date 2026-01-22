"""Device provisioning MDM - create device_models and devices tables, drop configs.

Revision ID: 002
Revises: 001
Create Date: 2026-01-22

This migration replaces the MAC-address-based config system with a device
provisioning MDM system using DeviceModel and Device tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create device_models table
    op.create_table(
        "device_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("firmware_version", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_device_models_code", "device_models", ["code"], unique=False)

    # Create devices table
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=8), nullable=False),
        sa.Column("device_model_id", sa.Integer(), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("rotation_state", sa.String(length=20), nullable=False, server_default="OK"),
        sa.Column("cached_secret", sa.String(length=500), nullable=True),
        sa.Column("secret_created_at", sa.DateTime(), nullable=True),
        sa.Column("last_rotation_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_rotation_completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["device_model_id"],
            ["device_models.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_devices_key", "devices", ["key"], unique=False)
    op.create_index("ix_devices_device_model_id", "devices", ["device_model_id"], unique=False)
    op.create_index("ix_devices_rotation_state", "devices", ["rotation_state"], unique=False)

    # Drop configs table (complete removal, no backwards compatibility)
    op.drop_index("ix_configs_mac_address", table_name="configs")
    op.drop_table("configs")


def downgrade() -> None:
    # Recreate configs table
    op.create_table(
        "configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mac_address", sa.String(length=17), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("device_entity_id", sa.String(length=255), nullable=True),
        sa.Column("enable_ota", sa.Boolean(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mac_address"),
    )
    op.create_index("ix_configs_mac_address", "configs", ["mac_address"], unique=False)

    # Drop devices table
    op.drop_index("ix_devices_rotation_state", table_name="devices")
    op.drop_index("ix_devices_device_model_id", table_name="devices")
    op.drop_index("ix_devices_key", table_name="devices")
    op.drop_table("devices")

    # Drop device_models table
    op.drop_index("ix_device_models_code", table_name="device_models")
    op.drop_table("device_models")
