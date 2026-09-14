"""Resample per-song feature timeseries onto a shared time axis and aggregate them.

Timestamps are not stored with the timeseries. Each value's timestamp (window
centre) is reconstructed from the hop and window length used at extraction
time, because features differ in resolution (EffNet ~1 s, MusiCNN ~1.5 s).
"""

from dataclasses import dataclass
from enum import Enum
from math import ceil

import numpy as np

N_POINTS: int = 100
MIN_SONGS: int = 5
ABSOLUTE_STEP_SECONDS: float = 1.0
LOWER_PERCENTILE: float = 25.0
UPPER_PERCENTILE: float = 75.0
PERCENT_SCALE: float = 100.0
# EBU R128 absolute gate — digital silence is reported as ~-300 dB.
LOUDNESS_FLOOR_DB: float = -70.0
CONSTANT_NORMALIZED_VALUE: float = 0.5

# Extraction parameters (see embeddings.py / classifiers.py / dsp.py).
_ML_SAMPLE_RATE: int = 16000
_ML_MEL_HOP: int = 256
_EFFNET_PATCH_HOP: int = 62
_EFFNET_PATCH_SIZE: int = 128
_MUSICNN_PATCH_HOP: int = 93
_MUSICNN_PATCH_SIZE: int = 187
_DSP_SAMPLE_RATE: int = 44100
_DSP_HOP: int = 1024
_DSP_FRAME: int = 2048
_DSP_FRAMES_PER_VALUE: int = 43
_LOUDNESS_SHORT_TERM_WINDOW_S: float = 3.0
_LOUDNESS_SHORT_TERM_HOP_S: float = 0.1
_LOUDNESS_VALUES_PER_SECOND: int = 10


class TimeAxisMode(str, Enum):
    RELATIVE = "relative"
    ABSOLUTE = "absolute"


class TimeseriesDataError(ValueError):
    """A song lacks the data required to place its values on a time axis."""


@dataclass(frozen=True)
class FeatureTimebase:
    """Hop and window length of one feature's timeseries, in seconds."""

    hop_seconds: float
    window_seconds: float

    def centers(self, n_values: int) -> np.ndarray:
        return np.arange(n_values) * self.hop_seconds + self.window_seconds / 2


_EFFNET_TIMEBASE = FeatureTimebase(
    hop_seconds=_EFFNET_PATCH_HOP * _ML_MEL_HOP / _ML_SAMPLE_RATE,
    window_seconds=_EFFNET_PATCH_SIZE * _ML_MEL_HOP / _ML_SAMPLE_RATE,
)
_MUSICNN_TIMEBASE = FeatureTimebase(
    hop_seconds=_MUSICNN_PATCH_HOP * _ML_MEL_HOP / _ML_SAMPLE_RATE,
    window_seconds=_MUSICNN_PATCH_SIZE * _ML_MEL_HOP / _ML_SAMPLE_RATE,
)
_DSP_TIMEBASE = FeatureTimebase(
    hop_seconds=_DSP_FRAMES_PER_VALUE * _DSP_HOP / _DSP_SAMPLE_RATE,
    window_seconds=((_DSP_FRAMES_PER_VALUE - 1) * _DSP_HOP + _DSP_FRAME) / _DSP_SAMPLE_RATE,
)
_LOUDNESS_TIMEBASE = FeatureTimebase(
    hop_seconds=_LOUDNESS_VALUES_PER_SECOND * _LOUDNESS_SHORT_TERM_HOP_S,
    window_seconds=_LOUDNESS_SHORT_TERM_WINDOW_S
    + (_LOUDNESS_VALUES_PER_SECOND - 1) * _LOUDNESS_SHORT_TERM_HOP_S,
)

FEATURE_TIMEBASES: dict[str, FeatureTimebase] = {
    "loudness":           _LOUDNESS_TIMEBASE,
    "spectral_centroid":  _DSP_TIMEBASE,
    "spectral_rolloff":   _DSP_TIMEBASE,
    "spectral_flux":      _DSP_TIMEBASE,
    "zero_crossing_rate": _DSP_TIMEBASE,
    "dissonance":         _DSP_TIMEBASE,
    "arousal":            _MUSICNN_TIMEBASE,
    "valence":            _MUSICNN_TIMEBASE,
    "approachability":    _EFFNET_TIMEBASE,
    "engagement":         _EFFNET_TIMEBASE,
    "voice":              _EFFNET_TIMEBASE,
    "gender":             _EFFNET_TIMEBASE,
    "happy":              _EFFNET_TIMEBASE,
    "sad":                _EFFNET_TIMEBASE,
    "aggressive":         _EFFNET_TIMEBASE,
    "party":              _EFFNET_TIMEBASE,
    "relaxed":            _EFFNET_TIMEBASE,
    "acoustic":           _EFFNET_TIMEBASE,
    "electronic":         _EFFNET_TIMEBASE,
}

FEATURE_VALUE_FLOORS: dict[str, float] = {
    "loudness": LOUDNESS_FLOOR_DB,
}


@dataclass(frozen=True)
class SongSeries:
    """One song's raw timeseries for a single feature."""

    song_id: str
    values: list[float]
    duration_seconds: float

    @classmethod
    def from_optional(
        cls,
        song_id: str,
        values: list[float] | None,
        duration_seconds: float | None,
    ) -> "SongSeries":
        """Build a SongSeries, rejecting songs without timeseries or duration.

        Raises:
            TimeseriesDataError: If values are missing/empty or the duration is missing/non-positive.
        """
        if not values:
            raise TimeseriesDataError(f"Song '{song_id}' has no timeseries for this feature — re-run the analysis.")
        if duration_seconds is None or duration_seconds <= 0:
            raise TimeseriesDataError(
                f"Song '{song_id}' has no valid duration (got {duration_seconds!r}) — re-extract file metadata."
            )
        return cls(song_id=song_id, values=values, duration_seconds=duration_seconds)


