"""Add a dedicated control state for test runs."""

from alembic import op
import sqlalchemy as sa


revision = "20260319_0003"
down_revision = "20260310_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("control_state", sa.String(length=32), nullable=True))
    op.execute(
        "UPDATE test_runs "
        "SET status = 'running', control_state = 'paused' "
        "WHERE status = 'paused'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE test_runs "
        "SET status = 'paused' "
        "WHERE status = 'running' AND control_state IN ('pause_requested', 'paused')"
    )
    op.execute(
        "UPDATE test_runs "
        "SET status = 'stopped', "
        "error_message = COALESCE(error_message, 'Run stopped by user.') "
        "WHERE status = 'running' AND control_state = 'stop_requested'"
    )
    op.drop_column("test_runs", "control_state")
