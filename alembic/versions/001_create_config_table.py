"""Create configs table.

Revision ID: 001
Revises:
Create Date: 2024-01-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("ix_configs_mac_address", table_name="configs")
    op.drop_table("configs")
