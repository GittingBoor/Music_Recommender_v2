import logging
import threading
from dataclasses import dataclass

import numpy as np
from sklearn.preprocessing import StandardScaler
from umap import UMAP

logger = logging.getLogger(__name__)

MIN_FIT_SONGS = 10  # Show a first preview once we have this many songs

FEATURE_DEFINITIONS: dict[str, tuple[str, str]] = {
    "bpm": ("dsp_features", "bpm"),
    "beat_confidence": ("dsp_features", "beat_confidence"),
    "danceability": ("dsp_features", "danceability"),
    "onset_rate": ("dsp_features", "onset_rate"),
    "key_strength": ("dsp_features", "key_strength"),
    "chord_strength_mean": ("dsp_features", "chord_strength_mean"),
    "chord_change_rate": ("dsp_features", "chord_change_rate"),
    "integrated_lufs": ("dsp_features", "integrated_lufs"),
    "loudness_range_lu": ("dsp_features", "loudness_range_lu"),
    "dynamic_complexity": ("dsp_features", "dynamic_complexity"),
    "loudness_db": ("dsp_features", "loudness_db"),
    "spectral_centroid_mean": ("dsp_features", "spectral_centroid_mean"),
    "spectral_rolloff_mean": ("dsp_features", "spectral_rolloff_mean"),
    "spectral_flux_mean": ("dsp_features", "spectral_flux_mean"),
    "zero_crossing_rate": ("dsp_features", "zero_crossing_rate"),
    "dissonance": ("dsp_features", "dissonance"),
    "happy": ("ml_moods", "happy"),
    "sad": ("ml_moods", "sad"),
    "aggressive": ("ml_moods", "aggressive"),
    "party": ("ml_moods", "party"),
    "relaxed": ("ml_moods", "relaxed"),
    "acoustic": ("ml_moods", "acoustic"),
    "electronic": ("ml_moods", "electronic"),
    "arousal": ("ml_profile", "arousal"),
    "valence": ("ml_profile", "valence"),
    "approachability_score": ("ml_profile", "approachability_score"),
    "engagement_score": ("ml_profile", "engagement_score"),
    "voice_score": ("ml_profile", "voice_score"),
}

ALL_FEATURES: list[str] = list(FEATURE_DEFINITIONS.keys())


@dataclass
class UmapPoint2D:
    song_id: str
    x: float
    y: float
    title: str | None
    artist: str | None


@dataclass
class UmapPoint3D:
    song_id: str
    x: float
    y: float
    z: float
    title: str | None
    artist: str | None


def _get_value(song: object, relation: str, attr: str) -> float | None:
    rel = getattr(song, relation, None)
    if rel is None:
        return None
    val = getattr(rel, attr, None)
    return float(val) if val is not None else None


def _build_feature_matrix(songs: list, feature_keys: list[str]) -> np.ndarray:
    rows = []
    for song in songs:
        row = [
            _get_value(song, *FEATURE_DEFINITIONS[key]) or np.nan
            for key in feature_keys
        ]
        rows.append(row)

    matrix = np.array(rows, dtype=float)
    for col_idx in range(matrix.shape[1]):
        col_mean = np.nanmean(matrix[:, col_idx])
        if np.isnan(col_mean):
            col_mean = 0.0
        matrix[np.isnan(matrix[:, col_idx]), col_idx] = col_mean

    return matrix


