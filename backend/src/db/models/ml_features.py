from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class MLProfileFeatures(Base):
    """
    Profile features from EffNet/MusiCNN classifiers.

    For 2-class classifiers (approachability, engagement, voice, gender):
      - *_label stores the dominant class name (fixed from the mean)
      - *_score stores the dominant class probability
      - *_timeseries stores per-second values of the dominant class only

    arousal and valence are regression values normalized 0–1 from 1–9.
    """
    __tablename__ = "ml_profile_features"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)

    approachability_label: Mapped[str | None] = mapped_column(String(20))   # "niche" or "mainstream"
    approachability_score: Mapped[float | None] = mapped_column(Float)
    approachability_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    engagement_label: Mapped[str | None] = mapped_column(String(20))        # "background" or "active"
    engagement_score: Mapped[float | None] = mapped_column(Float)
    engagement_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    voice_label: Mapped[str | None] = mapped_column(String(20))             # "instrumental" or "vocal"
    voice_score: Mapped[float | None] = mapped_column(Float)
    voice_timeseries: Mapped[list[float] | None] = mapped_column(ARRAY(Float))

    gender_label: Mapped[str | None] = mapped_column(String(10))            # "female" or "male"
    gender_score: Mapped[float | None] = mapped_column(Float)
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
