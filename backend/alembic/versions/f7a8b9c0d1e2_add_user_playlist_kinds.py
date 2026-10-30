"""add collaborative and artists to user_playlists

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-30

The Spotify page groups entries into own and shared playlists and saved albums.
Existing rows count as not collaborative until the next sync, which needs no
extra Spotify read for them.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_playlists",
        sa.Column("collaborative", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("user_playlists", sa.Column("artists", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("user_playlists", "artists")
    op.drop_column("user_playlists", "collaborative")
