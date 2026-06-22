"""add other_features table

Revision ID: a1b2c3d4e5f6
Revises: 54e51b95250d
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "54e51b95250d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "other_features",
        sa.Column("id", sa.String(22), nullable=False),

        # GMBI — 5 dimensions (RandomForest), scale approx -2..2
        sa.Column("gmbi_valence",      sa.Float(), nullable=True),
        sa.Column("gmbi_arousal",      sa.Float(), nullable=True),
        sa.Column("gmbi_authenticity", sa.Float(), nullable=True),
        sa.Column("gmbi_timeliness",   sa.Float(), nullable=True),
        sa.Column("gmbi_complexity",   sa.Float(), nullable=True),

        # Tonal/Atonal (MusiCNN) — probability of "tonal" class, 0..1
        sa.Column("tonal",            sa.Float(), nullable=True),
        sa.Column("tonal_timeseries", postgresql.ARRAY(sa.Float()), nullable=True),

        # Low-level harmony (Essentia, no external model)
        sa.Column("hpcp_mean",        postgresql.ARRAY(sa.Float()), nullable=True),  # 12-bin chroma
        sa.Column("tristimulus_mean", postgresql.ARRAY(sa.Float()), nullable=True),  # 3 values

        sa.ForeignKeyConstraint(["id"], ["songs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("other_features")
