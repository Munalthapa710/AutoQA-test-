"""Raise the default max steps to 1000."""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0002"
down_revision = "20260310_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "test_configs",
        "max_steps",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="1000",
    )


def downgrade() -> None:
    op.alter_column(
        "test_configs",
        "max_steps",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="20",
    )
