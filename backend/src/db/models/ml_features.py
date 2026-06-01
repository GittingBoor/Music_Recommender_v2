from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class MLProfileFeatures(Base):
    """
    Profile features from EffNet/MusiCNN classifiers.

    Each float stores the probability of the named side:
      niche        = P(niche)        → mainstream is 1 - niche
      background   = P(background)   → active is 1 - background
      instrumental = P(instrumental) → vocal is 1 - instrumental
      female       = P(female)       → male is 1 - female

    arousal and valence are normalized from 1–9 to 0–1: (raw - 1) / 8
    """
    __tablename__ = "ml_profile_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False, unique=True)

    niche: Mapped[float | None] = mapped_column(Float)
    background: Mapped[float | None] = mapped_column(Float)
    instrumental: Mapped[float | None] = mapped_column(Float)
    female: Mapped[float | None] = mapped_column(Float)
    arousal: Mapped[float | None] = mapped_column(Float)   # normalized 0–1
    valence: Mapped[float | None] = mapped_column(Float)   # normalized 0–1

    song: Mapped["Song"] = relationship(back_populates="ml_profile")


class MLMoodFeatures(Base):
    __tablename__ = "ml_mood_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False, unique=True)

    happy: Mapped[float | None] = mapped_column(Float)
    sad: Mapped[float | None] = mapped_column(Float)
    aggressive: Mapped[float | None] = mapped_column(Float)
    party: Mapped[float | None] = mapped_column(Float)
    relaxed: Mapped[float | None] = mapped_column(Float)
    acoustic: Mapped[float | None] = mapped_column(Float)
    electronic: Mapped[float | None] = mapped_column(Float)

    song: Mapped["Song"] = relationship(back_populates="ml_moods")


class MLGMBIFeatures(Base):
    """General Music Branding Inventory — placeholder, fields to be defined."""
    __tablename__ = "ml_gmbi_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False, unique=True)

    song: Mapped["Song"] = relationship(back_populates="ml_gmbi")
