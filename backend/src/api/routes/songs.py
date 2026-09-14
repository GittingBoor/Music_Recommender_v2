from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from src.analysis.similarity import get_similarity_index
from src.api.deps import get_db
from src.api.routes.audio import resolve_audio_file
from src.db.models import (
    Song,
    FileMetadata,
    TrackMetadata,
    DSPFeatures,
    MLProfileFeatures,
    MLMoodFeatures,
    ParentGenre,
    DetailedGenre,
    Instrument,
    OtherFeatures,
)
from src.schemas.songs import SongResponse

router = APIRouter()


@router.get("/songs/count")
def count_songs(db: Session = Depends(get_db)) -> dict[str, int]:
    """Cheap poll target: lets clients detect library changes without
    downloading the full song list every time."""
    return {"count": db.query(Song).count()}


@router.get("/songs/{song_id}/neighbors")
def get_song_neighbors(song_id: str, db: Session = Depends(get_db)) -> dict[str, list[str]]:
    """Return the most similar songs, closest first.

    Computed over all audio features and independent of the UMAP view's
    current axis selection, so playback recommendations stay stable.
    """
    songs = (
        db.query(Song)
        .options(
            selectinload(Song.dsp_features),
            selectinload(Song.ml_moods),
            selectinload(Song.ml_profile),
        )
        .all()
    )
    if not any(s.id == song_id for s in songs):
        raise HTTPException(status_code=404, detail="Song not found")

    return {"neighbors": get_similarity_index().neighbors_for(song_id, songs)}


@router.get("/songs", response_model=list[SongResponse])
def list_songs(db: Session = Depends(get_db)):
    songs = (
        db.query(Song)
        .options(
            selectinload(Song.file_metadata),
            selectinload(Song.track_metadata),
            selectinload(Song.parent_genres),
            selectinload(Song.detailed_genres),
            selectinload(Song.instruments),
            selectinload(Song.ml_profile),
            selectinload(Song.ml_moods),
            selectinload(Song.dsp_features),
            selectinload(Song.other_features),
        )
        .all()
    )

    result = []
    for song in songs:
        r = SongResponse.model_validate(song)
        # Previews are cut live from the full audio file, so playable == resolvable.
        filename = song.file_metadata.filename if song.file_metadata else None
        r.has_preview = bool(filename) and resolve_audio_file(filename) is not None
        result.append(r)
    return result
