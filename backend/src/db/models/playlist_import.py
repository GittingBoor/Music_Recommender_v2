from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base


class PlaylistImport(Base):
    """One click on "Importieren": a Spotify playlist queued for the library."""
    __tablename__ = "playlist_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    spotify_playlist_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlaylistImportTrack(Base):
    """
    One track of a playlist import and what became of it.

    status: queued (waiting in the bulk queue), saved, duplicate (already in
    the library) or failed (reason says why). Rows still queued after a
    restart are queued again on startup. artists is a JSON list.
    """
    __tablename__ = "playlist_import_tracks"
    __table_args__ = (Index("ix_playlist_import_tracks_import_position", "import_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlist_imports.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    spotify_track_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artists: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    isrc: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(64))
    song_id: Mapped[str | None] = mapped_column(String(22))
    video_id: Mapped[str | None] = mapped_column(String(32))
