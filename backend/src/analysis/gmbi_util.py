"""
GMBI feature-matrix utilities — ported 1:1 from audio_process/gmbi_util.py.

Column order and drop-lists are critical: the trained RandomForest models
expect EXACTLY this feature layout. Do not reorder or add/remove columns
without retraining the models.
"""
import pandas as pd

# Keys to drop from the Essentia Extractor JSON before building the DataFrame.
# These are high-cardinality or categorical features incompatible with the RF.
to_delete_from_json = [
    "barkbands", "bpm", "first_peak_bpm", "second_peak_bpm", "histogram",
    "beats_position", "bpm_estimates", "bpm_intervals", "onset_times",
    "chords_histogram", "thpcp", "chords_key", "chords_scale",
    "key_key", "key_scale", "chords_progression",
]

# DataFrame columns to drop after flattening (unreliable or leaking features).
to_delete_from_df = [
    "tristimulus_min_0", "tristimulus_min_1", "tristimulus_min_2",
    "tristimulus_max_0", "tristimulus_max_1", "tristimulus_max_2",
    "oddtoevenharmonicenergyratio_min", "inharmonicity_min", "inharmonicity_max",
    "second_peak_weight_stdev", "second_peak_spread_stdev",
    "second_peak_spread_min", "second_peak_spread_median",
    "second_peak_spread_mean", "second_peak_spread_max",
    "first_peak_weight_stdev", "first_peak_spread_stdev",
    "spectral_strongpeak_min", "spectral_complexity_min",
    "silence_rate_60dB_min", "silence_rate_60dB_median", "silence_rate_60dB_max",
    "silence_rate_30dB_min", "silence_rate_30dB_median", "silence_rate_30dB_max",
    "silence_rate_20dB_median", "silence_rate_20dB_min", "silence_rate_20dB_max",
]

# Beat-loudness columns — Essentia sometimes does not compute these, so they
# are dropped in a try/except to handle both cases gracefully.
beat_loudness = [
    "beats_loudness_band_ratio_max_2", "beats_loudness_stdev",
    "beats_loudness_band_ratio_min_5", "beats_loudness_band_ratio_min_2",
    "beats_loudness_band_ratio_mean_2", "beats_loudness_band_ratio_min_4",
    "beats_loudness_mean", "beats_loudness_band_ratio_mean_1",
    "beats_loudness_band_ratio_max_5", "beats_loudness_band_ratio_max_3",
    "beats_loudness_band_ratio_stdev_2", "beats_loudness_band_ratio_mean_5",
    "beats_loudness_band_ratio_median_0", "beats_loudness_max",
    "beats_loudness_band_ratio_stdev_5", "beats_loudness_min",
    "beats_loudness_band_ratio_min_1", "beats_loudness_band_ratio_mean_4",
    "beats_loudness_band_ratio_median_5", "beats_loudness_band_ratio_max_0",
    "beats_loudness_band_ratio_stdev_1", "beats_loudness_band_ratio_stdev_0",
    "beats_loudness_band_ratio_mean_0", "beats_loudness_band_ratio_min_0",
    "beats_loudness_band_ratio_mean_3", "beats_loudness_band_ratio_max_4",
    "beats_loudness_band_ratio_median_2", "beats_loudness_band_ratio_stdev_4",
    "beats_loudness_band_ratio_median_3", "beats_loudness_band_ratio_median_1",
    "beats_loudness_band_ratio_median_4", "beats_loudness_band_ratio_min_3",
    "beats_loudness_band_ratio_stdev_3", "beats_loudness_median",
    "beats_loudness_band_ratio_max_1",
]


def del_features_from_df(df: pd.DataFrame) -> pd.DataFrame:
    """Drop known-bad columns from the feature DataFrame."""
    hpcp = []
    for i in range(36):
        hpcp.append(f"hpcp_max_{i}")
        hpcp.append(f"hpcp_min_{i}")

    df.drop(to_delete_from_df + hpcp, axis=1, inplace=True)
    try:
        df.drop(beat_loudness, axis=1, inplace=True)
    except Exception:
        pass
    return df


def del_features_from_json(features_dict: dict) -> dict:
    """Remove high-cardinality / categorical keys from the Essentia JSON pool."""
    for key in ["lowLevel", "rhythm", "sfx", "tonal"]:
        for feature in list(features_dict.get(key, {})):
            if feature in to_delete_from_json:
                del features_dict[key][feature]
    return features_dict


def create_gmbi_df(features_ess: dict, features_ml: dict) -> pd.DataFrame:
    """
    Build the feature DataFrame consumed by the GMBI RandomForest models.

    Parameters
    ----------
    features_ess : dict
        Output of ``es.Extractor`` aggregated by ``PoolAggregator`` and
        converted to JSON (Python dict).  Must have keys
        ``lowLevel``, ``rhythm``, ``sfx``, ``tonal``.
    features_ml : dict
        Dict of per-frame DL predictions for this audio chunk.
        Keys: ``voice``, ``female``, ``danceability``, ``tonal``
        (one scalar value each, NOT arrays).

    Returns
    -------
    pd.DataFrame
        Single-row DataFrame ready for ``rf.predict()``.
    """
    df = pd.DataFrame()
    features_ess = del_features_from_json(features_ess)

    # Store DL features first (preserves original column order)
    for key in features_ml:
        df[key] = [features_ml[key]]

    # Flatten Essentia features into the DataFrame
    for section in ["lowLevel", "rhythm", "sfx", "tonal"]:
        for feature, item in features_ess.get(section, {}).items():
            if isinstance(item, (float, int)):
                df[feature] = [item]
            elif isinstance(item, dict):
                for stat, val in item.items():
                    if isinstance(val, (float, int)):
                        df[f"{feature}_{stat}"] = [val]
                    elif isinstance(val, list):
                        for j, v in enumerate(val):
                            df[f"{feature}_{stat}_{j}"] = [v]

    return del_features_from_df(df)
