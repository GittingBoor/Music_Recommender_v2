"""add login_events table

Revision ID: a2b3c4d5e6f7
Revises: b8c9d0e1f2a3
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a2b3c4d5e6f7"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_id", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_events_created_at", "login_events", ["created_at"])
    op.create_index("ix_login_events_device_id", "login_events", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_login_events_device_id", table_name="login_events")
    op.drop_index("ix_login_events_created_at", table_name="login_events")
    op.drop_table("login_events")
