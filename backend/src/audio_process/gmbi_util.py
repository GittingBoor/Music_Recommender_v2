import pandas as pd

to_delete_from_json = ["barkbands", "bpm", "first_peak_bpm", "second_peak_bpm", "histogram", "beats_position", "bpm_estimates",
                      "bpm_intervals", "onset_times",  "chords_histogram", "thpcp", "chords_key", "chords_scale", 
                      "key_key", "key_scale", "chords_progression"]

to_delete_from_df = ['tristimulus_min_0', 'tristimulus_min_1', 'tristimulus_min_2', 'tristimulus_max_0', 'tristimulus_max_1', 'tristimulus_max_2', 'oddtoevenharmonicenergyratio_min', 'inharmonicity_min', 'inharmonicity_max', 'second_peak_weight_stdev',
                   'second_peak_spread_stdev', 'second_peak_spread_min', 'second_peak_spread_median', 'second_peak_spread_mean', 'second_peak_spread_max', 'first_peak_weight_stdev', 'first_peak_spread_stdev', 'spectral_strongpeak_min', 'spectral_complexity_min',
                    'silence_rate_60dB_min', 'silence_rate_60dB_median', 'silence_rate_60dB_max', 'silence_rate_30dB_min', 'silence_rate_30dB_median', 'silence_rate_30dB_max', 'silence_rate_20dB_median', 'silence_rate_20dB_min', 'silence_rate_20dB_max']

# beat loudness gets randomly not computed by Essentia Extractor
beat_loudness = ['beats_loudness_band_ratio_max_2', 'beats_loudness_stdev', 'beats_loudness_band_ratio_min_5', 'beats_loudness_band_ratio_min_2', 'beats_loudness_band_ratio_mean_2', 'beats_loudness_band_ratio_min_4', 'beats_loudness_mean', 'beats_loudness_band_ratio_mean_1', 
                    'beats_loudness_band_ratio_max_5', 'beats_loudness_band_ratio_max_3', 'beats_loudness_band_ratio_stdev_2', 'beats_loudness_band_ratio_mean_5', 'beats_loudness_band_ratio_median_0', 'beats_loudness_max', 'beats_loudness_band_ratio_stdev_5', 
                    'beats_loudness_min', 'beats_loudness_band_ratio_min_1', 'beats_loudness_band_ratio_mean_4', 'beats_loudness_band_ratio_median_5', 'beats_loudness_band_ratio_max_0', 'beats_loudness_band_ratio_stdev_1', 'beats_loudness_band_ratio_stdev_0', 
                    'beats_loudness_band_ratio_mean_0', 'beats_loudness_band_ratio_min_0', 'beats_loudness_band_ratio_mean_3', 'beats_loudness_band_ratio_max_4', 'beats_loudness_band_ratio_median_2', 'beats_loudness_band_ratio_stdev_4', 'beats_loudness_band_ratio_median_3', 
                    'beats_loudness_band_ratio_median_1', 'beats_loudness_band_ratio_median_4', 'beats_loudness_band_ratio_min_3', 'beats_loudness_band_ratio_stdev_3', 'beats_loudness_median', 'beats_loudness_band_ratio_max_1']

def del_features_from_df(df):
    hpcp = []
    for i in range(0, 36):
        hpcp.append('hpcp_max_' + str(i))
        hpcp.append('hpcp_min_' + str(i))

    items_to_delete = to_delete_from_df + hpcp
    df.drop(items_to_delete, axis=1, inplace=True)
    try:
        df.drop(beat_loudness, axis=1, inplace=True)
    except:
        pass
    
    return df

def del_features_from_json(features_dict):
    for key in ['lowLevel', 'rhythm', 'sfx', 'tonal']:
        for feature in list(features_dict[key]): 
            if feature in to_delete_from_json:
                del features_dict[key][feature]
    return features_dict


def create_gmbi_df(features_ess, features_ml):
    
    df = pd.DataFrame()
    features_ess = del_features_from_json(features_ess)

    # store ml features to df
    for key in features_ml.keys():
        df[key] = [features_ml[key]]

    # store essentia features to df
    for key in ['lowLevel', 'rhythm', 'sfx', 'tonal']:
        for feature in features_ess[key]: 
            item = features_ess[key][feature]
            if isinstance(item, (float, int)):
                df[feature] = [item]
            if isinstance(item, dict):
                for i in list(item.keys()):
                    if isinstance(item[i], (float, int)):   
                        df['_'.join([feature, i])] = [item[i]]
                    if isinstance(item[i], list):
                        for j in range(len(item[i])):
                            df['_'.join([feature, i, str(j)])] = [item[i][j]]

    return del_features_from_df(df)