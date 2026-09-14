from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.analysis.chorus import get_chorus_locator
from src.api.deps import get_db
from src.core.config import SUPPORTED_AUDIO_EXTENSIONS, settings
from src.db.models import DSPFeatures, FileMetadata
from src.schemas.songs import PreviewSegmentSchema

router = APIRouter()

# Lazy-built cache: basename (lowercase) -> first matching Path in datasets/
_datasets_index: dict[str, Path] | None = None


def _get_datasets_index() -> dict[str, Path]:
    global _datasets_index
    if _datasets_index is None:
        _datasets_index = {}
        if settings.datasets_dir.exists():
            for p in settings.datasets_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                    key = p.name.lower()
                    if key not in _datasets_index:
                        _datasets_index[key] = p
    return _datasets_index


def resolve_audio_file(basename: str) -> Path | None:
    """Return the full Path for a given basename (case-insensitive), or None."""
    idx = _get_datasets_index()
    return idx.get(basename.lower())


_MEDIA_TYPES: dict[str, str] = {
    ".mp3":  "audio/mpeg",
    ".wav":  "audio/wav",
    ".flac": "audio/flac",
    ".ogg":  "audio/ogg",
    ".aiff": "audio/aiff",
    ".m4a":  "audio/mp4",
}


@router.get("/audio/preview/{song_id}", response_model=PreviewSegmentSchema)
def get_preview_segment(song_id: str, db: Session = Depends(get_db)):
    """Return the most recognisable segment (chorus) of a song, in seconds.

    The client plays the full audio file and seeks to this offset, so no
    separate preview file has to be cut.
    """
    dsp = db.get(DSPFeatures, song_id)
    meta = db.get(FileMetadata, song_id)
    if dsp is None or meta is None or not meta.duration_seconds:
        raise HTTPException(status_code=404, detail="No analysis data for this song")

    segment = get_chorus_locator().locate(
        [
            dsp.loudness_short_term_timeseries,
            dsp.spectral_flux_timeseries,
            dsp.spectral_centroid_timeseries,
            dsp.spectral_rolloff_timeseries,
            dsp.zero_crossing_rate_timeseries,
            dsp.dissonance_timeseries,
        ],
        float(meta.duration_seconds),
    )
    if segment is None:
        raise HTTPException(status_code=404, detail="No timeseries data for this song")

    return PreviewSegmentSchema(
        start_seconds=segment.start_seconds,
        duration_seconds=segment.duration_seconds,
    )


@router.get("/audio/full/{song_id}")
def get_full_audio(song_id: str, db: Session = Depends(get_db)):
    """Stream the full audio file for a song from the local datasets directory."""
    meta = db.get(FileMetadata, song_id)
    if not meta or not meta.filename:
        raise HTTPException(status_code=404, detail="No file metadata found")

    path = resolve_audio_file(meta.filename)
    if path is None:
        # Index might be stale (new file ingested after startup) — rebuild once and retry
        global _datasets_index
        _datasets_index = None
        path = resolve_audio_file(meta.filename)

    if path is None:
        raise HTTPException(status_code=404, detail=f"Audio file not found: {meta.filename}")

    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "audio/mpeg")
    return FileResponse(str(path), media_type=media_type)
