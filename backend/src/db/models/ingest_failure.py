from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base


class IngestFailure(Base):
    """
    A song that did not make it into the library (skipped or errored ingest).

    Written by src.ingest.failures.record_failure, listed by
    GET /api/ingest/failures. song_id is deliberately not a FK: skipped songs
    (e.g. duplicates) may reference a song, failed ones have no row in songs.
    """
    __tablename__ = "ingest_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    source: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    video_id: Mapped[str | None] = mapped_column(String(32))

    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text)

    title: Mapped[str | None] = mapped_column(String(512))
    artist: Mapped[str | None] = mapped_column(String(512))
    song_id: Mapped[str | None] = mapped_column(String(22))