class UmapState:
    """
    Global singleton that holds fitted UMAP models and current embeddings.

    fit()      — initial fit on all existing songs.
    add_songs() — projects new songs into the existing space via transform().
    reset()    — clears everything (called when DB is cleared).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reducer_2d: UMAP | None = None
        self._reducer_3d: UMAP | None = None
        self._scaler: StandardScaler | None = None
        self._feature_keys: list[str] = []
        self._coords_2d: dict[str, tuple[float, float]] = {}
        self._coords_3d: dict[str, tuple[float, float, float]] = {}
        self._meta: dict[str, tuple[str | None, str | None]] = {}

    # ── public properties ──────────────────────────────────────────────────

    @property
    def is_fitted(self) -> bool:
        return self._reducer_2d is not None

    @property
    def song_count(self) -> int:
        return len(self._coords_2d)

    @property
    def feature_keys(self) -> list[str]:
        return list(self._feature_keys)

    def has_song(self, song_id: str) -> bool:
        return song_id in self._coords_2d

    # ── public methods ─────────────────────────────────────────────────────

    def fit(self, songs: list, feature_keys: list[str]) -> None:
        """Fit UMAP from scratch on all given songs."""
        if len(songs) < 3:
            return

        keys = [k for k in feature_keys if k in FEATURE_DEFINITIONS]
        logger.info("[UMAP] Fitting on %d songs × %d features", len(songs), len(keys))

        matrix = _build_feature_matrix(songs, keys)
        scaler = StandardScaler()
        matrix_scaled = scaler.fit_transform(matrix)

        n_neighbors = min(15, len(songs) - 1)
        reducer_2d = UMAP(n_components=2, random_state=42, n_neighbors=n_neighbors)
        coords_2d = reducer_2d.fit_transform(matrix_scaled)
        reducer_3d = UMAP(n_components=3, random_state=42, n_neighbors=n_neighbors)
        coords_3d = reducer_3d.fit_transform(matrix_scaled)

        with self._lock:
            self._reducer_2d = reducer_2d
            self._reducer_3d = reducer_3d
            self._scaler = scaler
            self._feature_keys = keys
            self._coords_2d = {
                s.id: (float(coords_2d[i, 0]), float(coords_2d[i, 1]))
                for i, s in enumerate(songs)
            }
            self._coords_3d = {
                s.id: (float(coords_3d[i, 0]), float(coords_3d[i, 1]), float(coords_3d[i, 2]))
                for i, s in enumerate(songs)
            }
            self._meta = {s.id: (s.title, s.artist) for s in songs}

        logger.info("[UMAP] Fit complete")

    def add_songs(self, songs: list) -> None:
        """Project new songs into the existing embedding via transform()."""
        if not songs or not self.is_fitted:
            return

        new_songs = [s for s in songs if not self.has_song(s.id)]
        if not new_songs:
            return

        matrix = _build_feature_matrix(new_songs, self._feature_keys)
        matrix_scaled = self._scaler.transform(matrix)  # type: ignore[union-attr]
        coords_2d = self._reducer_2d.transform(matrix_scaled)  # type: ignore[union-attr]
        coords_3d = self._reducer_3d.transform(matrix_scaled)  # type: ignore[union-attr]

        with self._lock:
            for i, song in enumerate(new_songs):
                self._coords_2d[song.id] = (float(coords_2d[i, 0]), float(coords_2d[i, 1]))
                self._coords_3d[song.id] = (
                    float(coords_3d[i, 0]),
                    float(coords_3d[i, 1]),
                    float(coords_3d[i, 2]),
                )
                self._meta[song.id] = (song.title, song.artist)

        logger.info("[UMAP] Added %d song(s) via transform", len(new_songs))

    def reset(self) -> None:
        with self._lock:
            self._reducer_2d = None
            self._reducer_3d = None
            self._scaler = None
            self._feature_keys = []
            self._coords_2d.clear()
            self._coords_3d.clear()
            self._meta.clear()
        logger.info("[UMAP] State reset")

    def get_result(self) -> tuple[list[UmapPoint2D], list[UmapPoint3D]]:
        with self._lock:
            points_2d = [
                UmapPoint2D(
                    song_id=sid,
                    x=c[0],
                    y=c[1],
                    title=self._meta[sid][0],
                    artist=self._meta[sid][1],
                )
                for sid, c in self._coords_2d.items()
            ]
            points_3d = [
                UmapPoint3D(
                    song_id=sid,
                    x=c[0],
                    y=c[1],
                    z=c[2],
                    title=self._meta[sid][0],
                    artist=self._meta[sid][1],
                )
                for sid, c in self._coords_3d.items()
            ]
        return points_2d, points_3d


# Module-level singleton shared by all routes and background tasks
_state = UmapState()


def get_umap_state() -> UmapState:
    return _state
