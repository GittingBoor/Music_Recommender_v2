from pathlib import Path

import pytest

from src.analysis import pipeline
from src.api.routes import admin

_META = {"title": "Get Lucky", "artist": "Daft Punk", "acoustid_id": "rec-1"}


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Stub the slow steps; record whether the analysis lock was held during each."""
    held: dict[str, bool] = {}

    def precheck(audio: Path, hint: object) -> tuple[None, dict, str]:
        held["metadata"] = admin._ANALYSIS_LOCK.locked()
        return None, dict(_META), "song-1"

    def analyse(audio: Path, metadata: dict | None = None) -> dict:
        held["analysis"] = admin._ANALYSIS_LOCK.locked()
        return {"metadata": metadata}

    monkeypatch.setattr(pipeline, "precheck_skip", precheck)
    monkeypatch.setattr(pipeline, "run_full_pipeline", analyse)
    monkeypatch.setattr(pipeline, "_save_to_database", lambda result, audio, origin=None: None)
    monkeypatch.setattr(admin, "_get_duration_seconds", lambda audio: 200.0)
    monkeypatch.setattr(admin, "_update_umap_for_song", lambda song_id: None)
    monkeypatch.setattr(admin, "_already_saved", lambda song_id, acoustid_id: False)
    return held


def test_metadata_lookup_runs_outside_the_analysis_lock(calls: dict[str, bool]):
    result = admin.process_audio_file(Path("song.mp3"))
    assert result["status"] == "saved"
    assert calls == {"metadata": False, "analysis": True}


def test_a_song_saved_meanwhile_is_not_analysed_twice(calls: dict[str, bool], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(admin, "_already_saved", lambda song_id, acoustid_id: True)
    result = admin.process_audio_file(Path("song.mp3"))
    assert result["status"] == "skipped" and result["reason"] == "duplicate"
    assert "analysis" not in calls
