"""Add active boolean flag to devices table.

Allows administrators to exclude devices from automatic credential rotation
without removing them from the system. Defaults to True so all existing
devices remain active after migration.

Revision ID: 008
Revises: 007
Create Date: 2026-02-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add active boolean column to devices table."""
    with op.batch_alter_table("devices") as batch_op:
        batch_op.add_column(
            sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    """Remove active column from devices table."""
    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_column("active")
