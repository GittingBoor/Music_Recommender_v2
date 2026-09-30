from __future__ import annotations
from pydantic import BaseModel


class UmapPoint2D(BaseModel):
    song_id: str
    x: float
    y: float
    title: str | None = None
    artist: str | None = None
    # Nearest neighbours in the high-dimensional feature space, closest first.
    neighbors: list[str] = []


class UmapResponse(BaseModel):
    points_2d: list[UmapPoint2D]
    features_used: list[str]


class UmapStatusResponse(BaseModel):
    # "empty" | "fitting" | "ready"
    phase: str
    elapsed_seconds: float
    # Duration of the previous fit (a fixed guess before the first one).
    estimated_seconds: float
    song_count: int
