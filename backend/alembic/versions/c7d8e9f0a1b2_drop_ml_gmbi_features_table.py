"""Drop the unused ml_gmbi_features placeholder table.

The table only ever held empty rows (id column only); the actual GMBI
values live in other_features.

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-07
"""
import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("ml_gmbi_features")


def downgrade() -> None:
    op.create_table(
        "ml_gmbi_features",
        sa.Column("id", sa.String(22), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["songs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
