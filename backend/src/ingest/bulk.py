"""Backend queue for bulk YouTube imports ("Artist - Title" search queries).

One worker thread works through the queue: search YouTube, try up to
``_ATTEMPTS`` hits that are not in the library yet, and record the song in
``ingest_failures`` if none of them made it. Every queued song is visible in
the pipeline tracker from the moment it is enqueued.
"""
import json
import logging
import queue
import threading
import time

from src.ingest.failures import record_failure
from src.ingest.tracker import Stage, tracker

logger = logging.getLogger(__name__)

# Hits tried per song when AcoustID does not recognise the audio.
_ATTEMPTS = 3
_SEARCH_LIMIT = 5
# Pause when YouTube starts refusing the server, instead of burning the queue.
_BACKOFF_SECONDS = 300

_queue: "queue.Queue[tuple[int, str]]" = queue.Queue()
_cancelled: set[int] = set()
_state_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue(queries: list[str]) -> int:
    """Add search queries to the queue; returns how many were queued."""
    global _worker
    added = 0
    for q in queries:
        q = q.strip()
        if not q or q.startswith("#"):
            continue
        _queue.put((tracker.add("bulk", q, Stage.QUEUED), q))
        added += 1
    with _state_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="bulk-ingest", daemon=True)
            _worker.start()
    logger.info("[Bulk] Queued %d songs", added)
    return added


def cancel_pending() -> int:
    """Drop every song that has not started yet; the running one finishes."""
    dropped = 0
    while True:
        try:
            job_id, _ = _queue.get_nowait()
        except queue.Empty:
            break
        with _state_lock:
            _cancelled.add(job_id)
        tracker.remove(job_id)
        dropped += 1
    logger.info("[Bulk] Cancelled %d queued songs", dropped)
    return dropped


def _run() -> None:
    while True:
        job_id, query = _queue.get()
        with _state_lock:
            if job_id in _cancelled:
                _cancelled.discard(job_id)
                continue
        try:
            _process(job_id, query)
        except Exception as exc:  # one broken song must not stop the queue
            logger.exception("[Bulk] %s failed", query)
            record_failure("bulk", query, {"status": "error", "reason": str(exc)})
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
        req = YoutubeDownloadRequest(video_id=hit.video_id, title=hit.title)
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
