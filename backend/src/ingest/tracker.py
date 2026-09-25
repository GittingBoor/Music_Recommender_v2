"""In-memory view of everything currently in the ingest pipeline.

Uploads, YouTube downloads and the bulk queue register their songs here so
the Upload page can list what is still waiting, downloading or being
analysed. The state lives in the process (uvicorn runs a single worker), so
it starts empty after a restart.
"""
import itertools
import threading
import time
from dataclasses import dataclass
from enum import Enum


class Stage(str, Enum):
    QUEUED = "queued"            # bulk queue, not started yet
    SEARCHING = "searching"      # bulk: looking for a YouTube hit
    DOWNLOADING = "downloading"
    TRIMMING = "trimming"
    WAITING = "waiting"          # audio ready, waiting for the analysis lock
    ANALYZING = "analyzing"


# Order on the Upload page: whatever is running first, the queue last.
_STAGE_ORDER = {
    Stage.ANALYZING: 0,
    Stage.TRIMMING: 1,
    Stage.DOWNLOADING: 2,
    Stage.SEARCHING: 3,
    Stage.WAITING: 4,
    Stage.QUEUED: 5,
}


@dataclass
class PipelineJob:
    id: int
    source: str  # "upload" | "youtube" | "bulk"
    label: str
    stage: Stage
    created_at: float
    stage_since: float


class PipelineTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[int, PipelineJob] = {}
        self._ids = itertools.count(1)

    def add(self, source: str, label: str, stage: Stage = Stage.QUEUED) -> int:
        now = time.time()
        with self._lock:
            job_id = next(self._ids)
            self._jobs[job_id] = PipelineJob(job_id, source, label, stage, now, now)
        return job_id

    def update(self, job_id: int, *, stage: Stage | None = None, label: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if stage is not None and stage != job.stage:
                job.stage = stage
                job.stage_since = time.time()
            if label:
                job.label = label

    def remove(self, job_id: int) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def snapshot(self) -> list[PipelineJob]:
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted(jobs, key=lambda j: (_STAGE_ORDER[j.stage], j.id))


tracker = PipelineTracker()
