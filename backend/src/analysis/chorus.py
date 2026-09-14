"""Locate the most recognisable segment (chorus) of a track.

Works purely on the per-second DSP timeseries already stored for every song,
so no audio decoding is needed and a lookup costs ~2 ms.
"""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

PREVIEW_SECONDS = 15

# A song must be at least this long for the repetition analysis to be meaningful.
_MIN_ANALYSABLE_SECONDS = 3 * PREVIEW_SECONDS
# Intros and outros are skipped — they are rarely the hook.
_EDGE_SKIP_FRACTION = 0.08
_MIN_EDGE_SKIP_SECONDS = 8
# A chorus repeats (weighted high) and is energetic (weighted lower).
_REPETITION_WEIGHT = 0.65
_ENERGY_WEIGHT = 0.35
# Earlier repeats scoring within this fraction of the winner count as the same section.
_EARLIEST_INSTANCE_TOLERANCE = 0.92
_EPSILON = 1e-8


@dataclass(frozen=True)
class ChorusSegment:
    """A playable segment of a track, in whole seconds."""

    start_seconds: int
    duration_seconds: int


class ChorusLocator:
    """Find the segment of a track with the highest recognition value.

    The chorus is the passage that recurs most often while carrying high
    energy. Both signals are read from the 1 Hz feature timeseries stored in
    ``dsp_features``; the earliest occurrence of the winning passage is
    returned, because the first chorus is the one listeners recognise.
    """

    def __init__(self, window_seconds: int = PREVIEW_SECONDS) -> None:
        self._window = window_seconds

    def locate(
        self,
        timeseries: list[list[float] | None],
        total_seconds: float,
    ) -> ChorusSegment | None:
        """Return the most recognisable segment of a track.

        Args:
            timeseries: Per-second feature series. The first entry must be the
                loudness series, which doubles as the energy signal.
            total_seconds: Track duration in seconds.

        Returns:
            The segment to play, or ``None`` when no usable timeseries exist.
        """
        matrix = self._build_matrix(timeseries, total_seconds)
        if matrix is None:
            return None

        length = matrix.shape[0]
        if length < _MIN_ANALYSABLE_SECONDS:
            return ChorusSegment(
                start_seconds=max(0, (length - self._window) // 2),
                duration_seconds=min(self._window, length),
            )

        similarity = self._self_similarity(matrix)
        score = self._score_windows(matrix, similarity, length)
        best = int(np.argmax(score))
        start = self._earliest_instance(similarity, best, self._edge_skip(length))

        return ChorusSegment(start_seconds=start, duration_seconds=self._window)

    # ── internals ─────────────────────────────────────────────────────────

    def _build_matrix(
        self,
        timeseries: list[list[float] | None],
        total_seconds: float,
    ) -> np.ndarray | None:
        """Stack the populated series into a z-normalised (seconds × features) matrix."""
        if total_seconds <= 0:
            return None
        limit = int(total_seconds)
        columns = [
            np.asarray(series[:limit], dtype=float)
            for series in timeseries
            if series
        ]
        if not columns:
            return None

        length = min(len(column) for column in columns)
        if length < self._window * 2:
            return None

        matrix = np.column_stack([column[:length] for column in columns])
        return (matrix - matrix.mean(axis=0)) / (matrix.std(axis=0) + _EPSILON)

    def _edge_skip(self, length: int) -> int:
        return max(_MIN_EDGE_SKIP_SECONDS, int(length * _EDGE_SKIP_FRACTION))

    def _self_similarity(self, matrix: np.ndarray) -> np.ndarray:
        """Cosine similarity between every pair of sliding windows.

        Windows overlapping each other are masked out, so a window is never
        considered a repeat of itself or of its immediate neighbours.
        """
        count = matrix.shape[0] - self._window
        windows = np.stack([matrix[i: i + self._window].ravel() for i in range(count)])
        windows /= np.linalg.norm(windows, axis=1, keepdims=True) + _EPSILON

        similarity = windows @ windows.T
        for i in range(count):
            low = max(0, i - self._window)
            high = min(count, i + self._window + 1)
            similarity[i, low:high] = -1.0
        return similarity

    def _score_windows(
        self,
        matrix: np.ndarray,
        similarity: np.ndarray,
        length: int,
    ) -> np.ndarray:
        """Combine repetition strength and energy, masking intro and outro."""
        loudness = matrix[:, 0]
        energy = (loudness - loudness.min()) / (np.ptp(loudness) + _EPSILON)

        count = similarity.shape[0]
        repetition = similarity.max(axis=1)
        window_energy = np.array(
            [energy[i: i + self._window].mean() for i in range(count)]
        )

        score = _REPETITION_WEIGHT * repetition + _ENERGY_WEIGHT * window_energy
        skip = self._edge_skip(length)
        score[:skip] = -1.0
        score[max(0, count - skip):] = -1.0
        return score

    def _earliest_instance(
        self,
        similarity: np.ndarray,
        best: int,
        skip: int,
    ) -> int:
        """Return the first window that is essentially the same section as ``best``."""
        threshold = similarity[best].max() * _EARLIEST_INSTANCE_TOLERANCE
        for i in range(skip, best):
            if similarity[best, i] >= threshold:
                return i
        return best


_locator = ChorusLocator()


def get_chorus_locator() -> ChorusLocator:
    """Return the process-wide chorus locator."""
    return _locator
