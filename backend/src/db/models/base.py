from sqlalchemy import Float
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deferred-load group shared by every per-second array column.
TIMESERIES_GROUP = "timeseries"


class Base(DeclarativeBase):
    pass


def timeseries_column() -> Mapped[list[float] | None]:
    """A per-second float array that is only loaded when asked for.

    These arrays make up most of a song's row. Loading them for the whole
    library on every list request is what made the API slow, so they are
    deferred; undefer the ``TIMESERIES_GROUP`` group where they are needed.
    """
    return mapped_column(ARRAY(Float), deferred=True, deferred_group=TIMESERIES_GROUP)
