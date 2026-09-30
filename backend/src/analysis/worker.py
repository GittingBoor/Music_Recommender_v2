"""Runs the DSP/ML analysis in a process of its own.

The analysis spends long stretches in native code that keeps Python's global
interpreter lock. Inside the web process that froze every request — audio
streams, the song list, the UMAP — for as long as a song was analysed. In a
separate process it only competes for CPU time, and a crash in the native
libraries takes down the worker instead of the server and its ingest queue.
"""
import logging
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

logger = logging.getLogger(__name__)


class AnalysisWorkerCrashed(RuntimeError):
    """The worker process died while analysing a song."""


def _init_worker() -> None:
    import essentia

    logging.basicConfig(level=logging.INFO)
    # Same as in the web process: Essentia logs a line per analysed frame.
    essentia.log.infoActive = False
    essentia.log.warningActive = False


def _analyse(audio_file: Path, metadata: dict) -> dict[str, object]:
    # Imported in the worker only: loading the models is what makes it heavy.
    from src.analysis.pipeline import run_full_pipeline

    return run_full_pipeline(audio_file, metadata=metadata)


class AnalysisWorker:
    """One long-lived worker process; the models stay loaded between songs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pool: ProcessPoolExecutor | None = None

    def analyse(self, audio_file: Path, metadata: dict) -> dict[str, object]:
        """Analyse one audio file and return the pipeline result.

        Args:
            audio_file: File to analyse.
            metadata: Metadata already looked up for it (title, artist, …).

        Raises:
            AnalysisWorkerCrashed: The worker process died; the next call
                starts a fresh one.
        """
        try:
            return self._executor().submit(_analyse, audio_file, metadata).result()
        except BrokenProcessPool as exc:
            self._discard_pool()
            raise AnalysisWorkerCrashed(
                f"Analysis process died while analysing {audio_file.name}; it is restarted for the next song"
            ) from exc

    def _executor(self) -> ProcessPoolExecutor:
        with self._lock:
            if self._pool is None:
                # spawn, not fork: the web process has threads and loaded native libraries.
                self._pool = ProcessPoolExecutor(
                    max_workers=1,
                    mp_context=multiprocessing.get_context("spawn"),
                    initializer=_init_worker,
                )
            return self._pool

    def _discard_pool(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.shutdown(wait=False)
                self._pool = None


_worker = AnalysisWorker()


def get_analysis_worker() -> AnalysisWorker:
    """Return the process-wide analysis worker."""
    return _worker
