import json
import logging
from collections import Counter
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.heartbeat import run_with_heartbeat
from src.api.routes.admin import process_audio_file
from src.api.routes.upload import _safe_name, _unique_path
from src.core.config import settings
from src.db.models import Song
from src.ingest.failures import record_failure
from src.ingest.tracker import Stage, tracker
from src.youtube.library_match import LibraryMatcher
from src.youtube.service import MusicVerdict, YoutubeSearchResult, YoutubeService, classify_error
from src.youtube.trimmer import get_music_trimmer

logger = logging.getLogger(__name__)
router = APIRouter()

_service = YoutubeService()

# YouTube downloads live in the repo's own dataset dir, not user uploads.
_YOUTUBE_DIR = settings.datasets_dir / "youtube"

_EXAMPLE_ATTEMPTS = 3


class YoutubeSearchItem(BaseModel):
    video_id: str
    title: str
    uploader: str | None
    duration: int | None
    thumbnail: str | None
    url: str
    in_library: bool = False


class YoutubePlaylistResponse(BaseModel):
    title: str | None
    items: list[YoutubeSearchItem]


class YoutubePlaylistSearchItem(BaseModel):
    playlist_id: str
    title: str
    uploader: str | None
    thumbnail: str | None
    url: str


class YoutubeDownloadRequest(BaseModel):
    video_id: str
    title: str | None = None


def _library_matcher(db: Session) -> LibraryMatcher:
    return LibraryMatcher([(title, artist) for title, artist in db.query(Song.title, Song.artist).all()])


def _to_items(results: list[YoutubeSearchResult], matcher: LibraryMatcher) -> list[YoutubeSearchItem]:
    return [
        YoutubeSearchItem(**vars(r), in_library=matcher.contains(r.title, r.uploader))
        for r in results
    ]


def _raise_http(exc: Exception) -> None:
    """Translate a YouTube failure into an HTTP error the frontend can explain."""
    error = classify_error(exc)
    raise HTTPException(status_code=502, detail=error.as_dict())


@router.get("/youtube/search", response_model=list[YoutubeSearchItem])
def youtube_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=25),
    db: Session = Depends(get_db),
) -> list[YoutubeSearchItem]:
    """Search YouTube and return matching music videos (no download)."""
    try:
        results = _service.search(q, limit)
    except Exception as exc:
        logger.error("[YouTube] Search failed for %r: %s", q, exc)
        _raise_http(exc)
    return _to_items(results, _library_matcher(db))


