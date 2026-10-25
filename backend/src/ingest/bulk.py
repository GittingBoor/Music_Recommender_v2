"""Backend queue for bulk YouTube imports ("Artist - Title" search queries).

One worker thread works through the queue: search YouTube, try up to
``_ATTEMPTS`` hits that are not in the library yet, and record the song in
``ingest_failures`` if none of them made it. Every queued song is visible in
the pipeline tracker from the moment it is enqueued.

Spotify playlist imports use the same queue with an expected track: only
hits that pass ``candidate_fits`` are downloaded, and audio AcoustID knows
as another song is rejected (see src/spotify/matching.py).
"""
import itertools
import json
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from src.ingest.failures import record_failure
from src.ingest.tracker import Stage, tracker
from src.metadata.identity import IdentityHint, MetadataSource
from src.spotify.matching import SpotifyTrack, candidate_fits, order_candidates, trusted_upload
from src.youtube.service import YoutubeSearchResult

logger = logging.getLogger(__name__)

# Hits tried per song when AcoustID does not recognise the audio.
_ATTEMPTS = 3
_SEARCH_LIMIT = 5
# Pause when YouTube starts refusing the server, instead of burning the queue.
_BACKOFF_SECONDS = 300
# A clicked playlist import goes before a long-running chart list.
_SPOTIFY_PRIORITY = 0
_BULK_PRIORITY = 1


@dataclass(frozen=True)
class BulkItem:
    """One queued song. ``expected`` makes it a Spotify import; ``on_done`` gets (result, video_id)."""

    query: str
    label: str
    expected: SpotifyTrack | None = None
    on_done: Callable[[dict, str | None], None] | None = None

    @property
    def source(self) -> str:
        return "spotify" if self.expected is not None else "bulk"

    def finish(self, result: dict, video_id: str | None) -> None:
        """Report the result; a failing callback is logged, it must not stop the queue."""
        if self.on_done is None:
            return
        try:
            self.on_done(result, video_id)
        except Exception:
            logger.exception("[Bulk] Recording the result of %s failed", self.label)


# (priority, enqueue order, job id, item); the order keeps FIFO within a priority.
_queue: "queue.PriorityQueue[tuple[int, int, int, BulkItem]]" = queue.PriorityQueue()
_order = itertools.count()
_cancelled: set[int] = set()
_state_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue(queries: list[str]) -> int:
    """Add search queries to the queue; returns how many were queued."""
    stripped = (q.strip() for q in queries)
    return enqueue_items([BulkItem(query=q, label=q) for q in stripped if q and not q.startswith("#")])


def enqueue_items(items: list[BulkItem]) -> int:
    """Add songs to the queue (Spotify imports ahead of plain bulk queries); returns how many."""
    for item in items:
        priority = _SPOTIFY_PRIORITY if item.expected is not None else _BULK_PRIORITY
        _queue.put((priority, next(_order), tracker.add(item.source, item.label, Stage.QUEUED), item))
    _ensure_worker()
    logger.info("[Bulk] Queued %d songs", len(items))
    return len(items)


def _ensure_worker() -> None:
    global _worker
    with _state_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="bulk-ingest", daemon=True)
            _worker.start()


def cancel_pending() -> int:
    """Drop every plain bulk query that has not started yet; playlist imports stay queued."""
    kept: list[tuple[int, int, int, BulkItem]] = []
    dropped = 0
    while True:
        try:
            entry = _queue.get_nowait()
        except queue.Empty:
            break
        if entry[3].expected is not None:
            kept.append(entry)
            continue
        with _state_lock:
            _cancelled.add(entry[2])
        tracker.remove(entry[2])
        dropped += 1
    for entry in kept:
        _queue.put(entry)
    logger.info("[Bulk] Cancelled %d queued songs", dropped)
    return dropped


def _run() -> None:
    while True:
        _, _, job_id, item = _queue.get()
        with _state_lock:
            if job_id in _cancelled:
                _cancelled.discard(job_id)
                continue
        try:
            if item.expected is not None:
                _process_spotify(job_id, item, _search_youtube, _download_for_track)
            else:
                _process(job_id, item.query)
        except Exception as exc:  # one broken song must not stop the queue
            logger.exception("[Bulk] %s failed", item.label)
            error = {"status": "error", "reason": str(exc)}
            record_failure(item.source, item.label, error)
            item.finish(error, None)
        finally:
            tracker.remove(job_id)


