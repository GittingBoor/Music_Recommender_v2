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
)
from src.db.session import get_session
from src.schemas.songs import SongResponse

router = APIRouter()


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/songs", response_model=list[SongResponse])
def list_songs(db: Session = Depends(get_db)):
    return (
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
        )
        .all()
    )
