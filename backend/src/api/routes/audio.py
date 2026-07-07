from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.core.config import SUPPORTED_AUDIO_EXTENSIONS, settings
from src.db.models import FileMetadata

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


def _resolve_audio_file(basename: str) -> Path | None:
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


@router.get("/audio/{song_id}")
def get_audio_preview(song_id: str):
    path = settings.short_audio_dir / f"{song_id}.mp3"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No preview available")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/audio/full/{song_id}")
def get_full_audio(song_id: str, db: Session = Depends(get_db)):
    """Stream the full audio file for a song from the local datasets directory."""
    meta = db.get(FileMetadata, song_id)
    if not meta or not meta.filename:
        raise HTTPException(status_code=404, detail="No file metadata found")

    path = _resolve_audio_file(meta.filename)
    if path is None:
        # Index might be stale (new file ingested after startup) — rebuild once and retry
        global _datasets_index
        _datasets_index = None
        path = _resolve_audio_file(meta.filename)

    if path is None:
        raise HTTPException(status_code=404, detail=f"Audio file not found: {meta.filename}")

    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "audio/mpeg")
    return FileResponse(str(path), media_type=media_type)
