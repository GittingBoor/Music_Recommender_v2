from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class DSPFeatures(Base):
    __tablename__ = "dsp_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False, unique=True)

    # Rhythm
    bpm: Mapped[float | None] = mapped_column(Float)
    beat_count: Mapped[int | None] = mapped_column(Integer)
    beat_confidence: Mapped[float | None] = mapped_column(Float)
    danceability: Mapped[float | None] = mapped_column(Float)          # 0–3
    beat_loudness_mean: Mapped[float | None] = mapped_column(Float)
    onset_rate: Mapped[float | None] = mapped_column(Float)

    # Tonal
    key: Mapped[str | None] = mapped_column(String(10))
    scale: Mapped[str | None] = mapped_column(String(10))
    key_strength: Mapped[float | None] = mapped_column(Float)
    tuning_frequency_hz: Mapped[float | None] = mapped_column(Float)
    tuning_cents_deviation: Mapped[float | None] = mapped_column(Float)
    most_common_chord: Mapped[str | None] = mapped_column(String(20))
    chord_strength_mean: Mapped[float | None] = mapped_column(Float)
    chord_change_rate: Mapped[float | None] = mapped_column(Float)

    # Loudness
    integrated_lufs: Mapped[float | None] = mapped_column(Float)
    loudness_range_lu: Mapped[float | None] = mapped_column(Float)
    dynamic_complexity: Mapped[float | None] = mapped_column(Float)
    loudness_db: Mapped[float | None] = mapped_column(Float)

    # Spectral
    spectral_centroid_mean: Mapped[float | None] = mapped_column(Float)
    spectral_rolloff_mean: Mapped[float | None] = mapped_column(Float)
    spectral_flux_mean: Mapped[float | None] = mapped_column(Float)
    mfcc_mean: Mapped[list[float] | None] = mapped_column(ARRAY(Float))  # 13 coefficients
    zero_crossing_rate: Mapped[float | None] = mapped_column(Float)
    dissonance: Mapped[float | None] = mapped_column(Float)

    song: Mapped["Song"] = relationship(back_populates="dsp_features")