@router.get("/youtube/search/stream")
def youtube_search_stream(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=25),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream a music search so hits show up before the slow category checks finish.

    NDJSON events: ``{"type": "results", "items": [...]}`` with every plausible
    hit first, then ``{"type": "rejected", "video_id": ...}`` for each hit
    YouTube confirms is not music, then ``{"type": "done"}``. Hits whose check
    fails (e.g. YouTube's bot check) are kept.
    """
    try:
        candidates = _service.search_candidates(q, limit)
    except Exception as exc:
        logger.error("[YouTube] Search failed for %r: %s", q, exc)
        _raise_http(exc)
    items = _to_items(candidates, _library_matcher(db))
    return StreamingResponse(
        _search_events(items, candidates),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _search_events(
    items: list[YoutubeSearchItem], candidates: list[YoutubeSearchResult]
) -> Iterator[str]:
    yield json.dumps({"type": "results", "items": jsonable_encoder(items)}) + "\n"
    verdicts: Counter[MusicVerdict] = Counter()
    for video_id, verdict in _service.verify_music(candidates):
        verdicts[verdict] += 1
        if verdict is MusicVerdict.NOT_MUSIC:
            yield json.dumps({"type": "rejected", "video_id": video_id}) + "\n"
    logger.info(
        "[YouTube] Verified %d hits: %s",
        len(candidates), {v.value: n for v, n in verdicts.items()},
    )
    yield json.dumps({"type": "done"}) + "\n"


@router.get("/youtube/playlists/search", response_model=list[YoutubePlaylistSearchItem])
def youtube_playlist_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(3, ge=1, le=10),
) -> list[YoutubePlaylistSearchItem]:
    """Search YouTube for playlists (no download; open one via /youtube/playlist)."""
    try:
        hits = _service.search_playlists(q, limit)
    except Exception as exc:
        logger.error("[YouTube] Playlist search failed for %r: %s", q, exc)
        _raise_http(exc)
    return [YoutubePlaylistSearchItem(**vars(h)) for h in hits]


@router.get("/youtube/examples", response_model=list[YoutubeSearchItem])
def youtube_examples(
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
) -> list[YoutubeSearchItem]:
    """Suggest random music videos that are not in the library yet."""
    known = {
        f"{(t or '').strip().lower()}|{(a or '').strip().lower()}"
        for t, a in db.query(Song.title, Song.artist).all()
    }
    known_titles = {k.split("|", 1)[0] for k in known if k.split("|", 1)[0]}

    collected: list = []
    seen: set[str] = set()
    try:
        # Seeds are random per call, so a couple of rounds fills the list even
        # when the first one is mostly songs we already have.
        for _ in range(_EXAMPLE_ATTEMPTS):
            for result in _service.examples(limit):
                if result.video_id in seen:
                    continue
                if _already_known(result.title, known_titles):
                    continue
                seen.add(result.video_id)
                collected.append(result)
            if len(collected) >= limit:
                break
    except Exception as exc:
        logger.error("[YouTube] Examples failed: %s", exc)
        _raise_http(exc)

    return _to_items(collected[:limit], _library_matcher(db))


def _already_known(video_title: str, known_titles: set[str]) -> bool:
    """True when a library song's title appears in the video title."""
    haystack = video_title.lower()
    return any(title and title in haystack for title in known_titles)


@router.get("/youtube/playlist", response_model=YoutubePlaylistResponse)
def youtube_playlist(
    url: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> YoutubePlaylistResponse:
    """Resolve a playlist URL into its music videos (no download)."""
    try:
        title, results = _service.playlist_entries(url, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[YouTube] Playlist failed for %r: %s", url, exc)
        _raise_http(exc)
    return YoutubePlaylistResponse(title=title, items=_to_items(results, _library_matcher(db)))


def _event(stage: str, progress: float, result: dict | None = None) -> str:
    """Serialise one NDJSON progress event."""
    payload: dict = {"stage": stage, "progress": progress}
    if result is not None:
        payload["result"] = result
    return json.dumps(payload) + "\n"


def _error_result(filename: str, reason: str, error: dict | None = None) -> dict:
    return {
        "status": "error",
        "reason": reason,
        "title": None,
        "artist": None,
        "song_id": None,
        "filename": filename,
        "error": error,
    }


def _download_pipeline(
    req: YoutubeDownloadRequest, job_id: int | None = None, log_failures: bool = True
) -> Iterator[str]:
    """Download → trim → analyse, yielding NDJSON progress events.

    Terminal event always has ``stage == "done"`` and carries the result
    (status saved/skipped/error), so the frontend has a single completion path.

    ``job_id`` reuses an existing pipeline-tracker entry (bulk queue); without
    it the download registers and removes its own. ``log_failures=False``
    leaves recording a failure to the caller (bulk tries several hits).
    """
    fallback_name = req.title or req.video_id
    owns_job = job_id is None
    if job_id is None:
        job_id = tracker.add("youtube", fallback_name, Stage.DOWNLOADING)
    try:
        yield from _download_steps(req, fallback_name, job_id, log_failures)
    finally:
        if owns_job:
            tracker.remove(job_id)


def _download_steps(
    req: YoutubeDownloadRequest, fallback_name: str, job_id: int, log_failures: bool
) -> Iterator[str]:
    tracker.update(job_id, stage=Stage.DOWNLOADING)

    # 1) Download audio to datasets/youtube/.
    yield _event("downloading", 0.05)
    try:
        downloaded = _service.download_audio(req.video_id, _YOUTUBE_DIR)
    except Exception as exc:
        error = classify_error(exc)
        logger.error("[YouTube] Download failed for %s: %s", req.video_id, error.raw_message)
        result = _error_result(fallback_name, f"download_error: {error.title}", error.as_dict())
        if log_failures:
            record_failure("youtube", fallback_name, result, req.video_id)
        yield _event("done", 1.0, result)
        return

    # 2) Trim non-music intro/outro (YouTube only).
    yield _event("trimming", 0.45)
    tracker.update(job_id, stage=Stage.TRIMMING)
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
    result: dict = {}
    for outcome in run_with_heartbeat(lambda: process_audio_file(final_path, job_id)):
        if outcome is None:
            yield _event("analyzing", 0.7)  # keep-alive
        else:
            result = outcome
    result["filename"] = fallback_name
    result.setdefault("error", None)
    if log_failures:
        record_failure("youtube", fallback_name, result, req.video_id)

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
