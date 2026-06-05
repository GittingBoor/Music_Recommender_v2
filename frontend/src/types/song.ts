export interface FileMetadata {
  file_format: string | null;
  duration_seconds: number | null;
  sample_rate_hz: number | null;
  bitrate_kbps: number | null;
  channels: number | null;
}

export interface SimilarTrack {
  title: string;
  artist: string;
  similarity: number;
}

export interface TrackMetadata {
  release_date: string | null;
  playcount: number | null;
  listeners: number | null;
  mbid: string | null;
  url: string | null;
  album_mbid: string | null;
  mb_genres: string[] | null;
  featured_artists: string[] | null;
  similar_tracks: SimilarTrack[] | null;
}

export interface DSPFeatures {
  bpm: number | null;
  beat_count: number | null;
  beat_confidence: number | null;
  danceability: number | null;
  beat_loudness_mean: number | null;
  onset_rate: number | null;
  key: string | null;
  scale: string | null;
  key_strength: number | null;
  tuning_frequency_hz: number | null;
  tuning_cents_deviation: number | null;
  most_common_chord: string | null;
  chord_strength_mean: number | null;
  chord_change_rate: number | null;
  integrated_lufs: number | null;
  loudness_range_lu: number | null;
  dynamic_complexity: number | null;
  loudness_db: number | null;
  spectral_centroid_mean: number | null;
  spectral_rolloff_mean: number | null;
  spectral_flux_mean: number | null;
  mfcc_mean: number[] | null;
  zero_crossing_rate: number | null;
  dissonance: number | null;
}

export interface MLProfile {
  approachability_label: string | null;
  approachability_score: number | null;
  engagement_label: string | null;
  engagement_score: number | null;
  voice_label: string | null;
  voice_score: number | null;
  gender_label: string | null;
  gender_score: number | null;
  arousal: number | null;
  valence: number | null;
}

export interface MLMoods {
  happy: number | null;
  sad: number | null;
  aggressive: number | null;
  party: number | null;
  relaxed: number | null;
  acoustic: number | null;
  electronic: number | null;
}

export interface ParentGenre {
  genre: string;
  percentage: number;
}

export interface DetailedGenre {
  genre: string;
  probability: number;
}

export interface Instrument {
  instrument: string;
  probability: number;
}

export interface Song {
  id: string;
  title: string | null;
  artist: string | null;
  has_preview: boolean;
  file_metadata: FileMetadata | null;
  track_metadata: TrackMetadata | null;
  dsp_features: DSPFeatures | null;
  ml_profile: MLProfile | null;
  ml_moods: MLMoods | null;
  parent_genres: ParentGenre[];
  detailed_genres: DetailedGenre[];
  instruments: Instrument[];
}
