from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class MLProfileFeatures(Base):
    """
    Profile features from EffNet/MusiCNN classifiers.

    For 2-class classifiers both class scores are stored separately.
    Timeseries contains per-second values of the first-listed class.
    arousal and valence are regression values normalized 0–1 from 1–9.
    """
    __tablename__ = "ml_profile_features"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)

    niche_score: Mapped[float | None] = mapped_column(Float)
    mainstream_score: Mapped[float | None] = mapped_column(Float)
    approachability_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    background_score: Mapped[float | None] = mapped_column(Float)
    active_score: Mapped[float | None] = mapped_column(Float)
    engagement_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    instrumental_score: Mapped[float | None] = mapped_column(Float)
    vocal_score: Mapped[float | None] = mapped_column(Float)
    voice_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    female_score: Mapped[float | None] = mapped_column(Float)
    male_score: Mapped[float | None] = mapped_column(Float)
    gender_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    arousal: Mapped[float | None] = mapped_column(Float)                    # 0–1
    arousal_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    valence: Mapped[float | None] = mapped_column(Float)                    # 0–1
    valence_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    song: Mapped["Song"] = relationship(back_populates="ml_profile")


class MLMoodFeatures(Base):
    __tablename__ = "ml_mood_features"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)

    happy: Mapped[float | None] = mapped_column(Float)
    happy_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    sad: Mapped[float | None] = mapped_column(Float)
    sad_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    aggressive: Mapped[float | None] = mapped_column(Float)
    aggressive_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    party: Mapped[float | None] = mapped_column(Float)
    party_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    relaxed: Mapped[float | None] = mapped_column(Float)
    relaxed_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    acoustic: Mapped[float | None] = mapped_column(Float)
    acoustic_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    electronic: Mapped[float | None] = mapped_column(Float)
    electronic_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    song: Mapped["Song"] = relationship(back_populates="ml_moods")


class MLGMBIFeatures(Base):
    """General Music Branding Inventory — placeholder, fields to be defined."""
    __tablename__ = "ml_gmbi_features"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)

    song: Mapped["Song"] = relationship(back_populates="ml_gmbi")
