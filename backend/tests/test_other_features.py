from pathlib import Path

import numpy as np
import pytest

from src.analysis import other_features


def _fake_dl_results(_audio: np.ndarray) -> dict:
    return {
        name: {"mean": 0.8, "frames": [0.7, 0.9], "both_classes_mean": [0.8, 0.2]}
        for name in ("voice", "female", "danceability", "tonal")
    }


def test_tonal_is_kept_when_the_gmbi_models_are_missing(monkeypatch: pytest.MonkeyPatch):
    def missing_gmbi(*_args: object) -> dict:
        raise FileNotFoundError("GMBI NN model not found: gmbi_old_nn/valence")

    monkeypatch.setattr(other_features, "_run_dl_models", _fake_dl_results)
    monkeypatch.setattr(other_features, "_extract_gmbi_nn", missing_gmbi)

    result = other_features._extract_model_features(Path("song.mp3"), np.zeros(4), np.zeros(4))

    assert result["tonal"] == {"mean": 0.8, "timeseries": [0.7, 0.9]}
    assert "gmbi" not in result


def test_musicnn_models_come_from_the_model_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    requested: list[str] = []

    class _Manager:
        def ensure_key(self, key: str) -> None:
            requested.append(key)

        def get_path(self, key: str) -> Path:
            return tmp_path / f"{key}.pb"

    monkeypatch.setattr(other_features, "get_manager", lambda: _Manager())

    assert other_features._model_path("tonal") == tmp_path / "musicnn_tonal.pb"
    assert requested == ["musicnn_tonal"]
