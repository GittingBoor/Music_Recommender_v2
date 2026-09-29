"""add original name, YouTube id, review flag to songs and album to track_metadata

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("songs", sa.Column("metadata_reviewed", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("songs", sa.Column("original_name", sa.String(500), nullable=True))
    op.add_column("songs", sa.Column("youtube_video_id", sa.String(20), nullable=True))
    op.add_column("track_metadata", sa.Column("album", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("track_metadata", "album")
    op.drop_column("songs", "youtube_video_id")
    op.drop_column("songs", "original_name")
    op.drop_column("songs", "metadata_reviewed")
