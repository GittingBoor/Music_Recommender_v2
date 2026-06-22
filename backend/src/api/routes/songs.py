from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

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
from src.db.session import get_session
from src.schemas.songs import SongResponse

router = APIRouter()

_SHORT_AUDIO_DIR = Path(__file__).resolve().parent.parent.parent.parent / "short_audio"


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


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
        r.has_preview = (_SHORT_AUDIO_DIR / f"{song.id}.mp3").exists()
        result.append(r)
    return result
