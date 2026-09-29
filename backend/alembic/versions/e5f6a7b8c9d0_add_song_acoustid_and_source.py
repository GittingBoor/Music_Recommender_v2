"""add acoustid_id and metadata_source to songs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every song stored so far passed the AcoustID gate; their recording ids
    # were never saved, so acoustid_id stays empty for them.
    op.add_column("songs", sa.Column("acoustid_id", sa.String(36), nullable=True))
    op.add_column(
        "songs",
        sa.Column("metadata_source", sa.String(20), server_default="acoustid", nullable=False),
    )
    op.create_unique_constraint("uq_songs_acoustid_id", "songs", ["acoustid_id"])


def downgrade() -> None:
    op.drop_constraint("uq_songs_acoustid_id", "songs", type_="unique")
    op.drop_column("songs", "metadata_source")
    op.drop_column("songs", "acoustid_id")
