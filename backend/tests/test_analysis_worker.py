import os
from pathlib import Path

import pytest

from src.analysis import worker
from src.analysis.worker import AnalysisWorker, AnalysisWorkerCrashed


def _report_pid(audio_file: Path, metadata: dict) -> dict[str, object]:
    return {"pid": os.getpid(), "metadata": metadata}


def _die(audio_file: Path, metadata: dict) -> dict[str, object]:
    os._exit(0)


@pytest.fixture(autouse=True)
def _no_essentia_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "_init_worker", None)


def test_analysis_runs_outside_the_calling_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "_analyse", _report_pid)

    result = AnalysisWorker().analyse(Path("song.mp3"), {"title": "Get Lucky"})

    assert result["pid"] != os.getpid()
    assert result["metadata"] == {"title": "Get Lucky"}


def test_a_dying_worker_fails_the_song_and_is_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = AnalysisWorker()
    monkeypatch.setattr(worker, "_analyse", _die)
    with pytest.raises(AnalysisWorkerCrashed):
        analysis.analyse(Path("song.mp3"), {})

    monkeypatch.setattr(worker, "_analyse", _report_pid)
    assert analysis.analyse(Path("next.mp3"), {})["pid"] != os.getpid()
