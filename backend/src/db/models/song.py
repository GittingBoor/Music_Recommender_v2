import hashlib
import string

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base

_BASE62 = string.digits + string.ascii_letters  # 0-9A-Za-z


def generate_song_id(title: str, artist: str) -> str:
    """Generate a deterministic 22-char Base62 ID from title + artist.

    Same title+artist always yields the same ID, preventing duplicates.
    """
    normalized = f"{title.lower().strip()}|{artist.lower().strip()}"
    digest = hashlib.sha256(normalized.encode()).digest()
    n = int.from_bytes(digest, "big")
    chars: list[str] = []
    while n:
        chars.append(_BASE62[n % 62])
        n //= 62
    return "".join(reversed(chars))[:22].ljust(22, "0")


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(String(22), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(500))
    artist: Mapped[str | None] = mapped_column(String(500))

    file_metadata: Mapped["FileMetadata"] = relationship(back_populates="song", uselist=False)
    track_metadata: Mapped["TrackMetadata"] = relationship(back_populates="song", uselist=False)
    parent_genres: Mapped[list["ParentGenre"]] = relationship(back_populates="song")
    detailed_genres: Mapped[list["DetailedGenre"]] = relationship(back_populates="song")
    instruments: Mapped[list["Instrument"]] = relationship(back_populates="song")
    ml_profile: Mapped["MLProfileFeatures"] = relationship(back_populates="song", uselist=False)
    ml_moods: Mapped["MLMoodFeatures"] = relationship(back_populates="song", uselist=False)
    ml_gmbi: Mapped["MLGMBIFeatures"] = relationship(back_populates="song", uselist=False)
    dsp_features: Mapped["DSPFeatures"] = relationship(back_populates="song", uselist=False)
    other_features: Mapped["OtherFeatures"] = relationship(back_populates="song", uselist=False)
