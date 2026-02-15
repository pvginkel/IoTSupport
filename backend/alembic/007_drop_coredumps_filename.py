"""Drop coredumps.filename column after CLI migrate-to-s3 has run.

This migration should only be applied AFTER the CLI `migrate-to-s3` command
has been run in all environments to migrate filesystem data to S3.

Revision ID: 007
Revises: 006
Create Date: 2026-02-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the filename column from coredumps (S3 key is deterministic)."""
    with op.batch_alter_table("coredumps") as batch_op:
        batch_op.drop_column("filename")


def downgrade() -> None:
    """Re-add filename column to coredumps."""
    with op.batch_alter_table("coredumps") as batch_op:
        batch_op.add_column(
            sa.Column("filename", sa.String(255), nullable=True),
        )
