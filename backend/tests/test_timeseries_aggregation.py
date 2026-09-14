import numpy as np

from src.analysis.timeseries_aggregation import (
    FEATURE_TIMEBASES,
    N_POINTS,
    FeatureTimebase,
    SongSeries,
    TimeAxisMode,
    TimeseriesAggregator,
    TimeseriesDataError,
    TimeseriesResampler,
)

CONSTANT_VALUE = -12.5
DURATIONS_SECONDS = [138.4, 181.0, 240.7, 312.2, 356.9, 600.0]
IDEAL_TIMEBASE = FeatureTimebase(hop_seconds=1.0, window_seconds=0.0)
EXACT_TOLERANCE = 1e-9


def _song_from_signal(song_id: str, duration: float, timebase: FeatureTimebase, signal) -> SongSeries:
    n_values = int((duration - timebase.window_seconds) / timebase.hop_seconds) + 1
    centers = timebase.centers(n_values)
    return SongSeries(song_id=song_id, values=list(signal(centers, duration)), duration_seconds=duration)


def _constant_songs(timebase: FeatureTimebase) -> list[SongSeries]:
    return [
        _song_from_signal(f"s{i}", d, timebase, lambda c, _d: np.full(len(c), CONSTANT_VALUE))
        for i, d in enumerate(DURATIONS_SECONDS)
    ]


def _drawn(values: np.ndarray) -> np.ndarray:
    return values[~np.isnan(values)]


def test_constant_song_is_flat_in_relative_mode():
    for timebase in FEATURE_TIMEBASES.values():
        aggregator = TimeseriesAggregator(TimeseriesResampler(timebase))
        result = aggregator.aggregate(_constant_songs(timebase), TimeAxisMode.RELATIVE)
        assert len(_drawn(result.mean)) == N_POINTS
        np.testing.assert_allclose(result.mean, CONSTANT_VALUE, atol=EXACT_TOLERANCE)


def test_constant_song_is_flat_in_absolute_mode_until_the_end():
    for timebase in FEATURE_TIMEBASES.values():
        aggregator = TimeseriesAggregator(TimeseriesResampler(timebase), min_songs=1)
        result = aggregator.aggregate(_constant_songs(timebase), TimeAxisMode.ABSOLUTE)
        assert len(_drawn(result.mean)) == len(result.positions)
        np.testing.assert_allclose(result.mean, CONSTANT_VALUE, atol=EXACT_TOLERANCE)
        assert result.counts[0] == len(DURATIONS_SECONDS)
        assert result.counts[-1] == 1


def test_absolute_mode_hides_points_below_min_songs():
    min_songs = 3
    aggregator = TimeseriesAggregator(TimeseriesResampler(IDEAL_TIMEBASE), min_songs=min_songs)
    result = aggregator.aggregate(_constant_songs(IDEAL_TIMEBASE), TimeAxisMode.ABSOLUTE)
    assert np.all(np.isnan(result.mean[result.counts < min_songs]))
    assert not np.any(np.isnan(result.mean[result.counts >= min_songs]))


def test_linear_songs_of_different_length_coincide_in_relative_mode():
    rising = lambda centers, duration: centers / duration
    resampler = TimeseriesResampler(IDEAL_TIMEBASE)
    short = resampler.to_relative(_song_from_signal("short", 120.0, IDEAL_TIMEBASE, rising))
    long = resampler.to_relative(_song_from_signal("long", 480.0, IDEAL_TIMEBASE, rising))
    np.testing.assert_allclose(short, long, atol=EXACT_TOLERANCE)


def test_linear_songs_coincide_across_feature_resolutions():
    rising = lambda centers, duration: centers / duration
    effnet, musicnn = FEATURE_TIMEBASES["happy"], FEATURE_TIMEBASES["arousal"]
    happy = TimeseriesResampler(effnet).to_relative(_song_from_signal("a", 150.0, effnet, rising))
    arousal = TimeseriesResampler(musicnn).to_relative(_song_from_signal("b", 420.0, musicnn, rising))
    grid = np.linspace(0.0, 1.0, N_POINTS)
    both_covered = (grid > 0.03) & (grid < 0.97)
    np.testing.assert_allclose(happy[both_covered], arousal[both_covered], atol=EXACT_TOLERANCE)


def test_missing_duration_or_values_raise():
    for values, duration in [(None, 200.0), ([], 200.0), ([1.0], None), ([1.0], 0.0)]:
        try:
            SongSeries.from_optional("x", values, duration)
        except TimeseriesDataError:
            continue
        raise AssertionError(f"Expected TimeseriesDataError for values={values!r}, duration={duration!r}")
