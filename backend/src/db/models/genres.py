from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class ParentGenre(Base):
    __tablename__ = "parent_genres"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)
    genre: Mapped[str] = mapped_column(String(200), primary_key=True)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)

    song: Mapped["Song"] = relationship(back_populates="parent_genres")


class DetailedGenre(Base):
    __tablename__ = "detailed_genres"

    id: Mapped[str] = mapped_column(String(22), ForeignKey("songs.id"), primary_key=True)
    genre: Mapped[str] = mapped_column(String(200), primary_key=True)
    probability: Mapped[float] = mapped_column(Float, nullable=False)

    song: Mapped["Song"] = relationship(back_populates="detailed_genres")
