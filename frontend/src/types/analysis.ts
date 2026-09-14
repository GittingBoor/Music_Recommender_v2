export interface CorrelationResponse {
  features: string[];
  matrix: (number | null)[][];
}

export type TimeAxisMode = "relative" | "absolute";

export interface TimeseriesSong {
  song_id: string;
  title: string | null;
  artist: string | null;
  duration_seconds: number;
  values: number[];
}

export interface TimeseriesResponse {
  feature: string;
  mode: TimeAxisMode;
  song_count: number;
  min_songs: number;
  selected_song: TimeseriesSong | null;
  positions: number[];
  avg_timeseries: (number | null)[];
  p25_timeseries: (number | null)[];
  p75_timeseries: (number | null)[];
  counts_at_time: number[];
}

export interface SongDetailTimeseries {
  loudness?: number[] | null;
  spectral_centroid?: number[] | null;
  spectral_rolloff?: number[] | null;
  spectral_flux?: number[] | null;
  zero_crossing_rate?: number[] | null;
  dissonance?: number[] | null;
  arousal?: number[] | null;
  valence?: number[] | null;
  approachability?: number[] | null;
  engagement?: number[] | null;
  voice?: number[] | null;
  gender?: number[] | null;
  happy?: number[] | null;
  sad?: number[] | null;
  aggressive?: number[] | null;
  party?: number[] | null;
  relaxed?: number[] | null;
  acoustic?: number[] | null;
  electronic?: number[] | null;
}

export interface SongDetail {
  id: string;
  title: string | null;
  artist: string | null;
  dsp?: {
    bpm: number | null;
    beat_count: number | null;
    beat_confidence: number | null;
    danceability: number | null;
    key: string | null;
    scale: string | null;
    key_strength: number | null;
    integrated_lufs: number | null;
    loudness_range_lu: number | null;
    dynamic_complexity: number | null;
    loudness_db: number | null;
    spectral_centroid_mean: number | null;
    spectral_flux_mean: number | null;
    dissonance: number | null;
    chord_change_rate: number | null;
    most_common_chord: string | null;
    tuning_frequency_hz: number | null;
  };
  ml_profile?: {
    niche_score: number | null;
    mainstream_score: number | null;
    background_score: number | null;
    active_score: number | null;
    instrumental_score: number | null;
    vocal_score: number | null;
    female_score: number | null;
    male_score: number | null;
    arousal: number | null;
    valence: number | null;
  };
  ml_moods?: {
    happy: number | null;
    sad: number | null;
    aggressive: number | null;
    party: number | null;
    relaxed: number | null;
    acoustic: number | null;
    electronic: number | null;
  };
  file_metadata?: {
    duration_seconds: number | null;
    file_format: string | null;
    bitrate_kbps: number | null;
    sample_rate_hz: number | null;
  };
  track_metadata?: {
    release_date: string | null;
    playcount: number | null;
    listeners: number | null;
  };
  parent_genres: Array<{ genre: string; percentage: number }>;
  detailed_genres: Array<{ genre: string; probability: number }>;
  instruments: Array<{ instrument: string; probability: number }>;
  timeseries: SongDetailTimeseries;
}
