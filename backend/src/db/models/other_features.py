from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, timeseries_column


class OtherFeatures(Base):
    """
    Additional features extracted via the audio_process pipeline.

    GMBI (General Music Branding Inventory) scores come from Random Forest
    models trained on ~-2..2 range. Timeseries contain one value per
    DL-prediction frame (~1 s each).

    tonal is the probability that the track is tonal (vs. atonal), from a
    MusiCNN classifier. hpcp_mean is the 12-bin chroma mean vector.
    tristimulus_mean holds 3 tristimulus values (harmonic brightness).
    """
    __tablename__ = "other_features"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)

    # GMBI — 5 dimensions (RandomForest), scale approx -2..2
    gmbi_valence: Mapped[float | None] = mapped_column(Float)
    gmbi_arousal: Mapped[float | None] = mapped_column(Float)
    gmbi_authenticity: Mapped[float | None] = mapped_column(Float)
    gmbi_timeliness: Mapped[float | None] = mapped_column(Float)
    gmbi_complexity: Mapped[float | None] = mapped_column(Float)

    # Tonal/Atonal (MusiCNN) — probability of "tonal" class, 0..1
    tonal: Mapped[float | None] = mapped_column(Float)
    tonal_timeseries: Mapped[list[float] | None] = timeseries_column()

    # Low-level harmony (Essentia, no external model needed)
    hpcp_mean: Mapped[list[float] | None] = mapped_column(ARRAY(Float))        # 12-bin chroma
    tristimulus_mean: Mapped[list[float] | None] = mapped_column(ARRAY(Float))  # 3 values

    song: Mapped["Song"] = relationship(back_populates="other_features")
