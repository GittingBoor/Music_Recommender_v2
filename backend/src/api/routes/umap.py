import logging
import threading
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from src.analysis.umap_generator import ALL_FEATURES, UmapState, get_umap_state
from src.api.deps import get_db
from src.db.models import Song
from src.db.session import get_session
from src.schemas.umap import UmapPoint2D, UmapResponse, UmapStatusResponse

logger = logging.getLogger(__name__)
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


def _warm_umap() -> None:
    session = get_session()
    try:
        get_umap_state().ensure_fitted(lambda: _load_songs_for_umap(session), ALL_FEATURES)
    except Exception:
        logger.exception("[UMAP] Warm-up fit failed; the first request will fit instead")
    finally:
        session.close()


def warm_umap() -> None:
    """Fit the default embedding in the background right after startup.

    The first fit takes long (it compiles UMAP's numba code), so it should be
    finished before someone opens the UMAP view rather than start then.
    """
    threading.Thread(target=_warm_umap, name="umap-warmup", daemon=True).start()


def _to_response(state: UmapState, fallback_keys: list[str]) -> UmapResponse:
    if not state.is_fitted:
        return UmapResponse(points_2d=[], features_used=fallback_keys)
    return UmapResponse(
        points_2d=[UmapPoint2D(**asdict(p)) for p in state.get_result()],
        features_used=state.feature_keys,
    )


@router.get("/umap/status", response_model=UmapStatusResponse)
def get_umap_status() -> UmapStatusResponse:
    """Progress of the default (all features) embedding, for the loading bar."""
    status = get_umap_state().status()
    return UmapStatusResponse(
        phase=status.phase.value,
        elapsed_seconds=status.elapsed_seconds,
        estimated_seconds=status.estimated_seconds,
        song_count=status.song_count,
    )


@router.get("/umap", response_model=UmapResponse)
def get_umap(
    features: str | None = Query(default=None, description="Comma-separated feature keys"),
    db: Session = Depends(get_db),
):
    requested_keys = [f.strip() for f in features.split(",")] if features else ALL_FEATURES

    if set(requested_keys) == set(ALL_FEATURES):
        # The shared embedding: fitted once, then only extended by new songs.
        state = get_umap_state()
        state.ensure_fitted(lambda: _load_songs_for_umap(db), ALL_FEATURES)
        return _to_response(state, requested_keys)

    # A custom axis selection gets its own short-lived fit, so it cannot
    # replace the shared embedding other visitors are looking at.
    custom = UmapState()
    custom.fit(_load_songs_for_umap(db), requested_keys)
    return _to_response(custom, requested_keys)
