"""Create coredumps table for device crash dump tracking.

Revision ID: 005
Revises: 004
Create Date: 2026-02-11

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create coredumps table linked to devices."""
    op.create_table(
        "coredumps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("chip", sa.String(50), nullable=False),
        sa.Column("firmware_version", sa.String(50), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("parse_status", sa.String(20), nullable=False),
        sa.Column("parsed_output", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("parsed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_coredumps_device_id", "coredumps", ["device_id"])


def downgrade() -> None:
    """Drop coredumps table."""
    op.drop_index("ix_coredumps_device_id", table_name="coredumps")
    op.drop_table("coredumps")
