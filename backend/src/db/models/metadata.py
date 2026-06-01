from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class FileMetadata(Base):
    __tablename__ = "file_metadata"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)

    file_format: Mapped[str | None] = mapped_column(String(20))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer)
    bitrate_kbps: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)

    song: Mapped["Song"] = relationship(back_populates="file_metadata")


class TrackMetadata(Base):
    __tablename__ = "track_metadata"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)

    release_date: Mapped[str | None] = mapped_column(String(20))
    playcount: Mapped[int | None] = mapped_column(Integer)
    listeners: Mapped[int | None] = mapped_column(Integer)
    mbid: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(String(500))
    album_mbid: Mapped[str | None] = mapped_column(String(100))
    mb_genres: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    featured_artists: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    # list of {"title": str, "artist": str, "similarity": float}
    similar_tracks: Mapped[list | None] = mapped_column(JSONB)

    song: Mapped["Song"] = relationship(back_populates="track_metadata")


class Artist(Base):
    __tablename__ = "artists"

    name: Mapped[str] = mapped_column(String(500), primary_key=True)
    artist_playcount: Mapped[int | None] = mapped_column(Integer)
    artist_listeners: Mapped[int | None] = mapped_column(Integer)
    artist_bio: Mapped[str | None] = mapped_column(Text)
    similar_artists: Mapped[list[str] | None] = mapped_column(ARRAY(String))
