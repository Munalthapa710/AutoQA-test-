"""Add CRUD scope and destructive-action controls to test configs."""

from alembic import op
import sqlalchemy as sa


revision = "20260422_0004"
down_revision = "20260319_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_configs", sa.Column("include_paths", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("test_configs", sa.Column("exclude_paths", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("test_configs", sa.Column("crud_mode", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        "test_configs",
        sa.Column("crud_actions", sa.JSON(), nullable=False, server_default='["create", "read", "update"]'),
    )
    op.add_column(
        "test_configs",
        sa.Column("allow_destructive_actions", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("test_configs", "allow_destructive_actions")
    op.drop_column("test_configs", "crud_actions")
    op.drop_column("test_configs", "crud_mode")
    op.drop_column("test_configs", "exclude_paths")
    op.drop_column("test_configs", "include_paths")
