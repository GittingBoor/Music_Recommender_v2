import json
import threading
from collections.abc import Iterator

from src.ingest.tracker import tracker
from src.youtube.download_queue import DownloadQueue

_TIMEOUT = 5


def _wait_until_done(queue: DownloadQueue[str], job_id: int) -> None:
    done = threading.Event()
    while not done.wait(0.01):
        job = queue.get(job_id)
        if job is not None and job.result is not None:
            done.set()


def test_jobs_wait_in_the_tracker_until_a_worker_is_free():
    release = threading.Event()

    def runner(request: str, job_id: int) -> Iterator[str]:
        release.wait(_TIMEOUT)
        yield json.dumps({"stage": "done", "progress": 1.0, "result": {"status": "saved", "title": request}}) + "\n"

    queue: DownloadQueue[str] = DownloadQueue(runner, workers=1)
    first = queue.submit("a", "Song A")
    second = queue.submit("b", "Song B")

    assert queue.get(second).stage == "queued"
    assert any(j.id == second for j in tracker.snapshot())

    release.set()
    _wait_until_done(queue, first)
    _wait_until_done(queue, second)
    assert queue.get(second).stage == "done"
    assert queue.get(second).result == {"status": "saved", "title": "b"}
    assert all(j.id not in (first, second) for j in tracker.snapshot())


def test_a_crashing_runner_becomes_an_error_result():
    def runner(request: str, job_id: int) -> Iterator[str]:
        raise RuntimeError("boom")
        yield ""  # pragma: no cover

    queue: DownloadQueue[str] = DownloadQueue(runner, workers=1)
    job_id = queue.submit("a", "Song A")
    _wait_until_done(queue, job_id)
    assert queue.get(job_id).result["status"] == "error"
