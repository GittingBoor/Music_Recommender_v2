from __future__ import annotations
from pydantic import BaseModel


class UmapPoint2D(BaseModel):
    song_id: str
    x: float
    y: float
    title: str | None = None
    artist: str | None = None


class UmapPoint3D(BaseModel):
    song_id: str
    x: float
    y: float
    z: float
    title: str | None = None
    artist: str | None = None


class UmapResponse(BaseModel):
    points_2d: list[UmapPoint2D]
    points_3d: list[UmapPoint3D]
    features_used: list[str]
