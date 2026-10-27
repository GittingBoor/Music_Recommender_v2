from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base

PLAYLIST = "playlist"
# The user's saved tracks ("Lieblingssongs"); stored under spotify_playlist_id LIKED_ID.
LIKED = "liked"
LIKED_ID = "liked"


class UserPlaylist(Base):
    """
    A user's Spotify playlist (or saved tracks) as a personal view on the shared library.

    Written by an import (src.spotify.importer) and by a sync (src.spotify.library).
    track_count counts the playlist's distinct music tracks on Spotify, whether
    or not they are in the library; the ones that are sit in user_playlist_songs.
    """
    __tablename__ = "user_playlists"
    __table_args__ = (UniqueConstraint("user_id", "spotify_playlist_id", name="uq_user_playlists_user_playlist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    spotify_playlist_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    image: Mapped[str | None] = mapped_column(String(1024))
    track_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserPlaylistSong(Base):
    """A library song that is in a user's playlist; position is its first place in the playlist."""
    __tablename__ = "user_playlist_songs"

    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_playlists.id", ondelete="CASCADE"), primary_key=True
    )
    song_id: Mapped[str] = mapped_column(
        String(22), ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
