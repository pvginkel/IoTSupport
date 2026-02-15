"""Create firmware_versions table and make coredumps.filename nullable.

Revision ID: 006
Revises: 005
Create Date: 2026-02-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create firmware_versions table and make coredumps.filename nullable."""
    # Create firmware_versions table for tracking stored firmware per model
    op.create_table(
        "firmware_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_model_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["device_model_id"], ["device_models.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "device_model_id", "version", name="uq_firmware_versions_model_version"
        ),
    )
    op.create_index(
        "ix_firmware_versions_device_model_id",
        "firmware_versions",
        ["device_model_id"],
    )

    # Make coredumps.filename nullable (S3 key is derived from device_key + id)
    # The column is kept for the CLI migrate-to-s3 command to match files to records
    with op.batch_alter_table("coredumps") as batch_op:
        batch_op.alter_column(
            "filename",
            existing_type=sa.String(255),
            nullable=True,
        )


def downgrade() -> None:
    """Drop firmware_versions table and make coredumps.filename non-nullable."""
    with op.batch_alter_table("coredumps") as batch_op:
        batch_op.alter_column(
            "filename",
            existing_type=sa.String(255),
            nullable=False,
        )

    op.drop_index("ix_firmware_versions_device_model_id", table_name="firmware_versions")
    op.drop_table("firmware_versions")
