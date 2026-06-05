from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

_SHORT_AUDIO_DIR = Path(__file__).resolve().parent.parent.parent.parent / "short_audio"


@router.get("/audio/{song_id}")
def get_audio_preview(song_id: str):
    path = _SHORT_AUDIO_DIR / f"{song_id}.mp3"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No preview available")
    return FileResponse(path, media_type="audio/mpeg")
