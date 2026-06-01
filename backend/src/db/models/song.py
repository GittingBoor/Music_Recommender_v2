from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(500))
    artist: Mapped[str | None] = mapped_column(String(500))
    album: Mapped[str | None] = mapped_column(String(500))
    genre_tag: Mapped[str | None] = mapped_column(String(200))

    file_metadata: Mapped["FileMetadata"] = relationship(back_populates="song", uselist=False)
    lastfm: Mapped["LastfmFeatures"] = relationship(back_populates="song", uselist=False)
    parent_genres: Mapped[list["ParentGenre"]] = relationship(back_populates="song")
    detailed_genres: Mapped[list["DetailedGenre"]] = relationship(back_populates="song")
    instruments: Mapped[list["Instrument"]] = relationship(back_populates="song")
    ml_profile: Mapped["MLProfileFeatures"] = relationship(back_populates="song", uselist=False)
    ml_moods: Mapped["MLMoodFeatures"] = relationship(back_populates="song", uselist=False)
    ml_gmbi: Mapped["MLGMBIFeatures"] = relationship(back_populates="song", uselist=False)
    dsp_features: Mapped["DSPFeatures"] = relationship(back_populates="song", uselist=False)
