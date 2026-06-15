from __future__ import annotations
from pydantic import BaseModel


class UmapPoint2D(BaseModel):
    song_id: str
    x: float
    y: float
    title: str | None = None
    artist: str | None = None


class UmapResponse(BaseModel):
    points_2d: list[UmapPoint2D]
    features_used: list[str]