def _process(job_id: int, query: str) -> None:
    # Imported here: the routes import this package's tracker at load time.
    from src.api.routes.youtube import YoutubeDownloadRequest, _download_pipeline, _library_matcher, _service
    from src.db.session import get_session
    from src.youtube.service import YoutubeErrorKind, classify_error

    tracker.update(job_id, stage=Stage.SEARCHING)
    try:
        # Audio-only uploads match AcoustID far more often than music videos
        # with intros, so they are searched first.
        results = _service.search(f"{query} official audio", _SEARCH_LIMIT)
    except Exception as exc:
        error = classify_error(exc)
        record_failure("bulk", query, {"status": "error", "reason": "search_error", "error": error.as_dict()})
        if error.kind in (YoutubeErrorKind.BOT_CHECK, YoutubeErrorKind.RATE_LIMITED):
            logger.warning("[Bulk] YouTube refuses the server (%s) — pausing", error.kind.value)
            time.sleep(_BACKOFF_SECONDS)
        return

    session = get_session()
    try:
        matcher = _library_matcher(session)
    finally:
        session.close()
    hits = [r for r in results if not matcher.contains(r.title, r.uploader)]
    if not results:
        record_failure("bulk", query, {"status": "skipped", "reason": "no_search_hit"})
        return
    if not hits:
        record_failure("bulk", query, {"status": "skipped", "reason": "all_hits_in_library"})
        return

    result: dict = {}
    tried: list[str] = []
    for hit in hits[:_ATTEMPTS]:
        tracker.update(job_id, label=f"{query} — {hit.title}")
        req = YoutubeDownloadRequest(video_id=hit.video_id, title=hit.title, uploader=hit.uploader, query=query)
        for line in _download_pipeline(req, job_id=job_id, log_failures=False):
            event = json.loads(line)
            if event.get("stage") == "done":
                result = event.get("result") or {}
        tried.append(hit.video_id)
        if result.get("status") == "saved" or result.get("reason") == "duplicate":
            break

    if result.get("status") != "saved":
        record_failure("bulk", query, result, tried[-1] if tried else None,
                       note=f"{len(tried)} hit(s) tried: {', '.join(tried)}")


SearchFn = Callable[[str, int], list[YoutubeSearchResult]]
DownloadFn = Callable[[YoutubeSearchResult, BulkItem, int], dict]


def _search_youtube(query: str, limit: int) -> list[YoutubeSearchResult]:
    from src.api.routes.youtube import _service
    return _service.search(query, limit)


def _download_for_track(hit: YoutubeSearchResult, item: BulkItem, job_id: int) -> dict:
    """Download, trim and analyse one hit; the Spotify track names the song and vetoes other songs."""
    from src.api.routes.youtube import YoutubeDownloadRequest, _download_pipeline

    track = item.expected
    if track is None:
        raise ValueError(f"BulkItem {item.label!r} has no expected Spotify track")
    req = YoutubeDownloadRequest(video_id=hit.video_id, title=hit.title, uploader=hit.uploader, query=item.query)
    hint = IdentityHint(title=track.plain_title, artist=track.primary_artist, source=MetadataSource.SPOTIFY)
    result: dict = {}
    trusted = trusted_upload(track, hit.title, hit.uploader)
    for line in _download_pipeline(
        req, job_id=job_id, log_failures=False, hint=hint, expected=track, trust_unrecognised=trusted,
    ):
        event = json.loads(line)
        if event.get("stage") == "done":
            result = event.get("result") or {}
    return result


def _fitting_hits(track: SpotifyTrack, search: SearchFn) -> list[YoutubeSearchResult]:
    """Hits that are plausibly this exact track; the plain query only runs if "official audio" found none."""
    fitting: list[YoutubeSearchResult] = []
    for query in (f"{track.query} official audio", track.query):
        fitting = [h for h in search(query, _SEARCH_LIMIT) if candidate_fits(track, h.title, h.uploader, h.duration)]
        if fitting:
            break
    return order_candidates(track, fitting, key=lambda h: (h.title, h.uploader, h.duration))


def _finish_spotify(item: BulkItem, result: dict, tried: list[str]) -> None:
    if result.get("status") != "saved" and result.get("reason") != "duplicate":
        note = f"{len(tried)} hit(s) tried: {', '.join(tried)}" if tried else None
        record_failure(item.source, item.label, result, tried[-1] if tried else None, note=note)
    item.finish(result, tried[-1] if tried else None)


def _process_spotify(job_id: int, item: BulkItem, search: SearchFn, download: DownloadFn) -> None:
    from src.youtube.service import YoutubeErrorKind, classify_error

    track = item.expected
    if track is None:
        raise ValueError(f"BulkItem {item.label!r} has no expected Spotify track")
    tracker.update(job_id, stage=Stage.SEARCHING)
    try:
        hits = _fitting_hits(track, search)
    except Exception as exc:
        error = classify_error(exc)
        _finish_spotify(item, {"status": "error", "reason": "search_error", "error": error.as_dict()}, [])
        if error.kind in (YoutubeErrorKind.BOT_CHECK, YoutubeErrorKind.RATE_LIMITED):
            logger.warning("[Bulk] YouTube refuses the server (%s) — pausing", error.kind.value)
            time.sleep(_BACKOFF_SECONDS)
        return

    if not hits:
        result = {"status": "skipped", "reason": "no_fitting_hit", "title": track.title, "artist": track.primary_artist}
        _finish_spotify(item, result, [])
        return

    result: dict = {}
    tried: list[str] = []
    for hit in hits[:_ATTEMPTS]:
        tracker.update(job_id, label=f"{item.label} — {hit.title}")
        result = download(hit, item, job_id)
        tried.append(hit.video_id)
        if result.get("status") == "saved" or result.get("reason") == "duplicate":
            break
    _finish_spotify(item, result, tried)
