from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class FileMetadata(Base):
    __tablename__ = "file_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False, unique=True)

    file_format: Mapped[str | None] = mapped_column(String(20))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer)
    bitrate_kbps: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)

    song: Mapped["Song"] = relationship(back_populates="file_metadata")


class LastfmFeatures(Base):
    __tablename__ = "lastfm_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False, unique=True)

    release_year: Mapped[str | None] = mapped_column(String(10))
    playcount: Mapped[int | None] = mapped_column(Integer)
    listeners: Mapped[int | None] = mapped_column(Integer)
    mbid: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(String(500))
    album_mbid: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    artist_playcount: Mapped[int | None] = mapped_column(Integer)
    artist_listeners: Mapped[int | None] = mapped_column(Integer)
    artist_bio: Mapped[str | None] = mapped_column(Text)
    similar_artists: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    song: Mapped["Song"] = relationship(back_populates="lastfm")
