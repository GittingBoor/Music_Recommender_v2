from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base


class ParentGenre(Base):
    __tablename__ = "parent_genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False)

    genre: Mapped[str] = mapped_column(String(200), nullable=False)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)

    song: Mapped["Song"] = relationship(back_populates="parent_genres")


class DetailedGenre(Base):
    __tablename__ = "detailed_genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False)

    genre: Mapped[str] = mapped_column(String(200), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    song: Mapped["Song"] = relationship(back_populates="detailed_genres")
