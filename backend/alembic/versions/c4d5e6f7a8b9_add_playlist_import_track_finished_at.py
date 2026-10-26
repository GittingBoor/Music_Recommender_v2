"""add finished_at to playlist import tracks

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-10-26

Existing rows are backfilled where a time is known: duplicates ended with
their import, failed tracks when their ingest_failures row was written.
Saved tracks of older imports stay null (songs carry no timestamp).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None

# The bulk item's label is "Artist1, Artist2 – Title" (see PlaylistImporter._item).
_BACKFILL_FAILED = """
UPDATE playlist_import_tracks t SET finished_at = (
    SELECT min(f.created_at) FROM ingest_failures f JOIN playlist_imports i ON i.id = t.import_id
    WHERE f.source = 'spotify' AND f.created_at >= i.created_at
      AND f.video_id IS NOT DISTINCT FROM t.video_id
      AND f.label = (
          SELECT string_agg(a.value, ', ' ORDER BY a.n)
          FROM json_array_elements_text(t.artists::json) WITH ORDINALITY AS a(value, n)
      ) || ' – ' || t.title
)
WHERE t.status = 'failed'
"""

_BACKFILL_DUPLICATE = """
UPDATE playlist_import_tracks t SET finished_at = i.created_at
FROM playlist_imports i WHERE i.id = t.import_id AND t.status = 'duplicate'
"""


def upgrade() -> None:
    op.add_column("playlist_import_tracks", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(_BACKFILL_DUPLICATE)
    op.execute(_BACKFILL_FAILED)


def downgrade() -> None:
    op.drop_column("playlist_import_tracks", "finished_at")
