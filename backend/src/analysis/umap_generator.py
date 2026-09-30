import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from umap import UMAP

logger = logging.getLogger(__name__)

MIN_FIT_SONGS = 10  # Show a first preview once we have this many songs
NEIGHBOR_COUNT = 5  # Nearest neighbours reported per song
# Guess for the first fit after a start, which also compiles UMAP's numba code.
FIRST_FIT_ESTIMATE_SECONDS = 30.0

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
    "mainstream_score": ("ml_profile", "mainstream_score"),
    "active_score": ("ml_profile", "active_score"),
    "vocal_score": ("ml_profile", "vocal_score"),
}

ALL_FEATURES: list[str] = list(FEATURE_DEFINITIONS.keys())


class FitPhase(str, Enum):
    EMPTY = "empty"      # nothing fitted yet
    FITTING = "fitting"  # a fit is running
    READY = "ready"      # embedding available


@dataclass(frozen=True)
class FitStatus:
    """Where the embedding stands; the estimate is the duration of the last fit."""

    phase: FitPhase
    elapsed_seconds: float
    estimated_seconds: float
    song_count: int


@dataclass
class UmapPoint2D:
    song_id: str
    x: float
    y: float
    title: str | None
    artist: str | None
    neighbors: list[str]


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
    Global singleton that holds a fitted UMAP model and current 2D embeddings.

    fit()       — initial fit on all existing songs.
    add_songs() — projects new songs into the existing space via transform().
    reset()     — clears everything (called when DB is cleared).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Held for a whole fit, so parallel requests wait instead of fitting twice.
        self._fit_lock = threading.Lock()
        self._fit_started_at: float | None = None
        self._last_fit_seconds: float | None = None
        self._reducer_2d: UMAP | None = None
        self._scaler: StandardScaler | None = None
        self._feature_keys: list[str] = []
        self._coords_2d: dict[str, tuple[float, float]] = {}
        self._meta: dict[str, tuple[str | None, str | None]] = {}
        self._matrix_scaled: np.ndarray | None = None
        self._song_ids: list[str] = []
        self._neighbors: dict[str, list[str]] = {}

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

    def status(self) -> FitStatus:
        """Report whether the embedding is ready, and how far a running fit is."""
        started_at = self._fit_started_at
        if started_at is not None:
            phase = FitPhase.FITTING
        else:
            phase = FitPhase.READY if self.is_fitted else FitPhase.EMPTY
        return FitStatus(
            phase=phase,
            elapsed_seconds=0.0 if started_at is None else time.monotonic() - started_at,
            estimated_seconds=self._last_fit_seconds or FIRST_FIT_ESTIMATE_SECONDS,
            song_count=self.song_count,
        )

    def ensure_fitted(self, load_songs: Callable[[], list], feature_keys: list[str]) -> None:
        """Fit once if there is no embedding yet.

        Args:
            load_songs: Loads all songs with dsp/mood/profile relations; only
                called when a fit is actually needed.
            feature_keys: Features to fit on.
        """
        if self.is_fitted:
            return
        with self._fit_lock:
            if self.is_fitted:
                return
            self._fit(load_songs(), feature_keys)

    def fit(self, songs: list, feature_keys: list[str]) -> None:
        """Fit UMAP from scratch on all given songs."""
        with self._fit_lock:
            self._fit(songs, feature_keys)

    def _fit(self, songs: list, feature_keys: list[str]) -> None:
        if len(songs) < 3:
            return
        self._fit_started_at = time.monotonic()
        try:
            self._fit_embedding(songs, feature_keys)
            self._last_fit_seconds = time.monotonic() - self._fit_started_at
        finally:
            self._fit_started_at = None

    def _fit_embedding(self, songs: list, feature_keys: list[str]) -> None:
        keys = [k for k in feature_keys if k in FEATURE_DEFINITIONS]
        logger.info("[UMAP] Fitting on %d songs × %d features", len(songs), len(keys))

        matrix = _build_feature_matrix(songs, keys)
        scaler = StandardScaler()
        matrix_scaled = scaler.fit_transform(matrix)

        n_neighbors = min(15, len(songs) - 1)
        reducer_2d = UMAP(n_components=2, random_state=42, n_neighbors=n_neighbors)
        coords_2d = reducer_2d.fit_transform(matrix_scaled)

        with self._lock:
            self._reducer_2d = reducer_2d
            self._scaler = scaler
            self._feature_keys = keys
            self._coords_2d = {
                s.id: (float(coords_2d[i, 0]), float(coords_2d[i, 1]))
                for i, s in enumerate(songs)
            }
            self._meta = {s.id: (s.title, s.artist) for s in songs}
            self._matrix_scaled = matrix_scaled
            self._song_ids = [s.id for s in songs]
            self._recompute_neighbors()

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

        with self._lock:
            for i, song in enumerate(new_songs):
                self._coords_2d[song.id] = (float(coords_2d[i, 0]), float(coords_2d[i, 1]))
                self._meta[song.id] = (song.title, song.artist)
            if self._matrix_scaled is not None:
                self._matrix_scaled = np.vstack([self._matrix_scaled, matrix_scaled])
                self._song_ids.extend(s.id for s in new_songs)
                self._recompute_neighbors()

        logger.info("[UMAP] Added %d song(s) via transform", len(new_songs))

    def reset(self) -> None:
        with self._lock:
            self._reducer_2d = None
            self._scaler = None
            self._feature_keys = []
            self._coords_2d.clear()
            self._meta.clear()
            self._matrix_scaled = None
            self._song_ids = []
            self._neighbors.clear()
        logger.info("[UMAP] State reset")

    def _recompute_neighbors(self) -> None:
        """Find each song's nearest neighbours in the high-dimensional space.

        Runs on the scaled feature matrix — before UMAP reduces it — so the
        links reflect true feature similarity rather than 2D layout accidents.
        Must be called with the lock held.
        """
        matrix = self._matrix_scaled
        if matrix is None or len(self._song_ids) < 2:
            self._neighbors = {}
            return

        k = min(NEIGHBOR_COUNT, len(self._song_ids) - 1)
        finder = NearestNeighbors(n_neighbors=k + 1).fit(matrix)
        _, indices = finder.kneighbors(matrix)

        # Column 0 is the song itself — skip it.
        self._neighbors = {
            self._song_ids[row]: [self._song_ids[col] for col in indices[row][1:]]
            for row in range(len(self._song_ids))
        }

    def get_result(self) -> list[UmapPoint2D]:
        with self._lock:
            return [
                UmapPoint2D(
                    song_id=sid,
                    x=c[0],
                    y=c[1],
                    title=self._meta[sid][0],
                    artist=self._meta[sid][1],
                    neighbors=self._neighbors.get(sid, []),
                )
                for sid, c in self._coords_2d.items()
            ]


# Module-level singleton shared by all routes and background tasks
_state = UmapState()


def get_umap_state() -> UmapState:
    return _state
