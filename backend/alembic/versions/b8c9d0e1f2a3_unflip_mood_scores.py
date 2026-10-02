"""undo the happy/aggressive/acoustic/electronic flip

a7b8c9d0e1f2 assumed these heads were read from the wrong softmax column, but the data
it flipped was already correct (written since 6d040aa, which reads column 0). After the
flip, mood "electronic" correlated -0.89 with the Electronic parent genre and Slayer
scored aggressive ~0.05. Flipping again restores the values.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-02

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

_FLIPPED = ("happy", "aggressive", "acoustic", "electronic")


def _flip() -> None:
    sets = []
    for col in _FLIPPED:
        ts = f"{col}_timeseries"
        sets.append(f"{col} = round((1 - {col})::numeric, 4)")
        sets.append(
            f"{ts} = CASE WHEN {ts} IS NULL THEN NULL ELSE ARRAY("
            f"SELECT round((1 - x)::numeric, 4)::float8 "
            f"FROM unnest({ts}) WITH ORDINALITY AS t(x, i) ORDER BY i) END"
        )
    op.execute(f"UPDATE ml_mood_features SET {', '.join(sets)}")


def upgrade() -> None:
    _flip()


def downgrade() -> None:
    _flip()
