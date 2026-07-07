from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from src.analysis.umap_generator import ALL_FEATURES, get_umap_state
from src.api.deps import get_db
from src.db.models import Song
from src.schemas.umap import UmapPoint2D, UmapResponse

router = APIRouter()


def _load_songs_for_umap(db: Session) -> list:
    return (
        db.query(Song)
        .options(
            selectinload(Song.dsp_features),
            selectinload(Song.ml_moods),
            selectinload(Song.ml_profile),
        )
        .all()
    )


@router.get("/umap", response_model=UmapResponse)
def get_umap(
    features: str | None = Query(default=None, description="Comma-separated feature keys"),
    db: Session = Depends(get_db),
):
    state = get_umap_state()
    requested_keys = [f.strip() for f in features.split(",")] if features else ALL_FEATURES

    features_changed = features is not None and set(requested_keys) != set(state.feature_keys)

    # Fit from scratch if: not fitted yet, or user requested different features
    if not state.is_fitted or features_changed:
        songs = _load_songs_for_umap(db)
        if songs:
            state.fit(songs, requested_keys)

    if not state.is_fitted:
        return UmapResponse(points_2d=[], features_used=requested_keys)

    points_2d = state.get_result()
    return UmapResponse(
        points_2d=[UmapPoint2D(**asdict(p)) for p in points_2d],
        features_used=state.feature_keys,
    )
