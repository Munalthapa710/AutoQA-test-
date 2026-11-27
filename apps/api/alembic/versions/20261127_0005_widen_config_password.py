"""Allow encrypted credentials and configurable run time limits."""

from alembic import op
import sqlalchemy as sa


revision = "20261127_0005"
down_revision = "20260422_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("test_configs") as table:
        table.alter_column("password", existing_type=sa.String(255), type_=sa.Text())
        table.add_column(sa.Column("max_duration_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("test_configs") as table:
        table.drop_column("max_duration_seconds")
        table.alter_column("password", existing_type=sa.Text(), type_=sa.String(255))
