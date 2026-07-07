from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from src.api.deps import get_db
from src.core.config import settings
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
        r.has_preview = (settings.short_audio_dir / f"{song.id}.mp3").exists()
        result.append(r)
    return result
