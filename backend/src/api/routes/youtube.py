import json
import logging
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.routes.admin import _DATASETS_DIR, process_audio_file
from src.api.routes.upload import _safe_name, _unique_path
from src.youtube.service import YoutubeService
from src.youtube.trimmer import get_music_trimmer

logger = logging.getLogger(__name__)
router = APIRouter()

_service = YoutubeService()

# YouTube downloads live in the repo's own dataset dir, not user uploads.
_YOUTUBE_DIR = _DATASETS_DIR / "youtube"


class YoutubeSearchItem(BaseModel):
    video_id: str
    title: str
    uploader: str | None
    duration: int | None
    thumbnail: str | None
    url: str


class YoutubeDownloadRequest(BaseModel):
    video_id: str
    title: str | None = None


@router.get("/youtube/search", response_model=list[YoutubeSearchItem])
def youtube_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=25),
) -> list[YoutubeSearchItem]:
    """Search YouTube and return matching videos (no download)."""
    try:
        results = _service.search(q, limit)
    except Exception as exc:
        logger.error("[YouTube] Search failed for %r: %s", q, exc)
        raise HTTPException(status_code=502, detail=f"YouTube search failed: {exc}")
    return [YoutubeSearchItem(**vars(r)) for r in results]


def _event(stage: str, progress: float, result: dict | None = None) -> str:
    """Serialise one NDJSON progress event."""
    payload: dict = {"stage": stage, "progress": progress}
    if result is not None:
        payload["result"] = result
    return json.dumps(payload) + "\n"


def _error_result(filename: str, reason: str) -> dict:
    return {
        "status": "error",
        "reason": reason,
        "title": None,
        "artist": None,
        "song_id": None,
        "filename": filename,
    }


def _download_pipeline(req: YoutubeDownloadRequest) -> Iterator[str]:
    """Download → trim → analyse, yielding NDJSON progress events.

    Terminal event always has ``stage == "done"`` and carries the result
    (status saved/skipped/error), so the frontend has a single completion path.
    """
    fallback_name = req.title or req.video_id

    # 1) Download audio to datasets/youtube/.
    yield _event("downloading", 0.05)
    try:
        downloaded = _service.download_audio(req.video_id, _YOUTUBE_DIR)
    except Exception as exc:
        logger.error("[YouTube] Download failed for %s: %s", req.video_id, exc)
        yield _event("done", 1.0, _error_result(fallback_name, f"download_error: {exc}"))
        return

    # 2) Trim non-music intro/outro (YouTube only).
    yield _event("trimming", 0.45)
    final_path = _unique_path(_YOUTUBE_DIR, _safe_name(f"{fallback_name}.mp3"))
    trimmed = False
    try:
        trimmed = get_music_trimmer().trim_to(downloaded, final_path)
    except Exception as exc:
        logger.error("[YouTube] Trim failed for %s: %s", req.video_id, exc)

    if trimmed:
        downloaded.unlink(missing_ok=True)
    else:
        downloaded.rename(final_path)  # fall back to the untrimmed download

    # 3) Run the full analysis pipeline and save to the database.
    yield _event("analyzing", 0.7)
    result = process_audio_file(final_path)
    result["filename"] = fallback_name

    # Only successfully analysed files stay on disk.
    if result["status"] != "saved":
        try:
            final_path.unlink(missing_ok=True)
        except Exception:
            pass

    yield _event("done", 1.0, result)


@router.post("/youtube/download")
def youtube_download(req: YoutubeDownloadRequest) -> StreamingResponse:
    """Stream progress while downloading, trimming and analysing a video.

    Emits newline-delimited JSON events; the final event carries the same
    result shape as ``/api/upload``.
    """
    return StreamingResponse(
        _download_pipeline(req),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
