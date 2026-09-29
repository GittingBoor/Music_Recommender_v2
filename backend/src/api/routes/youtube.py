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
from src.db.session import get_session
from src.ingest.failures import record_failure
from src.ingest.tracker import Stage, tracker
from src.metadata.identity import IdentityHint, MetadataSource, SongOrigin
from src.youtube.download_queue import DownloadQueue
from src.youtube.example_pool import ExamplePool
from src.youtube.library_match import LibraryMatcher
from src.youtube.service import MusicVerdict, YoutubeSearchResult, YoutubeService, classify_error
from src.youtube.title_parser import parse_video_title
from src.youtube.trimmer import get_music_trimmer

logger = logging.getLogger(__name__)
router = APIRouter()

_service = YoutubeService()
_example_pool = ExamplePool(_service)

# YouTube downloads live in the repo's own dataset dir, not user uploads.
_YOUTUBE_DIR = settings.datasets_dir / "youtube"

_EXAMPLE_ATTEMPTS = 3
# Downloads/trims running side by side; the analysis itself stays one at a time.
_PARALLEL_DOWNLOADS = 2


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
    uploader: str | None = None


class YoutubeDownloadQueued(BaseModel):
    job_id: int


class YoutubeDownloadStatus(BaseModel):
    job_id: int
    stage: str
    progress: float
    result: dict | None


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
    """Suggest random music videos that are not in the library yet.

    Served from a pre-verified pool; only a cold pool (right after startup)
    falls back to searching YouTube while the request waits.
    """
    known = {
        f"{(t or '').strip().lower()}|{(a or '').strip().lower()}"
        for t, a in db.query(Song.title, Song.artist).all()
    }
    known_titles = {k.split("|", 1)[0] for k in known if k.split("|", 1)[0]}

    def is_known(result: YoutubeSearchResult) -> bool:
        return _already_known(result.title, known_titles)

    collected = _example_pool.take(limit, is_known)
    seen = {r.video_id for r in collected}
    leftover: list[YoutubeSearchResult] = []
    try:
        # Seeds are random per call, so a couple of rounds fills the list even
        # when the first one is mostly songs we already have.
        for _ in range(_EXAMPLE_ATTEMPTS):
            if len(collected) >= limit:
                break
            for result in _service.examples(limit):
                if result.video_id in seen or is_known(result):
                    continue
                seen.add(result.video_id)
                (collected if len(collected) < limit else leftover).append(result)
    except Exception as exc:
        logger.error("[YouTube] Examples failed: %s", exc)
        if not collected:
            _raise_http(exc)
    _example_pool.add(leftover)

    return _to_items(collected, _library_matcher(db))


def warm_example_pool() -> None:
    """Fill the suggestion pool in the background so the first visitor doesn't wait."""
    _example_pool.refill_async()


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
    # 0) Skip the download when the video title already names a library song.
    known = _library_hit(req)
    if known is not None:
        logger.info("[YouTube] %s is already in the library — not downloading", fallback_name)
        if log_failures:
            record_failure("youtube", fallback_name, known, req.video_id)
        yield _event("done", 1.0, known)
        return

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
    origin = SongOrigin(original_name=fallback_name, youtube_video_id=req.video_id)
    for outcome in run_with_heartbeat(lambda: process_audio_file(final_path, job_id, _title_hint(req), origin)):
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


def _title_hint(req: YoutubeDownloadRequest) -> IdentityHint | None:
    """Artist/title read from the video title, used when AcoustID does not know the audio."""
    parsed = parse_video_title(req.title or "", req.uploader)
    if parsed is None:
        return None
    return IdentityHint(title=parsed.title, artist=parsed.artist, source=MetadataSource.YOUTUBE_TITLE)


def _library_hit(req: YoutubeDownloadRequest) -> dict | None:
    """A "duplicate" result when the video title already names a library song, else None."""
    if not req.title:
        return None
    session = get_session()
    try:
        known = _library_matcher(session).contains(req.title, req.uploader)
    finally:
        session.close()
    if not known:
        return None
    parsed = parse_video_title(req.title, req.uploader)
    return {
        "status": "skipped",
        "reason": "duplicate",
        "title": parsed.title if parsed else None,
        "artist": parsed.artist if parsed else None,
        "song_id": None,
        "filename": req.title,
        "error": None,
    }


def _run_queued_download(req: YoutubeDownloadRequest, job_id: int) -> Iterator[str]:
    return _download_pipeline(req, job_id=job_id)


_downloads: DownloadQueue[YoutubeDownloadRequest] = DownloadQueue(_run_queued_download, _PARALLEL_DOWNLOADS)


@router.post("/youtube/downloads", response_model=YoutubeDownloadQueued)
def youtube_download_enqueue(req: YoutubeDownloadRequest) -> YoutubeDownloadQueued:
    """Queue a video for download, trimming and analysis; poll ``GET /youtube/downloads``."""
    job_id = _downloads.submit(req, req.title or req.video_id)
    return YoutubeDownloadQueued(job_id=job_id)


@router.get("/youtube/downloads", response_model=list[YoutubeDownloadStatus])
def youtube_download_status(ids: list[int] = Query(..., min_length=1)) -> list[YoutubeDownloadStatus]:
    """Stage, progress and — once finished — the result (same shape as ``/api/upload``) per job.

    A job the server no longer knows (e.g. after a restart) comes back as an error result.
    """
    statuses: list[YoutubeDownloadStatus] = []
    for job_id in ids:
        job = _downloads.get(job_id)
        if job is None:
            lost = _error_result("", "job_lost")
            statuses.append(YoutubeDownloadStatus(job_id=job_id, stage="done", progress=1.0, result=lost))
        else:
            statuses.append(YoutubeDownloadStatus(
                job_id=job_id, stage=job.stage, progress=job.progress, result=job.result,
            ))
    return statuses
