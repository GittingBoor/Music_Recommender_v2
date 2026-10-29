"""add snapshot_id and tracks to user_playlists

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-28

A sync reads a playlist from Spotify only when its snapshot_id changed and
otherwise matches the stored track list with the library again; a full read of
every playlist and the saved tracks used up the app's Spotify quota. Existing
rows have neither, so their first sync reads them once.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_playlists", sa.Column("snapshot_id", sa.String(128), nullable=True))
    op.add_column("user_playlists", sa.Column("tracks", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_playlists", "tracks")
    op.drop_column("user_playlists", "snapshot_id")
