"""Server-side queue for YouTube downloads started from the Upload page.

The browser only submits a video and polls its status, so any number of
downloads can be queued at once without holding a connection open per song.
Every job shows up in the pipeline tracker from the moment it is queued.
"""
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Generic, TypeVar

from src.ingest.tracker import Stage, tracker

logger = logging.getLogger(__name__)

# Finished jobs are kept this long so the page can pick up their result.
_RESULT_TTL_SECONDS = 3600

# Runs one download (``(request, job_id) -> NDJSON progress lines``); the last
# line has stage "done" and carries the result.
R = TypeVar("R")
DownloadRunner = Callable[[R, int], Iterator[str]]


@dataclass
class DownloadJob:
    """Progress of one queued download as the Upload page sees it."""

    job_id: int
    progress: float = 0.0
    result: dict | None = None
    finished_at: float | None = None

    @property
    def stage(self) -> str:
        if self.result is not None:
            return "done"
        return tracker.stage_of(self.job_id) or Stage.QUEUED.value


class DownloadQueue(Generic[R]):
    """Run submitted downloads on a small worker pool; analysis stays serialised downstream."""

    def __init__(self, runner: DownloadRunner[R], workers: int) -> None:
        self._runner = runner
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="yt-download")
        self._jobs: dict[int, DownloadJob] = {}
        self._lock = threading.Lock()

    def submit(self, request: R, label: str) -> int:
        """Queue ``request`` and return its job id (also its pipeline-tracker id)."""
        job_id = tracker.add("youtube", label, Stage.QUEUED)
        job = DownloadJob(job_id)
        with self._lock:
            self._prune()
            self._jobs[job_id] = job
        self._pool.submit(self._run, job, request)
        return job_id

    def get(self, job_id: int) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job: DownloadJob, request: R) -> None:
        result: dict = {}
        try:
            for line in self._runner(request, job.job_id):
                event = json.loads(line)
                job.progress = float(event.get("progress") or 0.0)
                if event.get("stage") == "done":
                    result = event.get("result") or {}
        except Exception as exc:  # one broken download must not kill the worker
            logger.exception("[YouTube] Queued download %d failed", job.job_id)
            result = {"status": "error", "reason": str(exc), "title": None, "artist": None, "song_id": None}
        finally:
            tracker.remove(job.job_id)
            job.progress = 1.0
            job.result = result
            job.finished_at = time.time()

    def _prune(self) -> None:
        cutoff = time.time() - _RESULT_TTL_SECONDS
        stale = [i for i, j in self._jobs.items() if j.finished_at is not None and j.finished_at < cutoff]
        for job_id in stale:
            del self._jobs[job_id]