@dataclass(frozen=True)
class AggregatedTimeseries:
    """Per-position statistics; stats are NaN where fewer than min_songs contribute."""

    positions: np.ndarray
    mean: np.ndarray
    p25: np.ndarray
    p75: np.ndarray
    counts: np.ndarray


class TimeseriesResampler:
    """Map a song's values onto the relative (0–100 %) or absolute (seconds) grid."""

    def __init__(self, timebase: FeatureTimebase, value_floor: float | None = None) -> None:
        self._timebase = timebase
        self._value_floor = value_floor

    def to_relative(self, series: SongSeries) -> np.ndarray:
        """Linearly interpolate at N_POINTS evenly spaced positions from 0 % to 100 %."""
        positions = self._centers(series) / series.duration_seconds
        return np.interp(relative_grid() / PERCENT_SCALE, positions, self._values(series))

    def to_absolute(self, series: SongSeries) -> np.ndarray:
        """Linearly interpolate at every ABSOLUTE_STEP_SECONDS while the song is still running."""
        grid = absolute_grid(series.duration_seconds)
        grid = grid[grid < series.duration_seconds]
        return np.interp(grid, self._centers(series), self._values(series))

    def _centers(self, series: SongSeries) -> np.ndarray:
        return self._timebase.centers(len(series.values))

    def _values(self, series: SongSeries) -> np.ndarray:
        values = np.asarray(series.values, dtype=float)
        if self._value_floor is None:
            return values
        return np.maximum(values, self._value_floor)


class TimeseriesAggregator:
    """Mean and interquartile band across songs, ignoring songs that have already ended."""

    def __init__(self, resampler: TimeseriesResampler, min_songs: int = MIN_SONGS) -> None:
        self._resampler = resampler
        self._min_songs = min_songs

    def aggregate(self, songs: list[SongSeries], mode: TimeAxisMode) -> AggregatedTimeseries:
        match mode:
            case TimeAxisMode.RELATIVE:
                positions = relative_grid()
                rows = [self._resampler.to_relative(s) for s in songs]
            case TimeAxisMode.ABSOLUTE:
                longest = max((s.duration_seconds for s in songs), default=0.0)
                positions = absolute_grid(longest)
                rows = [self._resampler.to_absolute(s) for s in songs]
        return self._statistics(positions, self._stack(rows, len(positions)))

    @staticmethod
    def _stack(rows: list[np.ndarray], width: int) -> np.ndarray:
        matrix = np.full((len(rows), width), np.nan)
        for i, row in enumerate(rows):
            matrix[i, : len(row)] = row
        return matrix

    def _statistics(self, positions: np.ndarray, matrix: np.ndarray) -> AggregatedTimeseries:
        counts = np.sum(~np.isnan(matrix), axis=0)
        drawn = counts >= self._min_songs
        mean = np.full(len(positions), np.nan)
        p25 = np.full(len(positions), np.nan)
        p75 = np.full(len(positions), np.nan)
        if drawn.any():
            mean[drawn] = np.nanmean(matrix[:, drawn], axis=0)
            p25[drawn] = np.nanpercentile(matrix[:, drawn], LOWER_PERCENTILE, axis=0)
            p75[drawn] = np.nanpercentile(matrix[:, drawn], UPPER_PERCENTILE, axis=0)
        return AggregatedTimeseries(positions=positions, mean=mean, p25=p25, p75=p75, counts=counts)


class AggregateNormalizer:
    """Min-max scale mean and band with one shared transform over the drawn points."""

    def normalize(self, aggregate: AggregatedTimeseries) -> AggregatedTimeseries:
        stacked = np.concatenate([aggregate.mean, aggregate.p25, aggregate.p75])
        if np.all(np.isnan(stacked)):
            return aggregate
        low, high = float(np.nanmin(stacked)), float(np.nanmax(stacked))
        return AggregatedTimeseries(
            positions=aggregate.positions,
            mean=self._scale(aggregate.mean, low, high),
            p25=self._scale(aggregate.p25, low, high),
            p75=self._scale(aggregate.p75, low, high),
            counts=aggregate.counts,
        )

    @staticmethod
    def _scale(values: np.ndarray, low: float, high: float) -> np.ndarray:
        if high == low:
            return np.where(np.isnan(values), np.nan, CONSTANT_NORMALIZED_VALUE)
        return (values - low) / (high - low)


def relative_grid() -> np.ndarray:
    return np.linspace(0.0, PERCENT_SCALE, N_POINTS)


def absolute_grid(duration_seconds: float) -> np.ndarray:
    return np.arange(ceil(duration_seconds / ABSOLUTE_STEP_SECONDS)) * ABSOLUTE_STEP_SECONDS


def resampler_for(feature: str) -> TimeseriesResampler:
    """Return the resampler configured with the feature's timebase and value floor.

    Raises:
        TimeseriesDataError: If no timebase is registered for the feature.
    """
    if feature not in FEATURE_TIMEBASES:
        raise TimeseriesDataError(f"No timebase registered for feature '{feature}'. Known: {sorted(FEATURE_TIMEBASES)}")
    return TimeseriesResampler(FEATURE_TIMEBASES[feature], FEATURE_VALUE_FLOORS.get(feature))
