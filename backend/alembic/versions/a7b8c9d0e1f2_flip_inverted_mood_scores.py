"""flip happy/aggressive/acoustic/electronic mood scores

These four heads were read from softmax column 0, which is the negative class
(see classifiers._binary_with_timeseries). Both columns sum to 1, so the stored
values become correct as 1 - value, timeseries included. Running it again undoes it.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-02

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

_FLIPPED = ("happy", "aggressive", "acoustic", "electronic")


def _flip() -> None:
    sets = []
    for col in _FLIPPED:
        ts = f"{col}_timeseries"
        sets.append(f"{col} = round((1 - {col})::numeric, 4)")
        # ARRAY(...) over a NULL array yields '{}', so missing timeseries stay NULL explicitly.
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
