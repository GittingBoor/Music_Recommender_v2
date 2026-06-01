from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)
    instrument: Mapped[str] = mapped_column(String(100), primary_key=True)
    probability: Mapped[float] = mapped_column(Float, nullable=False)

    song: Mapped["Song"] = relationship(back_populates="instruments")
