"""add ingest_failures table

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
Create Date: 2026-09-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingest_failures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("label", sa.String(512), nullable=False),
        sa.Column("video_id", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("artist", sa.String(512), nullable=True),
        sa.Column("song_id", sa.String(22), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_failures_created_at", "ingest_failures", ["created_at"])
    op.create_index("ix_ingest_failures_reason", "ingest_failures", ["reason"])


def downgrade() -> None:
    op.drop_index("ix_ingest_failures_reason", table_name="ingest_failures")
    op.drop_index("ix_ingest_failures_created_at", table_name="ingest_failures")
    op.drop_table("ingest_failures")
